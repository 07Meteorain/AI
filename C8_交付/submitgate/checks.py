"""把「必需交付物 + 评分维度 + 红旗项」翻译成一次可复跑的检查。

三层结构：

1. **交付物层**（客观）：平台写的每一条必需交付物，在交付目录里有没有对应文件、是不是空文件；
2. **维度层**（启发式）：每个维度先按 ``profiles`` 归到一类证据，再拆成若干可观察信号，
   每条信号给出权重、结论与证据文件；
3. **红旗层**（规则）：按 challenge.json 自带的三条红旗判定，命中即把对应维度封顶 ——
   照抄平台的惩罚逻辑，不做「加权平均把致命伤稀释掉」的事。

维度层永远是**估算**：它只说明「该有的证据在不在」，不说明「写得对不对」。
对无法从文件系统观察的维度（例如群内参与质量），本模块给出 ``unverified`` 而不是 0 分，
并在报告里把「可自动验证的维度数」单独列出来 —— 不假装能评不能评的东西。
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from . import textscan
from .challenge import Challenge, Deliverable, RubricDimension
from .gitinfo import last_commit_datetime
from .profiles import PROFILE_SPECS, EvidenceItem, profile_for
from .scan import FileEntry, iter_files, match_deliverable, normalize

DOC_SUFFIXES = (".md", ".markdown", ".txt", ".rst")
AI_LOG_HINTS = ("ai日志", "ai使用日志", "ai使用记录", "ailog", "ai log", "ai-日志")
ACCEPTANCE_HINTS = ("验收", "acceptance")
SUBMIT_NOTE_HINTS = ("提交说明", "交付说明", "submission", "提交清单")
README_HINTS = ("readme.md",)

_KEYWORD_STOP = frozenset(
    {
        "质量",
        "程度",
        "能力",
        "是否",
        "以及",
        "并且",
        "相关",
        "方面",
        "情况",
        "能够",
        "通过",
        "对于",
        "或者",
        "进行",
        "上的",
        "中的",
        "类",
    }
)


@dataclass
class CheckOutcome:
    id: str
    label: str
    dimension: str
    weight: float
    status: str  # pass / fail / unverified
    detail: str
    evidence: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "pass"


@dataclass
class DeliverableOutcome:
    deliverable: Deliverable
    hits: list[FileEntry]
    ok: bool
    note: str


@dataclass
class DimensionScore:
    id: str
    label: str
    max_points: int
    score: int
    capped: bool
    cap_reason: str
    pass_ratio: float
    covered: bool
    coverage_note: str


@dataclass
class FlagHit:
    id: str
    description: str
    dimension: str
    max_score: int
    detail: str


@dataclass
class AiMetrics:
    log: tuple[str, str] | None
    rounds: int
    distinct_rounds: int
    prompts: int
    failures: int
    length: int

    @property
    def has_iteration(self) -> bool:
        """「多轮迭代」的两种可观察写法：编号轮次，或多次 prompt + 多条失败记录。

        真实日志有的按「第 N 轮」编号，有的按阶段分节（C9 的中英双语日志就没有轮次），
        后者只要留下多次 prompt 原文与多次返工记录，同样算有迭代证据。
        """

        return self.rounds >= 3 or (self.prompts >= 2 and self.failures >= 2)


@dataclass
class ChallengeEvaluation:
    challenge: Challenge
    delivery_dir: Path | None
    files: list[FileEntry]
    deliverables: list[DeliverableOutcome]
    checks: list[CheckOutcome]
    dimensions: list[DimensionScore]
    flags: list[FlagHit]
    notes: list[str] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        return [item.deliverable.name for item in self.deliverables if not item.ok]

    @property
    def covered_dimensions(self) -> list[DimensionScore]:
        return [dim for dim in self.dimensions if dim.covered]

    @property
    def total_score(self) -> int:
        return sum(dim.score for dim in self.covered_dimensions)

    @property
    def max_score(self) -> int:
        return sum(dim.max_points for dim in self.covered_dimensions)

    @property
    def full_score(self) -> int:
        return sum(dim.max_points for dim in self.dimensions)

    @property
    def passed(self) -> bool:
        return not self.missing and not self.flags

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


class Docs:
    """交付目录里的文档文本索引（只索引文档后缀，避免读二进制）。"""

    def __init__(self, delivery_dir: Path, files: Sequence[FileEntry]) -> None:
        self._items: list[tuple[str, str]] = []
        for entry in files:
            if not entry.rel.casefold().endswith(DOC_SUFFIXES):
                continue
            if entry.size == 0 or entry.size > 1_500_000:
                continue
            text = textscan.read_text(Path(delivery_dir) / entry.rel)
            if text:
                self._items.append((entry.rel, text))

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def all_text(self) -> str:
        return "\n\n".join(text for _, text in self._items)

    def by_name(self, hints: Iterable[str]) -> list[tuple[str, str]]:
        folded_hints = [normalize(hint) for hint in hints]
        found = []
        for rel, text in self._items:
            name = normalize(rel.rsplit("/", 1)[-1])
            if any(hint in name for hint in folded_hints):
                found.append((rel, text))
        return found

    def first(self, hints: Iterable[str]) -> tuple[str, str] | None:
        items = self.by_name(hints)
        return items[0] if items else None


@dataclass
class _Ctx:
    challenge: Challenge
    delivery_dir: Path
    delivery_rel: str
    repo_root: Path | None
    files: list[FileEntry]
    docs: Docs

    def ev(self, rel: str) -> str:
        return f"{self.delivery_rel}/{rel}" if self.delivery_rel else rel

    def ev_many(self, rels: Iterable[str]) -> list[str]:
        return [self.ev(rel) for rel in rels]


def _pass(check_id: str, label: str, dim: str, weight: float, detail: str, evidence: Sequence[str] = ()) -> CheckOutcome:
    return CheckOutcome(check_id, label, dim, weight, "pass", detail, list(evidence)[:6])


def _fail(check_id: str, label: str, dim: str, weight: float, detail: str, evidence: Sequence[str] = ()) -> CheckOutcome:
    return CheckOutcome(check_id, label, dim, weight, "fail", detail, list(evidence)[:6])


def _skip(check_id: str, label: str, dim: str, weight: float, detail: str) -> CheckOutcome:
    return CheckOutcome(check_id, label, dim, weight, "unverified", detail, [])


def _resolve(deliverable: Deliverable, files: Sequence[FileEntry]) -> DeliverableOutcome:
    hits = match_deliverable(deliverable, list(files))
    nonempty = [item for item in hits if item.size > 0]
    if not hits:
        return DeliverableOutcome(deliverable, [], False, "未找到匹配文件")
    if not nonempty:
        return DeliverableOutcome(deliverable, hits, False, f"命中 {len(hits)} 个文件，但全部为 0 字节")
    return DeliverableOutcome(deliverable, nonempty, True, f"命中 {len(nonempty)} 个文件")


# ---------------------------------------------------------------- 交付物 / 交付卫生


def _artifact_checks(ctx: _Ctx, dim_id: str, outcomes: Sequence[DeliverableOutcome], *, hygiene: bool) -> list[CheckOutcome]:
    checks: list[CheckOutcome] = []
    for outcome in outcomes:
        check_id = f"req:{outcome.deliverable.name}"
        label = f"必需交付物：{outcome.deliverable.name}"
        evidence = ctx.ev_many(hit.rel for hit in outcome.hits[:4])
        if outcome.ok:
            checks.append(_pass(check_id, label, dim_id, 2.0, outcome.note, evidence))
        else:
            checks.append(_fail(check_id, label, dim_id, 2.0, outcome.note, evidence))

    readme = ctx.docs.first(README_HINTS)
    if readme is None:
        checks.append(_fail("readme", "README 存在", dim_id, 2.0, "交付根目录没有 README.md"))
    else:
        rel, text = readme
        length = len(text)
        checks.append(
            _pass("readme", "README 存在", dim_id, 2.0, f"{rel}（{length} 字符）", [ctx.ev(rel)])
            if length >= 400
            else _fail("readme", "README 存在", dim_id, 2.0, f"{rel} 只有 {length} 字符，不足以说明用法", [ctx.ev(rel)])
        )
        heading = textscan.find_heading(
            text, ("安装", "使用", "快速开始", "验证", "上手", "getting started", "usage", "quick start", "开发", "运行")
        )
        checks.append(
            _pass("readme_usage", "README 有安装/使用小节", dim_id, 1.0, f"小节：{heading}", [ctx.ev(rel)])
            if heading
            else _fail("readme_usage", "README 有安装/使用小节", dim_id, 1.0, "没找到安装/使用类小节标题", [ctx.ev(rel)])
        )

    entry_names = {
        "__main__.py",
        "pyproject.toml",
        "setup.py",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "Makefile",
        "main.py",
        "cli.py",
        "Cargo.toml",
        "go.mod",
    }
    entry_dirs = {"tests", "test", "__tests__", "spec"}
    runnable = [
        entry.rel
        for entry in ctx.files
        if entry.name in entry_names or entry_dirs & set(entry.rel.split("/")[:-1])
    ]
    checks.append(
        _pass("runnable", "有可运行入口", dim_id, 2.0, f"入口：{runnable[0]}", ctx.ev_many(runnable[:4]))
        if runnable
        else _fail("runnable", "有可运行入口", dim_id, 2.0, "没找到 tests/、入口脚本或依赖清单")
    )

    volume = sum(hit.size for outcome in outcomes for hit in outcome.hits)
    checks.append(
        _pass("volume", "必需交付物总体量", dim_id, 1.0, f"共 {volume} 字节")
        if volume >= 4096
        else _fail("volume", "必需交付物总体量", dim_id, 1.0, f"仅 {volume} 字节，疑似占位")
    )

    if hygiene:
        checks.extend(_hygiene_checks(ctx, dim_id, scale=0.5))
    return checks


def _hygiene_checks(ctx: _Ctx, dim_id: str, *, scale: float = 1.0) -> list[CheckOutcome]:
    checks: list[CheckOutcome] = []
    acceptance = sorted({entry.rel for entry in ctx.files if any(hint in entry.rel.casefold() for hint in ACCEPTANCE_HINTS)})
    checks.append(
        _pass("acceptance", "有验收记录", dim_id, 3.0 * scale, f"验收文件：{acceptance[0]}", ctx.ev_many(acceptance[:4]))
        if acceptance
        else _fail("acceptance", "有验收记录", dim_id, 3.0 * scale, "没有 验收/acceptance 命名的文件或目录")
    )

    note = ctx.docs.first(SUBMIT_NOTE_HINTS)
    checks.append(
        _pass("submit_note", "有提交说明", dim_id, 2.0 * scale, f"{note[0]}", [ctx.ev(note[0])])
        if note
        else _fail("submit_note", "有提交说明", dim_id, 2.0 * scale, "没有 提交说明/交付说明")
    )

    deadline = ctx.challenge.deadline_dt
    if ctx.repo_root is None or deadline is None:
        checks.append(_skip("on_time", "按时交付", dim_id, 2.0 * scale, "缺少 git 历史或截止时间，无法验证"))
    else:
        committed = last_commit_datetime(Path(ctx.repo_root), ctx.delivery_rel)
        if committed is None:
            checks.append(_skip("on_time", "按时交付", dim_id, 2.0 * scale, "git 不可用或无提交历史"))
        elif committed <= deadline:
            checks.append(
                _pass(
                    "on_time",
                    "按时交付",
                    dim_id,
                    2.0 * scale,
                    f"最后提交 {committed:%Y-%m-%d %H:%M} ≤ 截止 {deadline:%Y-%m-%d %H:%M}",
                )
            )
        else:
            checks.append(
                _fail(
                    "on_time",
                    "按时交付",
                    dim_id,
                    2.0 * scale,
                    f"最后提交 {committed:%Y-%m-%d %H:%M} 晚于截止 {deadline:%Y-%m-%d %H:%M}",
                )
            )
    return checks


def _delivery_checks(ctx: _Ctx, dim_id: str, outcomes: Sequence[DeliverableOutcome]) -> list[CheckOutcome]:
    checks: list[CheckOutcome] = []
    missing = [outcome.deliverable.name for outcome in outcomes if not outcome.ok]
    if missing:
        checks.append(_fail("req_all", "必需交付物齐全", dim_id, 4.0, "缺：" + "、".join(missing)))
    else:
        checks.append(_pass("req_all", "必需交付物齐全", dim_id, 4.0, f"{len(outcomes)} 项全部命中"))
    checks.extend(_hygiene_checks(ctx, dim_id))
    return checks


# ---------------------------------------------------------------- 问题解决


def _problem_checks(ctx: _Ctx, dim_id: str) -> list[CheckOutcome]:
    checks: list[CheckOutcome] = []
    evidence: list[str] = []
    for entry in ctx.files:
        head = entry.rel.split("/")[0].casefold()
        if head in {"tests", "test", "demo", "证据", "验证", "截图"}:
            evidence.append(entry.rel)
        elif any(hint in entry.name.casefold() for hint in ("测试结果", "验证报告", "证据", "test_output", "测试输出")):
            evidence.append(entry.rel)
    evidence = sorted(set(evidence), key=lambda rel: (len(rel), rel))
    checks.append(
        _pass("evidence", "验证证据（测试/演示/证据）", dim_id, 4.0, f"共 {len(evidence)} 个证据文件", ctx.ev_many(evidence[:5]))
        if evidence
        else _fail("evidence", "验证证据（测试/演示/证据）", dim_id, 4.0, "没有 tests/、demo/ 或证据类文件")
    )

    readme = ctx.docs.first(README_HINTS)
    if readme and textscan.has_command_block(readme[1]):
        checks.append(_pass("repro", "README 含可复现命令", dim_id, 3.0, "README 代码块里有可执行命令", [ctx.ev(readme[0])]))
    elif readme:
        checks.append(_fail("repro", "README 含可复现命令", dim_id, 3.0, "README 没有可复制的命令块", [ctx.ev(readme[0])]))
    else:
        checks.append(_fail("repro", "README 含可复现命令", dim_id, 3.0, "没有 README"))

    text = ctx.docs.all_text()
    located = textscan.count_keyword_hits(text, ("根因", "定位", "原因"))
    fixed = textscan.count_keyword_hits(text, ("修复", "解决", "修正", "改成"))
    if located >= 1 and fixed >= 1:
        checks.append(_pass("root_cause", "记录了问题定位与修复", dim_id, 3.0, f"命中 定位类 {located} / 修复类 {fixed}"))
    else:
        checks.append(_fail("root_cause", "记录了问题定位与修复", dim_id, 3.0, f"命中 定位类 {located} / 修复类 {fixed}"))
    return checks


# ---------------------------------------------------------------- AI 使用


def _ai_metrics(docs: Docs) -> AiMetrics:
    log = docs.first(AI_LOG_HINTS)
    if log is None:
        return AiMetrics(None, 0, 0, 0, 0, 0)
    rel, text = log
    rounds, distinct = textscan.round_metrics(text)
    prompts = max(textscan.count_fences(text), textscan.count_quote_blocks(text))
    failures = textscan.count_keyword_hits(
        text,
        ("失败", "出错", "翻车", "返工", "纠正", "返修", "踩坑", "bug", "fail", "wrong", "rework"),
    )
    return AiMetrics(
        log=(rel, text),
        rounds=rounds,
        distinct_rounds=distinct,
        prompts=prompts,
        failures=failures,
        length=len(text),
    )


def _ai_checks(ctx: _Ctx, dim_id: str, metrics: AiMetrics) -> list[CheckOutcome]:
    if metrics.log is None:
        return [
            _fail("ai_log", "AI 日志存在", dim_id, 3.0, "没有 AI日志/使用记录 命名的文档"),
            _fail("ai_rounds", "AI 日志有迭代轮次", dim_id, 4.0, "无日志"),
            _fail("ai_prompts", "AI 日志含 prompt 原文", dim_id, 3.0, "无日志"),
            _fail("ai_failures", "AI 日志含失败/返工记录", dim_id, 3.0, "无日志"),
            _fail("ai_volume", "AI 日志体量", dim_id, 2.0, "无日志"),
        ]

    rel = metrics.log[0]
    ev = [ctx.ev(rel)]
    checks = [_pass("ai_log", "AI 日志存在", dim_id, 3.0, f"{rel}（{metrics.length} 字符）", ev)]
    checks.append(
        _pass(
            "ai_rounds",
            "AI 日志有迭代证据",
            dim_id,
            4.0,
            f"轮次 {metrics.rounds}、prompt {metrics.prompts}、失败记录 {metrics.failures}",
            ev,
        )
        if metrics.has_iteration
        else _fail(
            "ai_rounds",
            "AI 日志有迭代证据",
            dim_id,
            4.0,
            f"轮次 {metrics.rounds}、prompt {metrics.prompts}、失败记录 {metrics.failures}（不足以说明多轮迭代）",
            ev,
        )
    )
    checks.append(
        _pass("ai_prompts", "AI 日志含 prompt 原文", dim_id, 3.0, f"{metrics.prompts} 个 prompt 片段（代码块/引用）", ev)
        if metrics.prompts >= 2
        else _fail("ai_prompts", "AI 日志含 prompt 原文", dim_id, 3.0, f"只有 {metrics.prompts} 个（要求 ≥2）", ev)
    )
    checks.append(
        _pass("ai_failures", "AI 日志含失败/返工记录", dim_id, 3.0, f"命中 {metrics.failures} 处", ev)
        if metrics.failures >= 1
        else _fail("ai_failures", "AI 日志含失败/返工记录", dim_id, 3.0, "没有失败/返工/纠正记录", ev)
    )
    checks.append(
        _pass("ai_volume", "AI 日志体量", dim_id, 2.0, f"{metrics.length} 字符", ev)
        if metrics.length >= 2000
        else _fail("ai_volume", "AI 日志体量", dim_id, 2.0, f"{metrics.length} 字符（要求 ≥2000）", ev)
    )
    return checks


# ---------------------------------------------------------------- 复盘


def _reflection_checks(ctx: _Ctx, dim_id: str) -> list[CheckOutcome]:
    aar = ctx.docs.first(("aar", "复盘", "反思"))
    if aar is None:
        return [
            _fail("aar", "AAR 复盘存在", dim_id, 4.0, "没有 AAR/复盘/反思 命名的文档"),
            _fail("aar_sections", "AAR 覆盖复盘要素", dim_id, 4.0, "无复盘文档"),
            _fail("aar_numbers", "AAR 含具体数字", dim_id, 2.0, "无复盘文档"),
            _fail("aar_failures", "AAR 有失败经验小节", dim_id, 2.0, "无复盘文档"),
            _fail("aar_actions", "AAR 有改进方案", dim_id, 3.0, "无复盘文档"),
        ]

    rel, text = aar
    ev = [ctx.ev(rel)]
    checks = [_pass("aar", "AAR 复盘存在", dim_id, 4.0, f"{rel}（{len(text)} 字符）", ev)]
    elements = textscan.count_keyword_hits(text, ("预期", "实际", "做对", "失败", "改进", "教训", "根因"))
    checks.append(
        _pass("aar_sections", "AAR 覆盖复盘要素", dim_id, 4.0, f"覆盖 {elements}/7 类要素", ev)
        if elements >= 3
        else _fail("aar_sections", "AAR 覆盖复盘要素", dim_id, 4.0, f"只覆盖 {elements}/7 类要素", ev)
    )
    numbers = textscan.count_distinct_numbers(text)
    checks.append(
        _pass("aar_numbers", "AAR 含具体数字", dim_id, 2.0, f"{numbers} 个不同数字", ev)
        if numbers >= 3
        else _fail("aar_numbers", "AAR 含具体数字", dim_id, 2.0, f"只有 {numbers} 个不同数字", ev)
    )
    failure_heading = textscan.find_heading(
        text, ("失败", "教训", "没做成", "翻车", "做错", "没达到", "未达", "踩坑", "fail", "lesson", "went wrong")
    )
    checks.append(
        _pass("aar_failures", "AAR 有失败经验小节", dim_id, 2.0, f"小节：{failure_heading}", ev)
        if failure_heading
        else _fail("aar_failures", "AAR 有失败经验小节", dim_id, 2.0, "没有失败/教训类小节", ev)
    )
    action_heading = textscan.find_heading(
        text, ("改进", "下一步", "行动", "以后", "重来", "清单", "计划", "下次", "next", "improve", "action", "plan")
    )
    actionable = textscan.has_command_block(text) or ("\n- " in text or "\n1. " in text)
    if action_heading and actionable:
        checks.append(_pass("aar_actions", "AAR 有改进方案", dim_id, 3.0, f"小节：{action_heading}", ev))
    elif action_heading:
        checks.append(_fail("aar_actions", "AAR 有改进方案", dim_id, 3.0, f"有「{action_heading}」小节但没有具体动作", ev))
    else:
        checks.append(_fail("aar_actions", "AAR 有改进方案", dim_id, 3.0, "没有改进/下一步小节", ev))
    return checks


# ---------------------------------------------------------------- 目录证据类


def _match_globs(files: Sequence[FileEntry], patterns: Sequence[str]) -> list[str]:
    folded = [pattern.casefold() for pattern in patterns]
    hits = []
    for entry in files:
        rel = entry.rel.casefold()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in folded):
            hits.append(entry.rel)
    return sorted(set(hits), key=lambda rel: (len(rel), rel))


def _repo_workflows(ctx: _Ctx) -> list[str]:
    """仓库根 ``.github/workflows/`` 里与本挑战同名的 workflow（GitHub 只认仓库根）。"""

    if ctx.repo_root is None:
        return []
    directory = Path(ctx.repo_root) / ".github" / "workflows"
    if not directory.is_dir():
        return []
    prefix = ctx.challenge.source_id.casefold()
    return [
        f".github/workflows/{path.name}"
        for path in sorted(directory.glob("*.yml"))
        if prefix in path.name.casefold()
    ]


def _spec_checks(ctx: _Ctx, dim_id: str, profile: str) -> list[CheckOutcome]:
    checks: list[CheckOutcome] = []
    for item in PROFILE_SPECS[profile]:
        hits = _match_globs(ctx.files, item.patterns)
        if not hits and "CI" in item.label:
            hits = _repo_workflows(ctx)
            if hits:
                checks.append(
                    _pass(
                        f"spec:{profile}:{item.label}",
                        f"{profile}：{item.label}",
                        dim_id,
                        1.0,
                        f"仓库根有：{hits[0]}",
                        hits[:4],
                    )
                )
                continue
        if hits:
            checks.append(
                _pass(
                    f"spec:{profile}:{item.label}",
                    f"{profile}：{item.label}",
                    dim_id,
                    1.0,
                    f"命中 {len(hits)} 个：{hits[0]}",
                    ctx.ev_many(hits[:4]),
                )
            )
        else:
            checks.append(
                _fail(f"spec:{profile}:{item.label}", f"{profile}：{item.label}", dim_id, 1.0, "未找到对应文件")
            )
    return checks


def _keywords(text: str) -> set[str]:
    """从维度标签/描述里抽关键词：英文单词 + 中文二元组，去掉泛词。"""

    keywords: set[str] = set()
    for chunk in re.findall(r"[\u4e00-\u9fff]+|[A-Za-z]{3,}", text):
        if re.match(r"[A-Za-z]", chunk):
            keywords.add(chunk.casefold())
            continue
        if len(chunk) <= 4:
            keywords.add(chunk)
        for index in range(len(chunk) - 1):
            keywords.add(chunk[index : index + 2])
    return {word for word in keywords if word not in _KEYWORD_STOP and len(word) >= 2}


def _docs_checks(ctx: _Ctx, dim: RubricDimension, dim_id: str) -> list[CheckOutcome]:
    keywords = _keywords(f"{dim.label} {dim.description}")

    # 证据必须「点名」到这个维度：文件名含关键词，或标题里至少命中两个关键词。
    # 只用「任意文档里出现过关键词」会把参与质量判给一篇恰好提到「参与」的复盘文档 —— 这是第二版的误报来源。
    by_name: list[tuple[str, str]] = []
    by_heading: list[tuple[str, str]] = []
    for rel, text in ctx.docs:
        name = rel.rsplit("/", 1)[-1].casefold()
        heading_text = " ".join(title for _, title in textscan.headings(text)).casefold()
        if any(keyword in name for keyword in keywords):
            by_name.append((rel, text))
        elif sum(1 for keyword in keywords if keyword in heading_text) >= 2:
            by_heading.append((rel, text))

    candidates = by_name or by_heading
    if not candidates:
        return [
            _skip("docs_evidence", f"{dim.label}：相关文档", dim_id, 1.0, "交付目录里没有可自动核对的证据，需人工判断"),
            _skip("docs_substance", f"{dim.label}：文档有实际内容", dim_id, 2.0, "同上"),
        ]

    rel, text = max(candidates, key=lambda item: len(item[1]))
    length = len(text)
    marks = textscan.template_marks(text)
    rows = textscan.table_rows(text)
    checks = [_pass("docs_evidence", f"{dim.label}：相关文档", dim_id, 1.0, f"{rel}（{length} 字符）", [ctx.ev(rel)])]
    substantive = length >= 800 and marks <= 1 and (rows >= 3 or length >= 1500)
    detail = f"{length} 字符 / 模板痕迹 {marks} 处 / 表格 {rows} 行"
    checks.append(
        _pass("docs_substance", f"{dim.label}：文档有实际内容", dim_id, 2.0, detail, [ctx.ev(rel)])
        if substantive
        else _fail("docs_substance", f"{dim.label}：文档有实际内容", dim_id, 2.0, detail + "（疑似模板）", [ctx.ev(rel)])
    )
    return checks


# ---------------------------------------------------------------- 红旗与计分


def _evaluate_flags(
    challenge: Challenge,
    outcomes: Sequence[DeliverableOutcome],
    metrics: AiMetrics,
) -> list[FlagHit]:
    hits: list[FlagHit] = []
    for flag in challenge.red_flags:
        if flag.id == "missing_artifacts":
            missing = [item.deliverable.name for item in outcomes if not item.ok]
            if missing:
                hits.append(FlagHit(flag.id, flag.description, flag.dimension, flag.max_score, "缺失/为空：" + "、".join(missing)))
        elif flag.id == "no_ai_log":
            if metrics.log is None:
                hits.append(FlagHit(flag.id, flag.description, flag.dimension, flag.max_score, "没有任何 AI 使用记录"))
        elif flag.id == "one_shot_ai":
            if metrics.log is not None and (not metrics.has_iteration or metrics.prompts < 2):
                hits.append(
                    FlagHit(
                        flag.id,
                        flag.description,
                        flag.dimension,
                        flag.max_score,
                        f"轮次={metrics.rounds}、prompt 片段={metrics.prompts}、失败记录={metrics.failures}",
                    )
                )
    return hits


def _score_dimensions(
    challenge: Challenge,
    checks: Sequence[CheckOutcome],
    flags: Sequence[FlagHit],
) -> list[DimensionScore]:
    scores: list[DimensionScore] = []
    for dim in challenge.dimensions:
        relevant = [check for check in checks if check.dimension == dim.id]
        scored = [check for check in relevant if check.status != "unverified"]
        covered = bool(scored)
        total_weight = sum(check.weight for check in scored)
        got = sum(check.weight for check in scored if check.ok)
        ratio = (got / total_weight) if total_weight else 0.0
        score = int(dim.max_points * ratio + 0.5) if covered else 0
        capped = False
        cap_reason = ""
        if covered:
            for flag in flags:
                if flag.dimension == dim.id and score > flag.max_score:
                    score = flag.max_score
                    capped = True
                    cap_reason = f"红旗 {flag.id} 触发：{flag.description}，封顶 {flag.max_score}"
        scores.append(
            DimensionScore(
                id=dim.id,
                label=dim.label,
                max_points=dim.max_points,
                score=score,
                capped=capped,
                cap_reason=cap_reason,
                pass_ratio=ratio,
                covered=covered,
                coverage_note="" if covered else "交付目录里没有可核对的证据，需人工判断",
            )
        )
    return scores


def _empty_evaluation(challenge: Challenge, note: str) -> ChallengeEvaluation:
    outcomes = [
        DeliverableOutcome(deliverable, [], False, "没有找到对应交付目录")
        for deliverable in challenge.deliverables
    ]
    metrics = AiMetrics(None, 0, 0, 0, 0, 0)
    flags = _evaluate_flags(challenge, outcomes, metrics)
    return ChallengeEvaluation(
        challenge=challenge,
        delivery_dir=None,
        files=[],
        deliverables=outcomes,
        checks=[],
        dimensions=_score_dimensions(challenge, [], flags),
        flags=flags,
        notes=[note],
    )


def evaluate_challenge(
    challenge: Challenge,
    delivery_dir: Path | None,
    *,
    repo_root: Path | None = None,
) -> ChallengeEvaluation:
    if delivery_dir is None or not Path(delivery_dir).is_dir():
        return _empty_evaluation(challenge, "仓库里没有与该挑战编号对应的交付目录")

    delivery_dir = Path(delivery_dir)
    repo_root = Path(repo_root) if repo_root is not None else None
    if repo_root is not None:
        try:
            delivery_rel = delivery_dir.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            delivery_rel = delivery_dir.name
    else:
        delivery_rel = ""

    files = iter_files(delivery_dir)
    docs = Docs(delivery_dir, files)
    ctx = _Ctx(
        challenge=challenge,
        delivery_dir=delivery_dir,
        delivery_rel=delivery_rel,
        repo_root=repo_root,
        files=files,
        docs=docs,
    )
    outcomes = [_resolve(deliverable, files) for deliverable in challenge.deliverables]
    metrics = _ai_metrics(docs)

    profiles = {dim.id: profile_for(dim) for dim in challenge.dimensions}
    has_delivery = "delivery" in profiles.values()

    checks: list[CheckOutcome] = []
    for dim in challenge.dimensions:
        profile = profiles[dim.id]
        if profile == "artifact":
            checks.extend(_artifact_checks(ctx, dim.id, outcomes, hygiene=not has_delivery))
        elif profile == "delivery":
            checks.extend(_delivery_checks(ctx, dim.id, outcomes))
        elif profile == "problem":
            checks.extend(_problem_checks(ctx, dim.id))
        elif profile == "ai":
            checks.extend(_ai_checks(ctx, dim.id, metrics))
        elif profile == "reflection":
            checks.extend(_reflection_checks(ctx, dim.id))
        elif profile in PROFILE_SPECS:
            checks.extend(_spec_checks(ctx, dim.id, profile))
        else:
            checks.extend(_docs_checks(ctx, dim, dim.id))

    flags = _evaluate_flags(challenge, outcomes, metrics)
    dimensions = _score_dimensions(challenge, checks, flags)

    notes: list[str] = []
    uncovered = [dim.label for dim in dimensions if not dim.covered]
    if uncovered:
        notes.append("无法自动验证的维度（需人工）：" + "、".join(uncovered))

    return ChallengeEvaluation(
        challenge=challenge,
        delivery_dir=delivery_dir,
        files=files,
        deliverables=outcomes,
        checks=checks,
        dimensions=dimensions,
        flags=flags,
        notes=notes,
    )
