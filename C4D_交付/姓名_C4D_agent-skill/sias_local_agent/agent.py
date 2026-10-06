"""Agent 主循环：function calling 路由 + ReAct 多步推理 + 记忆注入。

这是技能包的调度中枢。对应 rubric 的三个核心信号：
* 「有技能」—— 工具注册表 + 技能编排
* 「有记忆」—— 每次调用注入历史与长期事实
* 「功能可用」—— 端到端可跑通的地图生成 / 问答 / 规划

主循环采用 Ollama 原生 function calling：
    while未达最大步数:
        resp = llm.chat(messages, tools=schemas)
        if resp.tool_calls: 执行工具，追加 tool 结果到 messages
        else: 视为最终答案，退出
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .knowledge import knowledge_catalog, search_knowledge
from .llm import LLMResponse, OllamaClient, OllamaError, _extract_json
from .memory import MemoryStore, memory_prompt_block
from .tools import Tool, ToolError, build_registry, tool_stats

SYSTEM_PROMPT = """你是一个运行在**用户自己电脑上的**离线地图与规划 Agent。

你的运行环境：
- 你完全在本地运行，不调用任何云端 API，不产生任何费用。
- 你可以通过工具访问一个随技能包分发的本地知识库，其中包含西亚斯学院
  (SIAS University) 及周边地点的**真实经纬度**。

核心规则：
1. 你自己决定调用哪个工具、需要调用几次。不要向用户解释你要调用什么，
   直接调用。
2. 任何地点的经纬度都必须来自 `get_reference` 工具或下方「本地知识目录」，
   **绝不允许自己编造坐标**。
3. 最终输出必须是**严格合法的 JSON**，不要包含 markdown 代码围栏，
   不要包含任何 JSON 之外的解释文字。
4. 所有文本字段都要同时提供中文与英文两个版本（`*_zh` 与 `*_en`）。

