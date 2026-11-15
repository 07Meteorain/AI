"""从 trace 里挖东西：哪些流程重复了、哪些工具在失败、哪些查询白问了。

挖矿的原则是**只挖已经发生过三次以上的事**。一两次的偶然重复看起来也像模式，
但把它固化成技能，等于把噪声写进基础设施——以后每次调用都在放大那次的偶然。

三条产出：

* ``WorkflowPattern``  → 该固化成技能（交给 ``scaffold.py``）
* ``failure_stats``    → 该修工具 / 该写"已知坑"（交给 ``promote.py``）
* ``alias_candidates`` → 该学同义词（写回 ``memory/db/aliases.json``）
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..util import days_between, tokenize, truncate

CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")


@dataclass
class WorkflowPattern:
    signature: str
    runs: list[dict[str, Any]] = field(default_factory=list)
    intents: Counter = field(default_factory=Counter)

    @property
    def count(self) -> int:
        return len(self.runs)

    @property
    def tools(self) -> list[str]:
        return [t for t in self.signature.split(">") if t]

    @property
    def label(self) -> str:
        return self.intents.most_common(1)[0][0] if self.intents else "flow"

    def sample(self) -> dict[str, Any]:
        return self.runs[-1]

    def line(self) -> str:
        return f"{self.signature}  ×{self.count}  （主导意图 {self.label}）"


def signature(trace: dict[str, Any]) -> str:
    steps = trace.get("steps") or []
    return ">".join(str(s.get("tool", "")) for s in steps if s.get("tool"))


def workflows(traces: Iterable[dict[str, Any]], *, min_runs: int = 3, min_steps: int = 2) -> list[WorkflowPattern]:
    patterns: dict[str, WorkflowPattern] = {}
    for trace in traces:
        if trace.get("status") != "ok":
            continue
        sig = signature(trace)
        if sig.count(">") + 1 < min_steps:
            continue
        if all(s.get("tool") == "skill.run" for s in trace.get("steps") or []):
            continue  # 全是技能调用，没有可固化的编排
        pattern = patterns.setdefault(sig, WorkflowPattern(signature=sig))
        pattern.runs.append(trace)
        pattern.intents[str(trace.get("intent") or "?")] += 1

    found = [p for p in patterns.values() if p.count >= min_runs]
    found.sort(key=lambda p: (-p.count, p.signature))
    return found


def failure_stats(traces: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "failed": 0, "errors": Counter()})
    for trace in traces:
        for step in trace.get("steps") or []:
            tool = str(step.get("tool") or "?")
            out[tool]["calls"] += 1
            if not step.get("ok"):
                out[tool]["failed"] += 1
                err = str(step.get("error") or "?").split(":")[0]
                out[tool]["errors"][err] += 1
    result: dict[str, dict[str, Any]] = {}
    for tool, slot in out.items():
        calls = slot["calls"]
        result[tool] = {
            "calls": calls,
            "failed": slot["failed"],
            "success_rate": round(1 - slot["failed"] / calls, 3) if calls else 1.0,
            "top_error": slot["errors"].most_common(1)[0][0] if slot["errors"] else "",
        }
    return result


def recall_misses(traces: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in traces if str(t.get("intent")) in ("recall", "chat") and int(t.get("recall_hits") or 0) == 0]


def alias_candidates(
    traces: list[dict[str, Any]],
    known_terms: set[str],
    curated_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    """同义词候选：同一 session 里"先问不到、换个说法问到了"，把差别记下来。

    两个词表是分开的，这一点很关键：

    * ``known_terms``（全部索引词）用来判断"换个说法后命中的词"是否真的存在；
    * ``curated_terms``（只取 K 层）用来判断"原话里的哪个词系统压根没学过"。

    为什么不能都用全量索引：每次提问本身都会被写进 S/AR 层，于是**没问到的那个词
    立刻变成了"索引里有的词"**，再拿它做"未知词"判断就永远判不出来。
    用 K 层（人工/技能沉淀过的知识）当"学过没有"的标尺，才稳定。
    """

    curated = curated_terms if curated_terms is not None else known_terms
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in sorted(traces, key=lambda t: str(t.get("started", ""))):
        by_session[str(trace.get("session") or "default")].append(trace)

    out: list[dict[str, Any]] = []
    for session, runs in by_session.items():
        for prev, nxt in zip(runs, runs[1:]):
            if int(prev.get("recall_hits") or 0) != 0:
                continue
            if int(nxt.get("recall_hits") or 0) == 0:
                continue
            if str(prev.get("intent")) not in ("recall", "chat"):
                continue
            key = _unknown_phrase(str(prev.get("input") or ""), curated)
            targets = [t for t in tokenize(str(nxt.get("input") or "")) if t in known_terms][:3]
            if not key or not targets:
                continue
            out.append(
                {
                    "key": key,
                    "targets": targets,
                    "session": session,
                    "miss": truncate(str(prev.get("input")), 60),
                    "hit": truncate(str(nxt.get("input")), 60),
                }
            )
    # 同一个 key 只留一条（后出现的覆盖前面的）
    dedup: dict[str, dict[str, Any]] = {}
    for item in out:
        dedup[item["key"]] = item
    return list(dedup.values())


STOPWORD_RUNS = {"回忆", "找一下", "查一下", "还记得", "上次", "那个", "帮我", "什么", "怎么", "为什么", "记一下"}


def _unknown_phrase(text: str, curated_terms: set[str]) -> str:
    best = ""
    for run in CJK_RUN.findall(text):
        if len(run) < 3 or run in STOPWORD_RUNS:
            continue
        grams = [run[i : i + 2] for i in range(len(run) - 1)]
        if not any(g in curated_terms for g in grams) and len(run) > len(best):
            best = run
    return best[:12]


def unused_skills(usage: dict[str, dict[str, Any]], all_skills: Iterable[str], *, days: float = 45.0) -> list[str]:
    stale: list[str] = []
    for name in all_skills:
        slot = usage.get(name)
        if slot is None:
            stale.append(name)
            continue
        last = str(slot.get("last") or "")
        if last and days_between(last) > days:
            stale.append(name)
    return stale
