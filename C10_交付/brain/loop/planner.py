"""规划：把一句人话变成"要说几次工具、说什么"。

**默认是规则规划器**，不是模型。这个选择需要解释，因为它看起来像倒退：

* 一个没有 API key 的评审者，打开仓库要能跑出完整闭环。做不到这一点的"AI 系统"
  在我这里不算交付物。
* 规则规划器把"意图 → 步骤"的映射**写死且可测**，LLM 规划器接进来时
  就有了对照基线——它到底比规则强在哪，可以直接 A/B，而不是感觉。

接 LLM 时不用改循环：``brain/llm/provider.py`` 里的 ``LLMPlanner`` 实现同样的
``plan()`` 接口，失败自动降级回规则（trace 里标 ``degraded``）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

KINDS = ("capture", "recall", "task", "skill", "review", "chat")

INTENT_KEYWORDS = {
    "review": ("周复盘", "复盘", "review"),
    "capture": ("记一下", "记住", "记住这个", "记：", "note:", "capture", "存档"),
    "task": ("任务", "待办", "todo", "要做"),
    "skill": ("技能", "skill"),
    "recall": ("回忆", "找一下", "找出", "之前", "上次", "recall", "查一下", "还记得"),
}


@dataclass
class Intent:
    kind: str
    query: str
    text: str
    confidence: float
    rationale: str
    args: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.kind}:{self.query[:40]}"


@dataclass
class PlannedStep:
    tool: str
    args: dict[str, Any]
    why: str

    def __str__(self) -> str:
        return f"{self.tool}({_short(self.args)})"


def _short(args: dict[str, Any], limit: int = 48) -> str:
    parts = []
    for k, v in args.items():
        text = " ".join(str(v).split())
        parts.append(f"{k}={text[:limit]}")
    return ", ".join(parts)


class RulePlanner:
    """关键词 + 前缀的确定性分类器。

    诚实的边界：它只认**显式说法**。一句"帮我想想上次那个事"会被判成 chat
    而不是 recall——这不是 bug，是规则规划器的天花板；LLM 规划器就是为了这个
    场景存在的（见 README「三种运行模式」）。
    """

    def classify(self, text: str, context: dict[str, Any] | None = None) -> Intent:
        raw = (text or "").strip()
        low = raw.lower()
        if not raw:
            return Intent("chat", "", "", 0.2, "空输入")

        # 显式技能调用：技能 <name> <args>
        match = re.match(r"^(?:技能|skill|/skill)\s+([\w\-_.]+)\s*(.*)$", raw, re.IGNORECASE)
        if match:
            return Intent("skill", match.group(2).strip(), raw, 0.95, "显式技能前缀", {"skill": match.group(1)})

        # 任务完成：任务 完成 <id|标题>
        match = re.match(r"^(?:任务|todo)\s*(?:完成|done|做完)\s*(.+)$", raw, re.IGNORECASE)
        if match:
            return Intent("task", match.group(1).strip(), raw, 0.95, "任务完成句式", {"action": "done"})

        # 动作词开头优先：句首的"回忆/查一下"比句中的"复盘"更能说明意图。
        # 「回忆 复盘 周末」是在找东西，不是在要周报——这条规则就是为它加的。
        for kind, keywords in (("recall", ("回忆", "找一下", "查一下", "还记得")), ("capture", ("记一下", "记住", "记："))):
            for kw in keywords:
                if low.startswith(kw):
                    return Intent(kind, raw, raw, 0.85, f"句首动词「{kw}」")

        for kind in ("review", "capture", "task", "skill", "recall"):
            for kw in INTENT_KEYWORDS[kind]:
                if kw in low:
                    return Intent(kind, raw, raw, 0.8 if len(kw) > 2 else 0.65, f"命中关键词「{kw}」")

        if raw.endswith(("?", "？")) or "什么" in raw or "为什么" in raw:
            return Intent("recall", raw.rstrip("?？ "), raw, 0.6, "疑问句，优先检索记忆")
        return Intent("chat", raw, raw, 0.5, "无显式意图，按对话处理")

    def plan(self, intent: Intent, text: str, *, context: dict[str, Any] | None = None) -> list[PlannedStep]:
        kind = intent.kind

        # 先看有没有"已经固化过的同类流程"自动接管。
        # 只让 auto-* 草稿技能自动接管：人工技能必须显式调用，
        # 否则哪天有人加了一个 tag 相同的技能，行为就被悄悄改掉了。
        preferred = self._preferred_skill(kind, context)
        if preferred:
            return [
                PlannedStep(
                    "skill.run",
                    {"name": preferred, "args": json.dumps({"query": intent.query or text}, ensure_ascii=False)},
                    f"已固化的技能 {preferred} 接管（省掉重新规划）",
                )
            ]

        if kind == "capture":
            body = self._strip_prefix(text)
            forced = str(intent.args.get("layer") or "").upper()
            layer = forced if forced in ("K", "S") else ("K" if any(k in body for k in ("结论", "知识", "决策", "方法论", "原则")) else "S")
            return [
                PlannedStep(
                    "memory.write",
                    {
                        "text": body,
                        "layer": layer,
                        "tags": "capture",
                        "importance": 0.6 if layer == "S" else 0.8,
                    },
                    f"把这段话写进 {layer} 层",
                )
            ]
        if kind == "task":
            if intent.args.get("action") == "done":
                return [PlannedStep("task.done", {"id": intent.query}, "按 id/标题找任务并标记完成")]
            body = self._strip_prefix(text)
            return [PlannedStep("task.add", {"title": body[:40], "detail": body}, "新建任务并进 T 层")]
        if kind == "recall":
            return [PlannedStep("memory.search", {"query": intent.query or text, "k": 5}, "在四层记忆里检索")]
        if kind == "chat":
            return [
                PlannedStep("time.now", {}, "先确认现在是什么时候"),
                PlannedStep("memory.search", {"query": text, "k": 3}, "看看记忆里有没有相关背景"),
            ]
        if kind == "review":
            return [
                PlannedStep("memory.search", {"query": "复盘 记录", "k": 5, "layers": "AR,T"}, "先看这周发生过什么"),
                PlannedStep(
                    "skill.run",
                    {"name": "weekly-review", "args": json.dumps({"week": self._week_of(intent.query)}, ensure_ascii=False)},
                    "生成周复盘报告",
                ),
                PlannedStep("memory.promote", {"apply": False}, "把重复出现的工作流沉淀成知识"),
            ]
        if kind == "skill":
            name = intent.args.get("skill") or ""
            return [
                PlannedStep("skill.run", {"name": name, "args": json.dumps({"query": intent.query}, ensure_ascii=False)}, "调用指定技能")
            ]
        return [PlannedStep("memory.search", {"query": text, "k": 3}, "兜底检索")]

    @staticmethod
    def _week_of(text: str) -> str:
        """只有看起来真的像周编号才当周编号传下去。

        「回忆 复盘 周末」这种句子里，intent.query 是整句话；
        直接把它当 week 传给技能，会让技能抛"周编号格式不对"——而这个错
        本来就不该发生，因为用户根本没在指定周。
        """

        text = (text or "").strip()
        return text if re.match(r"^\d{4}-?W?\d{1,2}$", text, re.IGNORECASE) else ""

    @staticmethod
    def _preferred_skill(kind: str, context: dict[str, Any] | None) -> str:
        if kind == "skill":  # 显式点名的技能，不允许被接管
            return ""
        skills = (context or {}).get("skills")
        if skills is None:
            return ""
        try:
            rows = skills.loader.load_all()
        except Exception:  # noqa: BLE001 —— 技能层坏了不该让对话挂掉
            return ""
        for skill in rows:
            if skill.name.startswith("auto-") and kind in skill.tags and skill.executable and skill.status == "draft":
                return skill.name
        return ""

    @staticmethod
    def _strip_prefix(text: str) -> str:
        return re.sub(
            r"^(?:记一下|记住|记：|记:|note:|capture|存档|任务|待办|todo)[\s:：]*",
            "",
            (text or "").strip(),
            flags=re.IGNORECASE,
        ).strip() or (text or "").strip()