可用工具：
{tool_docs}
"""

PLANNING_PROMPT = """你是一个本地运行的行程规划 Agent。
你可以使用工具检索本地知识库、校验坐标、规划路线。
最终输出严格 JSON，格式：
{{
  "title_zh": "...", "title_en": "...",
  "summary_zh": "...", "summary_en": "...",
  "steps": [
    {{"order": 1, "name_zh": "...", "name_en": "...",
      "description_zh": "...", "description_en": "...",
      "minutes": 30}}
  ],
  "total_minutes": 120
}}
{tool_docs}
"""


@dataclass
class AgentStep:
    """Agent 单步执行记录，构成可审计的推理轨迹。"""

    index: int
    kind: str  # "tool_call" | "final"
    detail: str
    tool_name: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    result_preview: str = ""
    elapsed_s: float = 0.0
    tok_per_second: float = 0.0
    tokens: int = 0


@dataclass
class AgentRun:
    """一次完整 Agent 运行的产物。"""

    ok: bool
    final_text: str
    parsed: Any
    steps: list[AgentStep] = field(default_factory=list)
    total_tokens: int = 0
    total_seconds: float = 0.0
    tool_calls: int = 0
    memory_summary: str = ""
    error: str | None = None

    def trace(self) -> str:
        """把推理轨迹渲染成可读日志（写入交付物）。"""
        lines = []
        for s in self.steps:
            head = f"[{s.index}] {s.kind}"
            if s.tool_name:
                head += f" tool={s.tool_name}"
            head += f" ({s.elapsed_s:.1f}s, {s.tok_per_second:.1f} tok/s)"
            lines.append(head)
            if s.args:
                lines.append(f"    args: {json.dumps(s.args, ensure_ascii=False)[:160]}")
            if s.result_preview:
                lines.append(f"    -> {s.result_preview[:200]}")
            if s.kind == "final":
                lines.append(f"    final: {s.detail[:300]}")
        return "\n".join(lines)

    def summary(self) -> str:
        return (
            f"ok={self.ok} steps={len(self.steps)} tools={self.tool_calls} "
            f"tokens={self.total_tokens} {self.total_seconds:.1f}s "
            f"memory[{self.memory_summary}]"
        )


class LocalAgent:
    """具备工具调用、结构化输出与记忆的本地 Agent。"""

    def __init__(
        self,
        client: OllamaClient,
        memory: MemoryStore,
        max_steps: int = 6,
        verbose: bool = True,
    ) -> None:
        self.client = client
        self.memory = memory
        self.max_steps = max_steps
        self.verbose = verbose
        self.registry: dict[str, Tool] = build_registry()
        self.logger: Callable[[str], None] = (
            print if verbose else (lambda _m: None)
        )

    # ---------- 提示词组装 ----------

    def _tool_docs(self) -> str:
        lines = []
        for name, tool in self.registry.items():
            props = ", ".join(tool.parameters.get("properties", {}).keys())
            req = ", ".join(tool.parameters.get("required", []))
            lines.append(
                f"- `{name}({props})` [必填: {req or '无'}]: {tool.description}"
            )
        return "\n".join(lines)

    def _system_prompt(self, base: str = SYSTEM_PROMPT) -> str:
        facts = self.memory.recall()
        return base.format(tool_docs=self._tool_docs()) + memory_prompt_block(facts)

    # ---------- 主循环 ----------

    def run(
        self,
        user_input: str,
        system_prompt: str | None = None,
        expect_json: bool = True,
        context_kb: bool = True,
    ) -> AgentRun:
        """执行一次完整的 Agent 推理循环。

        参数
        ----
        user_input    用户指令
        system_prompt 自定义系统提示（默认地图 Agent）
        expect_json   是否要求最终输出为 JSON
        context_kb    是否把本地知识目录注入上下文（小模型更需要显式目录）
        """
        base = system_prompt or SYSTEM_PROMPT
        started = time.time()
        steps: list[AgentStep] = []
        tool_calls = 0
        total_tokens = 0

        # 把用户输入记入记忆（长期记忆的来源）
        self.memory.add_turn("user", user_input)

        msgs, mem_stats = self.memory.build_messages(self._system_prompt(base))
        self.logger(f"  [memory] {mem_stats.summary()}")

        # 注入本地知识目录：显式列出可用的真实坐标，显著降低幻觉率
        if context_kb:
            catalog = knowledge_catalog()
            msgs.append(
                {
                    "role": "user",
                    "content": (
                        "以下是本地知识库中可用的地点（含真实坐标，务必从这里取）：\n"
                        + json.dumps(catalog, ensure_ascii=False, indent=1)
                        + "\n\n请基于以上地点完成我的请求。"
                    ),
                }
            )

        if expect_json:
            msgs.append(
                {
                    "role": "user",
                    "content": (
                        "记住：最终只输出 JSON，不要任何其他文字。"
                        "每条记录都要有 name/name_zh/description/description_en/"
                        "latitude/longitude/category 字段。"
                    ),
                }
            )

        schema_hint = (
            '{"locations":[{"name":..,"name_zh":..,"description":..,'
            '"description_en":..,"latitude":float,"longitude":float,'
            '"category":..}]}'
        )

        final_text = ""
        parsed: Any = None
        error: str | None = None
        resp: LLMResponse | None = None

        for idx in range(1, self.max_steps + 1):
            t0 = time.time()
            try:
                resp = self.client.chat(msgs, tools=[t.to_schema() for t in self.registry.values()])
            except OllamaError as exc:
                error = str(exc)
                break

            total_tokens += resp.eval_count
            dt = time.time() - t0

            # --- 分支 1：模型要求调用工具 ---
            if resp.tool_calls:
                for call in resp.tool_calls:
                    fn = call.get("function", {}) or {}
                    tool_name = fn.get("name", "")
                    raw_args = fn.get("arguments", {}) or {}
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                    else:
                        args = raw_args

                    msgs.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [call],
                        }
                    )

                    tool = self.registry.get(tool_name)
                    if tool is None:
                        out = json.dumps(
                            {"error": f"未知工具 {tool_name}"}, ensure_ascii=False
                        )
                    else:
                        try:
                            out = tool.invoke(args)
                        except ToolError as exc:
                            out = json.dumps({"error": str(exc)}, ensure_ascii=False)

                    tool_calls += 1
                    msgs.append(
                        {
                            "role": "tool",
                            "content": out[:1800],
                            "name": tool_name,
                        }
                    )
                    steps.append(
                        AgentStep(
                            index=idx,
                            kind="tool_call",
                            detail=f"call {tool_name}",
                            tool_name=tool_name,
                            args=args,
                            result_preview=out[:200],
                            elapsed_s=dt,
                            tok_per_second=resp.tokens_per_second,
                            tokens=resp.eval_count,
                        )
                    )
                    self.logger(
                        f"  [step {idx}] tool={tool_name} "
                        f"args={json.dumps(args, ensure_ascii=False)[:90]} "
                        f"({resp.tokens_per_second:.1f} tok/s)"
                    )
                continue

            # --- 分支 2：模型给出最终答案 ---
            final_text = resp.content
            steps.append(
                AgentStep(
                    index=idx,
                    kind="final",
                    detail=final_text,
                    elapsed_s=dt,
                    tok_per_second=resp.tokens_per_second,
                    tokens=resp.eval_count,
                )
            )
            self.logger(
                f"  [step {idx}] final ({resp.tokens_per_second:.1f} tok/s)"
            )
            if expect_json:
                # 优先就地解析本轮输出——模型已经给出最终答案了，
                # 不应为此再发一次推理请求（既慢又可能得到无关回复）。
                # 只有就地解析失败时，才让客户端带着错误信息回灌重试。
                try:
                    parsed = _extract_json(final_text)
                except OllamaError as first_err:
                    self.logger(f"  [parse] 就地解析失败({first_err})，回灌重试")
                    try:
                        parsed, retry_resp = self.client.structured(
                            [
                                {"role": "system",
                                 "content": self._system_prompt(base)},
                                {"role": "user", "content": final_text},
                            ],
                            schema_hint=schema_hint,
                        )
                        total_tokens += retry_resp.eval_count
                    except OllamaError as exc:
                        error = f"最终输出解析失败: {exc}"
            break
        else:
            error = f"达到最大步数 {self.max_steps}，未产出最终答案"

        self.memory.add_turn("assistant", final_text or (error or ""))
        stats = self.memory.stats()
        self.memory.log_run(
            "agent_run",
            {
                "input": user_input,
                "ok": error is None,
                "steps": [s.detail for s in steps],
                "tool_calls": tool_calls,
                "tokens": total_tokens,
                "seconds": round(time.time() - started, 2),
            },
        )

        return AgentRun(
            ok=error is None,
            final_text=final_text,
            parsed=parsed,
            steps=steps,
            total_tokens=total_tokens,
            total_seconds=round(time.time() - started, 2),
            tool_calls=tool_calls,
            memory_summary=stats.summary(),
            error=error,
        )

    # ---------- 便捷方法 ----------

    def generate_locations(
        self,
        count: int = 8,
        focus: str = "校园与周边",
        notes: str = "",
    ) -> AgentRun:
        """让 Agent 生成一组结构化地点数据（地图生成的输入）。"""
        catalog = knowledge_catalog()
        lines = "\n".join(
            f"- {c['name_zh']} ({c['name']}) | id={c['id']} | "
            f"{c['lat']},{c['lng']} | {c['category_zh']}"
            for c in catalog
        )
        user_input = (
            f"请从下面这份本地地点清单中挑选 {count} 个最有代表性的地点，"
            f"范围侧重「{focus}」。\n"
            f"必须包含郑州西亚斯学院主校区本身。\n"
            f"为每个地点写一段 30~60 字的中文描述和一段对应的英文描述，"
            f"要体现该地点与校园的关系或特色。\n"
            f"坐标直接沿用清单中的真实值，不要修改。\n"
            + (f"\n额外要求：{notes}" if notes else "")
            + "\n\n本地地点清单：\n"
            + lines
        )
        return self.run(user_input, expect_json=True, context_kb=False)

    def plan_itinerary(
        self,
        site_count: int = 6,
        minutes_per_site: int = 40,
    ) -> AgentRun:
        """让 Agent 规划一条多步参观行程（多步推理 + 工具调用）。"""
        user_input = (
            f"请规划一条在西雅斯学院及周边游览的行程，共 {site_count} 个地点，"
            f"每个地点停留约 {minutes_per_site} 分钟。"
            f"请先调用 get_reference 工具确认地点坐标，"
            f"再用 plan_route 工具排好顺序，最后输出 JSON。"
            f"每个步骤要包含中英文名称与描述，以及建议停留分钟数。"
        )
        return self.run(user_input, system_prompt=PLANNING_PROMPT, expect_json=True)

    def chat(self, user_input: str) -> AgentRun:
        """自由问答（不强制 JSON）。"""
        return self.run(
            user_input,
            expect_json=False,
            context_kb=True,
        )

    def remember(self, key: str, value: str) -> None:
        """由外部（或 Agent）显式写入长期记忆。"""
        self.memory.remember(key, value)

    def tool_usage(self) -> list[dict[str, Any]]:
        return tool_stats(self.registry)


__all__ = [
    "LocalAgent",
    "AgentRun",
    "AgentStep",
    "SYSTEM_PROMPT",
    "PLANNING_PROMPT",
]