"""输出排版：回执要能被人读，也要能被 grep。

原则：**每个结论都带一个可以复核的位置**。回答后面跟"哪几条记忆"，
工具调用后面跟"哪一步失败"，进化报告后面跟"改了什么文件"。
一个只会输出漂亮话的界面，会把系统的不确定性藏起来。
"""

from __future__ import annotations

from typing import Any, Iterable

from ..util import table, truncate

BAR = "─"


def header(text: str, width: int = 60) -> str:
    return f"{text}\n{BAR * width}"


def receipt(result: Any, *, verbose: bool = False) -> str:
    trace = result.trace
    lines = [header("执行回执")]
    lines.append(f"意图      {trace.intent}  (置信度 {trace.confidence:.2f})")
    lines.append(f"运行 id   {trace.run_id}")
    lines.append(f"状态      {trace.status}    {len(trace.steps)} 步    {trace.duration_ms:.1f} ms")
    lines.append("")
    if trace.steps:
        rows = []
        for step in trace.steps:
            rows.append([step.index, "✓" if step.ok else "✗", step.tool, truncate(step.error or step.note or "", 46)])
        lines.append(table(rows, ["#", "状态", "工具", "说明"]))
    if trace.meta.get("degraded_reasons"):
        lines.append("")
        lines.append("降级原因：")
        lines.extend(f"  - {r}" for r in trace.meta["degraded_reasons"])
    if verbose:
        lines.append("")
        lines.append("计划：")
        for item in trace.meta.get("plan", []):
            lines.append(f"  · {item}")
    lines.append("")
    lines.append(f"trace：memory/db/traces/{trace.started[:10]}.jsonl")
    if not trace.meta.get("reflected", True):
        lines.append("（只读模式：本次未写入记忆）")
    return "\n".join(lines)


def hits(hits: Iterable[Any]) -> str:
    rows = []
    for hit in hits:
        rows.append(
            [
                hit.record.layer,
                hit.record.id,
                truncate(hit.record.title, 30),
                f"{hit.score:.2f}",
                truncate("、".join(hit.matched[:4]), 22),
            ]
        )
    return table(rows, ["层", "id", "标题", "分数", "命中词"])


def memory_bar(memory: Any) -> str:
    stats = memory.stats()["layers"]
    cells = "   ".join(f"{layer}={stats[layer]['count']}" for layer in ("K", "S", "T", "AR"))
    return f"记忆  {cells}   索引 {memory.stats()['index_size']} 条   同义词 {memory.stats()['aliases']} 组"


def costs(trace: Any) -> str:
    calls = len(trace.steps)
    return f"{calls} 次工具调用 / {trace.duration_ms:.0f} ms"
