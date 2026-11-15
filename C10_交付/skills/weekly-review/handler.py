"""weekly-review：把一周的 trace/记忆压成一页纸。

刻意不做的事：不写"本周辛苦了"这类总结。复盘报告的价值在于**能被下一次行动引用**，
所以每条结论都必须挂着一个可点击的记录 id。
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path

WEEK_RE = re.compile(r"^(\d{4})-?W?(\d{1,2})$", re.IGNORECASE)


def _parse_week(raw: str) -> tuple[int, int, dt.date, dt.date]:
    raw = (raw or "").strip()
    if raw:
        match = WEEK_RE.match(raw)
        if not match:
            raise ValueError(f"周编号格式应为 2026-W46，收到 {raw!r}")
        year, week = int(match.group(1)), int(match.group(2))
        if not 1 <= week <= 53:
            raise ValueError(f"周编号越界：{week}")
        start = dt.date.fromisocalendar(year, week, 1)
    else:
        today = dt.date.today()
        year, week, _ = today.isocalendar()
        start = dt.date.fromisocalendar(year, week, 1)
    return year, week, start, start + dt.timedelta(days=6)


def run(ctx, args=None):
    args = args or {}
    year, week, start, end = _parse_week(str(args.get("week") or ""))
    label = f"{year}-W{week:02d}"

    def in_range(record) -> bool:
        try:
            day = dt.date.fromisoformat(record.created[:10])
        except ValueError:
            return False
        return start <= day <= end

    actions = [r for r in ctx.memory.all("AR") if in_range(r)]
    tasks = [r for r in ctx.memory.all("T") if in_range(r)]
    knowledge = [r for r in ctx.memory.all("K") if in_range(r)]

    if not actions and not tasks:
        return {"summary": f"{label} 没有任何记录，不生成空报告。", "empty": True, "counts": {}}

    intents = Counter(str(r.meta.get("intent") or "?") for r in actions)
    failed = [r for r in actions if r.status == "failed"]
    steps = [len(r.meta.get("steps") or []) for r in actions if r.meta.get("steps")]
    avg_steps = round(sum(steps) / len(steps), 2) if steps else 0.0
    done_tasks = [r for r in tasks if r.status == "done"]

    lines = [
        f"# 周复盘 {label}",
        "",
        f"> 区间 {start} ~ {end} ｜ 自动生成于 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "> 生成方式：`skills/weekly-review/handler.py`，数据源 AR/T/K 三层。",
        "",
        "## 一、数字",
        "",
        f"- 行动记录：**{len(actions)}** 条（失败 {len(failed)}）",
        f"- 平均步数：**{avg_steps}**",
        f"- 任务：新建 {len(tasks)}，完成 {len(done_tasks)}",
        f"- 新增知识：**{len(knowledge)}** 条",
        "",
        "## 二、意图分布",
        "",
        "| 意图 | 次数 |",
        "| --- | --- |",
    ]
    lines += [f"| {name} | {count} |" for name, count in intents.most_common()]
    lines += ["", "## 三、失败与坑", ""]
    if failed:
        for rec in failed[:8]:
            err = str(rec.meta.get("error") or "").strip() or "（未记录错误）"
            lines.append(f"- `{rec.id}` {err[:120]}")
    else:
        lines.append("- 本周没有失败的运行记录。")

    lines += ["", "## 四、值得固化的事", ""]
    workflows = Counter(str(r.meta.get("workflow") or "") for r in actions if r.meta.get("workflow"))
    repeated = [(wf, c) for wf, c in workflows.most_common(3) if c >= 2 and ">" in wf]
    if repeated:
        for wf, count in repeated:
            lines.append(f"- `{wf}` 重复 {count} 次 → 可以 `brain evolve --apply` 固化成技能")
    else:
        lines.append("- 没有重复到值得固化的流程（阈值：同一条流程 ≥ 2 次）。")

    lines += ["", "## 五、下周只改一件事", "", "- [ ] （人填：从上面四节里挑一件，写下具体动作）", ""]

    text = "\n".join(lines)
    out = str(args.get("out") or "").strip()
    path = Path(out) if out else ctx.config.home / "reviews" / f"{label}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    return {
        "summary": f"{label} 复盘：{len(actions)} 次行动（失败 {len(failed)}），{len(done_tasks)} 个任务完成，{len(knowledge)} 条新知识",
        "path": ctx.config.rel(path),
        "counts": {
            "actions": len(actions),
            "failed": len(failed),
            "tasks": len(tasks),
            "done": len(done_tasks),
            "knowledge": len(knowledge),
            "avg_steps": avg_steps,
        },
    }
