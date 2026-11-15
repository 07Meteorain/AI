"""自动生成的技能 handler —— 只回放已记录的工具调用，不含新逻辑。

由 ``brain evolve`` 于 2026-11-15T16:09:47+08:00 生成。
"""

from __future__ import annotations

from typing import Any

STEPS: list[dict[str, Any]] = [{'tool': 'memory.search', 'args': {'query': '复盘 记录', 'k': 5, 'layers': 'AR,T'}}, {'tool': 'skill.run', 'args': {'name': 'weekly-review', 'args': '{"week": ""}'}}, {'tool': 'memory.promote', 'args': {'apply': False}}]

WORKFLOW = 'memory.search>skill.run>memory.promote'


def _fill(value: Any, query: str) -> Any:
    if isinstance(value, str):
        return value.replace("{query}", query)
    if isinstance(value, dict):
        return {k: _fill(v, query) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, query) for v in value]
    return value


def run(ctx, args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    query = str(args.get("query") or args.get("text") or "")
    outputs = []
    failures = 0
    for step in STEPS:
        payload = _fill(step.get("args") or {}, query)
        result = ctx.tools.call(step["tool"], payload, ctx)
        if not result.ok:
            failures += 1
        outputs.append({"tool": step["tool"], "ok": result.ok, "error": result.error})
    return {
        "summary": f"回放 {len(STEPS)} 步（失败 {failures}）",
        "workflow": WORKFLOW,
        "steps": outputs,
        "query": query,
    }
