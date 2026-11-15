"""沉淀：把"发生过的事"变成"以后用得上的东西"。

这是 KSTAR 与"存一堆日志"的分界线。日志只会越长越大；沉淀会让库**变短变准**。

四条规则（每条都有单独测试）：

==================  ============================================  ==========================
编号                 触发条件                                      动作
==================  ============================================  ==========================
P1                   任务 T 被标记 done                            生成一条 AR（结果 + 耗时）
P2                   同一工作流签名（工具序列）≥ 3 条成功           提议沉淀为 K「已验证流程」
P3                   同一错误的 AR ≥ 2 条                          提议沉淀为 K「已知坑」
P4                   S 记录超过 ``archive_after_days`` 且从未被找回  标记 ``archived``（不删除）
==================  ============================================  ==========================

``archive`` 而不是 ``delete``：记忆系统的删除必须是可撤销的，
否则一次误判就永久弄丢了一段经历。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..util import days_between, iso, truncate

if TYPE_CHECKING:  # pragma: no cover
    from .kstar import KSTARMemory
    from .store import Record


@dataclass
class Proposal:
    """一条待确认的沉淀提议。``--apply`` 之前它什么也不会改。"""

    kind: str
    reason: str
    suggestion: str
    records: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    applied: bool = False

    def line(self) -> str:
        mark = "✓" if self.applied else "·"
        return f"{mark} [{self.kind}] {self.reason} → {self.suggestion}"


def task_done_to_action(memory: "KSTARMemory", task: "Record") -> "Record":
    """P1：任务完成 → 一条可追溯的行动记录。"""

    started = task.meta.get("started") or task.created
    took = round(days_between(started), 2)
    text = f"完成任务「{task.title}」，耗时约 {took} 天。结果：{task.text.strip() or '（未填写）'}"
    return memory.write(
        "AR",
        text,
        title=f"完成：{task.title}",
        tags=["task"] + list(task.tags),
        source=task.source,
        importance=0.6,
        status="ok",
        meta={"intent": "task.done", "task_id": task.id, "days": took},
        dedupe=True,
    )


def collect_proposals(
    memory: "KSTARMemory",
    *,
    promote_threshold: int = 3,
    archive_after_days: float = 14.0,
) -> list[Proposal]:
    proposals: list[Proposal] = []

    # ---- P2：重复成功流程 → 知识 ----
    # 按**工作流签名**（工具调用序列）分组，而不是按意图字面。
    # "复盘" 与 "周复盘" 的意图标签可能不同，但 memory.search>skill.run>memory.write
    # 这条流程是同一个——可复用的是流程，不是说法。
    buckets: dict[str, list["Record"]] = {}
    for rec in memory.all("AR"):
        if rec.status != "ok":
            continue
        workflow = str(rec.meta.get("workflow") or "").strip()
        if workflow.count(">") < 1:  # 单步动作没有"流程"可言
            continue
        if rec.meta.get("from_skill"):  # 已经是技能跑出来的，不需要再固化
            continue
        buckets.setdefault(workflow, []).append(rec)

    for workflow, recs in sorted(buckets.items()):
        if len(recs) < promote_threshold:
            continue
        if _knowledge_covers(memory, f"workflow:{workflow}"):
            continue
        payload = {
            "workflow": workflow,
            "count": len(recs),
            "records": [r.id for r in recs[-5:]],
            "steps": [s for s in (recs[-1].meta.get("steps") or [])],
            "samples": [str(r.meta.get("intent") or "") for r in recs[-5:]],
        }
        proposals.append(
            Proposal(
                kind="ar→k",
                reason=f"工作流「{workflow}」已成功重复 {len(recs)} 次",
                suggestion="沉淀为知识层「已验证流程」卡片，并考虑固化成技能",
                records=payload["records"],
                payload=payload,
            )
        )

    # ---- P3：重复失败 → 已知坑 ----
    errors: dict[str, list["Record"]] = {}
    for rec in memory.all("AR"):
        if rec.status != "failed":
            continue
        sig = str(rec.meta.get("error") or "").strip()
        if not sig:
            continue
        errors.setdefault(sig, []).append(rec)

    for sig, recs in sorted(errors.items()):
        if len(recs) < 2:
            continue
        if _knowledge_covers(memory, f"坑:{sig}"):
            continue
        proposals.append(
            Proposal(
                kind="failure→k",
                reason=f"同一错误已出现 {len(recs)} 次：{truncate(sig, 40)}",
                suggestion="沉淀为知识层「已知坑」条目（含规避方法）",
                records=[r.id for r in recs],
                payload={"error": sig, "count": len(recs)},
            )
        )

    # ---- P4：变冷的情境 ----
    cold = [
        r
        for r in memory.all("S")
        if r.hits == 0 and not r.meta.get("archived") and days_between(r.created) >= archive_after_days
    ]
    if cold:
        proposals.append(
            Proposal(
                kind="s→archive",
                reason=f"{len(cold)} 条情境记录超过 {archive_after_days:.0f} 天且从未被找回",
                suggestion="标记 archived（保留原文，不删除）",
                records=[r.id for r in cold],
                payload={"ids": [r.id for r in cold]},
            )
        )

    return proposals


def _knowledge_covers(memory: "KSTARMemory", intent: str) -> bool:
    for rec in memory.all("K"):
        if rec.meta.get("covers") == intent:
            return True
    return False


def apply_proposal(memory: "KSTARMemory", proposal: Proposal) -> bool:
    """执行一条提议，返回是否真的改动了记忆。"""

    if proposal.applied:
        return False

    if proposal.kind == "ar→k":
        workflow = proposal.payload["workflow"]
        count = proposal.payload["count"]
        steps = proposal.payload.get("steps") or []
        step_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps)) or "  （未记录步骤）"
        text = (
            f"已验证流程：`{workflow}`，已成功重复 {count} 次。\n"
            f"步骤：\n{step_text}\n"
            f"沉淀时间 {iso()}。来源记录：{', '.join(proposal.records)}。\n"
            "复用方式：`brain evolve --apply` 会把它固化成技能；在那之前，"
            "直接照着步骤走也比重新想一遍快。"
        )
        memory.write(
            "K",
            text,
            title=f"已验证流程：{truncate(workflow, 40)}",
            tags=["流程", "沉淀"],
            source="promote",
            importance=0.8,
            meta={"covers": f"workflow:{workflow}", "kind": "playbook", "evidence": proposal.records},
            dedupe=True,
        )
        proposal.applied = True
        return True

    if proposal.kind == "failure→k":
        error = proposal.payload["error"]
        text = (
            f"已知坑：`{truncate(error, 120)}`\n"
            f"已累计遇到 {proposal.payload['count']} 次。\n"
            "先查这条再动手；若已修复，请把修复方式补在本条下方（保留原始现象）。\n"
            f"证据：{', '.join(proposal.records)}"
        )
        memory.write(
            "K",
            text,
            title=f"已知坑：{truncate(error, 24)}",
            tags=["坑", "故障"],
            source="promote",
            importance=0.75,
            meta={"covers": f"坑:{error}", "kind": "pitfall", "evidence": proposal.records},
            dedupe=True,
        )
        proposal.applied = True
        return True

    if proposal.kind == "s→archive":
        changed = 0
        for rid in proposal.payload["ids"]:
            rec = memory.get(rid)
            if rec is None:
                continue
            meta = dict(rec.meta)
            meta["archived"] = True
            meta["archived_at"] = iso()
            memory.update(rid, meta=meta, importance=max(0.1, rec.importance - 0.2))
            changed += 1
        proposal.applied = changed > 0
        return proposal.applied

    return False
