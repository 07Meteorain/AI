"""度量：怎么证明"它在进化"，而不是"它在变忙"。

三个指标必须同时看，否则很容易自欺：

* **步数**下降 —— 同一类任务从 3 步变 1 步，才叫固化；
* **命中率**上升 —— 检索真的找得到，而不是"库里东西变多了"；
* **成功率**不下降 —— 少了步骤但开始出错，那是退化不是进化。

``trend()`` 把 trace 按时间对半分，前半段 vs 后半段。样本少于 4 条就不给结论——
从这个量级里读出趋势，是在读噪声。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..config import Config
from ..util import iso, table


@dataclass
class Metrics:
    runs: int = 0
    sessions: int = 0
    ok: int = 0
    degraded: int = 0
    failed: int = 0
    avg_steps: float = 0.0
    avg_ms: float = 0.0
    tool_calls: int = 0
    tool_success: float = 0.0
    recall_queries: int = 0
    recall_hit_rate: float = 0.0
    distinct_intents: int = 0
    memory: dict[str, Any] = field(default_factory=dict)
    skills: dict[str, Any] = field(default_factory=dict)
    evolutions: int = 0
    first: str = ""
    last: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "sessions": self.sessions,
            "status": {"ok": self.ok, "degraded": self.degraded, "failed": self.failed},
            "avg_steps": round(self.avg_steps, 2),
            "avg_ms": round(self.avg_ms, 1),
            "tool_calls": self.tool_calls,
            "tool_success": round(self.tool_success, 3),
            "recall": {"queries": self.recall_queries, "hit_rate": round(self.recall_hit_rate, 3)},
            "distinct_intents": self.distinct_intents,
            "memory": self.memory,
            "skills": self.skills,
            "evolutions": self.evolutions,
            "window": {"first": self.first, "last": self.last},
        }

    def render(self) -> str:
        lines = [
            "运行",
            table(
                [
                    ["runs", self.runs],
                    ["sessions", self.sessions],
                    ["ok / degraded / failed", f"{self.ok} / {self.degraded} / {self.failed}"],
                    ["avg steps", f"{self.avg_steps:.2f}"],
                    ["avg duration", f"{self.avg_ms:.0f} ms"],
                    ["工具调用 / 成功率", f"{self.tool_calls} / {self.tool_success:.0%}"],
                    ["检索命中率", f"{self.recall_hit_rate:.0%}（{self.recall_queries} 次查询）"],
                    ["出现过的意图数", self.distinct_intents],
                    ["进化事件", self.evolutions],
                ],
                ["指标", "值"],
            ),
            "",
            "记忆（KSTAR）",
            table(
                [[k, v.get("count", 0), v.get("total_hits", 0)] for k, v in self.memory.get("layers", {}).items()],
                ["层", "条数", "被找回次数"],
            ),
            "",
            "技能",
            table(
                [
                    ["技能总数", self.skills.get("total", 0)],
                    ["草稿", self.skills.get("drafts", 0)],
                    ["被调用过", self.skills.get("used", 0)],
                    ["总调用次数", self.skills.get("calls", 0)],
                ],
                ["指标", "值"],
            ),
        ]
        return "\n".join(lines)


def compute(config: Config, memory: Any, traces: Iterable[dict[str, Any]], skills: Any = None) -> Metrics:
    traces = list(traces)
    m = Metrics(runs=len(traces))
    if not traces:
        m.memory = memory.stats()
        if skills is not None:
            rows = skills.loader.load_all()
            m.skills = {"total": len(rows), "drafts": sum(1 for s in rows if s.status == "draft"), "used": 0, "calls": 0}
        return m

    sessions = {str(t.get("session")) for t in traces}
    m.sessions = len(sessions)
    status = Counter(str(t.get("status")) for t in traces)
    m.ok, m.degraded, m.failed = status.get("ok", 0), status.get("degraded", 0), status.get("failed", 0)
    m.avg_steps = sum(len(t.get("steps") or []) for t in traces) / len(traces)
    m.avg_ms = sum(float(t.get("duration_ms") or 0) for t in traces) / len(traces)

    calls = 0
    ok_calls = 0
    for t in traces:
        for s in t.get("steps") or []:
            calls += 1
            ok_calls += 1 if s.get("ok") else 0
    m.tool_calls = calls
    m.tool_success = ok_calls / calls if calls else 1.0

    recall = [t for t in traces if str(t.get("intent")) in ("recall", "chat")]
    m.recall_queries = len(recall)
    if recall:
        m.recall_hit_rate = sum(1 for t in recall if int(t.get("recall_hits") or 0) > 0) / len(recall)

    m.distinct_intents = len({str(t.get("intent")) for t in traces})
    m.first = str(traces[0].get("started", ""))
    m.last = str(traces[-1].get("started", ""))
    m.memory = memory.stats()

    if skills is not None:
        rows = skills.loader.load_all()
        usage = skills.stats()
        m.skills = {
            "total": len(rows),
            "drafts": sum(1 for s in rows if s.status == "draft"),
            "used": len(usage),
            "calls": sum(u.get("calls", 0) for u in usage.values()),
        }
    try:
        from ..util import read_jsonl

        m.evolutions = len(read_jsonl(config.evolution_log))
    except Exception:  # noqa: BLE001
        m.evolutions = 0
    return m


def trend(traces: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """前后半段对比 + **按意图**的对比。

    为什么必须按意图分开看：一次 `capture` 是 1 步、一次 `review` 是 3 步。
    如果把不同意图混在一起算平均步数，步数下降可能只是"最近问的问题变简单了"，
    而不是"系统变快了"。**同类任务前后的步数变化，才是进化的证据。**
    """

    traces = list(traces)
    if len(traces) < 4:
        return {"insufficient": True, "runs": len(traces), "why": "样本少于 4 条，不给趋势结论"}

    half = len(traces) // 2

    def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
        if not rows:
            return {}
        steps = sum(len(t.get("steps") or []) for t in rows) / len(rows)
        ok_rate = sum(1 for t in rows if t.get("status") == "ok") / len(rows)
        recall = [t for t in rows if str(t.get("intent")) in ("recall", "chat")]
        hit = sum(1 for t in recall if int(t.get("recall_hits") or 0) > 0) / len(recall) if recall else 0.0
        return {"runs": len(rows), "avg_steps": round(steps, 2), "ok_rate": round(ok_rate, 3), "recall_hit": round(hit, 3)}

    first, second = summarize(traces[:half]), summarize(traces[half:])

    grouped: dict[str, list[dict[str, Any]]] = {}
    for trace in traces:
        grouped.setdefault(str(trace.get("intent") or "?"), []).append(trace)

    per_intent: dict[str, dict[str, Any]] = {}
    verdict: list[str] = []
    for intent, rows in sorted(grouped.items()):
        if len(rows) < 2:
            continue
        mid = len(rows) // 2
        before = sum(len(t.get("steps") or []) for t in rows[:mid]) / mid
        after_rows = rows[mid:]
        after = sum(len(t.get("steps") or []) for t in after_rows) / len(after_rows)
        delta = round(after - before, 2)
        per_intent[intent] = {
            "runs": len(rows),
            "before_steps": round(before, 2),
            "after_steps": round(after, 2),
            "delta": delta,
        }
        if delta <= -0.5:
            verdict.append(f"{intent}：{before:.1f} 步 → {after:.1f} 步（固化生效）")
        elif delta >= 0.5:
            verdict.append(f"{intent}：{before:.1f} 步 → {after:.1f} 步（变复杂了，注意是否过拟合）")

    if second.get("recall_hit", 0) > first.get("recall_hit", 0):
        verdict.append("检索命中率上升（同义词/沉淀生效）")
    elif second.get("recall_hit", 0) < first.get("recall_hit", 0):
        verdict.append("检索命中率下降（需要查同义词表或索引）")
    if second.get("ok_rate", 1) < first.get("ok_rate", 1):
        verdict.append("成功率下降 —— 退化信号，优先处理")

    return {
        "insufficient": False,
        "runs": len(traces),
        "first": first,
        "second": second,
        "per_intent": per_intent,
        "verdict": verdict or ["没有显著变化"],
        "generated_at": iso(),
    }


def render_trend(data: dict[str, Any]) -> str:
    if data.get("insufficient"):
        return f"趋势：{data.get('why')}（当前 {data.get('runs', 0)} 条）"
    a, b = data["first"], data["second"]
    blocks = ["进化趋势"]
    per_intent = data.get("per_intent") or {}
    if per_intent:
        blocks.append("按意图看（同一类任务的前后对比，这一张才是进化的证据）")
        blocks.append(
            table(
                [[name, v["runs"], v["before_steps"], v["after_steps"], f"{v['delta']:+.2f}"] for name, v in per_intent.items()],
                ["意图", "运行数", "前", "后", "变化"],
            )
        )
        blocks.append("")
    blocks.append("整体（混合意图，仅参考——capture 本来 1 步、review 本来 3 步）")
    blocks.append(
        table(
            [
                ["运行数", a["runs"], b["runs"]],
                ["平均步数", a["avg_steps"], b["avg_steps"]],
                ["成功率", f"{a['ok_rate']:.0%}", f"{b['ok_rate']:.0%}"],
                ["检索命中率", f"{a['recall_hit']:.0%}", f"{b['recall_hit']:.0%}"],
            ],
            ["指标", "前半段", "后半段"],
        )
    )
    blocks.append("")
    blocks.append("结论：" + "；".join(data["verdict"]))
    return "\n".join(blocks)
