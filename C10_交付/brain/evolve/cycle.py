"""进化周期：一次 ``evolve`` 做四件事，默认全部只看不改。

    ① 挖重复工作流 → 生成技能草稿（改代码，所以默认不写）
    ② 挖查询失败   → 学同义词（改索引，默认不写）
    ③ 跑沉淀规则   → AR 变知识、冷情境归档（默认不写）
    ④ 算度量       → 前后半段对比，判断"是不是真的在变好"

``--apply`` 才会落盘。每一次落盘都进 ``memory/db/evolution.jsonl``：
系统改了自己什么，必须留一笔，否则它就是一个无法审计的自修改程序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import Config
from ..memory.promote import apply_proposal, collect_proposals
from ..loop.trace import TraceStore
from ..util import append_jsonl, iso
from . import metrics as metrics_mod
from . import miner
from .scaffold import draft_skill


@dataclass
class EvolutionReport:
    generated_at: str
    runs: int
    patterns: list[str] = field(default_factory=list)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    aliases: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[str] = field(default_factory=list)
    applied: int = 0
    stale_skills: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    trend: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = True

    def render(self) -> str:
        lines = [f"进化周期 @ {self.generated_at}   （{'只看不改' if self.dry_run else '已落盘'}）", ""]
        lines.append(f"扫描 {self.runs} 条 trace。")
        lines.append("")
        lines.append("① 重复工作流")
        lines.extend([f"   - {p}" for p in self.patterns] or ["   （没有达到阈值的重复工作流）"])
        lines.append("")
        lines.append("② 技能草稿")
        if self.drafts:
            for d in self.drafts:
                mark = "✓" if d.get("ok") else "✗"
                lines.append(f"   {mark} {d.get('reason')}")
        else:
            lines.append("   （没有需要固化的流程）")
        lines.append("")
        lines.append("③ 同义词候选")
        if self.aliases:
            for a in self.aliases:
                lines.append(f"   - 「{a['key']}」→ {'、'.join(a['targets'])}   （没问到：{a['miss']}）")
        else:
            lines.append("   （没有可学的同义词）")
        lines.append("")
        lines.append("④ 沉淀提议")
        lines.extend([f"   {p}" for p in self.proposals] or ["   （没有需要沉淀的记录）"])
        if self.stale_skills:
            lines.append("")
            lines.append("⑤ 长期未用的技能（建议复审，不要直接删）")
            lines.extend([f"   - {s}" for s in self.stale_skills])
        lines.append("")
        lines.append(f"本次落盘改动：{self.applied} 处。")
        return "\n".join(lines)


def evolve_once(
    config: Config,
    memory: Any,
    loader: Any,
    runtime: Any,
    *,
    apply: bool = False,
    min_runs: int = 3,
) -> EvolutionReport:
    traces = TraceStore(config).all()
    report = EvolutionReport(generated_at=iso(), runs=len(traces), dry_run=not apply)

    patterns = miner.workflows(traces, min_runs=min_runs)
    report.patterns = [p.line() for p in patterns]

    # ① 技能草稿
    existing = loader.load_all(force=True)
    covered = {tuple(s.tools) for s in existing if s.tools}
    for pattern in patterns:
        if tuple(pattern.tools) in covered:
            continue
        info = draft_skill(
            config,
            workflow=pattern.signature,
            label=pattern.label,
            count=pattern.count,
            runs=pattern.runs,
            write=apply,
        )
        if info.get("ok") and not info.get("planned"):
            append_jsonl(config.evolution_log, {"ts": iso(), "kind": "skill_draft", **info})
            report.applied += 1
            loader.load_all(force=True)
        report.drafts.append(info)

    # ② 同义词
    known = memory.known_terms() if hasattr(memory, "known_terms") else set()
    curated: set[str] = set()
    try:
        from ..util import tokenize

        for rec in memory.all("K"):
            curated.update(tokenize(rec.keyword_haystack()))
    except Exception:  # noqa: BLE001
        curated = set()
    for cand in miner.alias_candidates(traces, known, curated):
        report.aliases.append(cand)
        if apply and memory.add_alias(cand["key"], cand["targets"], source="evolve"):
            report.applied += 1

    # ③ 沉淀
    proposals = collect_proposals(memory)
    for proposal in proposals:
        if apply:
            changed = apply_proposal(memory, proposal)
            if changed:
                append_jsonl(
                    config.evolution_log,
                    {"ts": iso(), "kind": "promote", "proposal": proposal.kind, "reason": proposal.reason},
                )
                report.applied += 1
        report.proposals.append(proposal.line())

    # ④ 度量
    report.metrics = metrics_mod.compute(config, memory, traces, runtime).as_dict()
    report.trend = metrics_mod.trend(traces)
    report.stale_skills = miner.unused_skills(runtime.stats(), [s.name for s in loader.load_all()])
    return report
