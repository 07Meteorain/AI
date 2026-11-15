"""编排层：扫描课程记录 → 映射仓库目录 → 逐挑战评估 → 汇总成一份可序列化的报告。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__
from .challenge import Challenge, discover_course
from .checks import ChallengeEvaluation, evaluate_challenge
from .gitinfo import short_head
from .mapping import Mapping, build_mapping, load_aliases


class ToolError(RuntimeError):
    """可预期的使用错误（退出码 2），例如课程目录里没有 challenge.json。"""


@dataclass
class Report:
    generated_at: datetime
    course_root: Path
    repo_root: Path
    evaluations: list[ChallengeEvaluation]
    mapping: Mapping
    git_head: str | None = None
    tool_version: str = __version__

    @property
    def total(self) -> int:
        return len(self.evaluations)

    @property
    def passed(self) -> list[ChallengeEvaluation]:
        return [item for item in self.evaluations if item.passed]

    @property
    def failed(self) -> list[ChallengeEvaluation]:
        return [item for item in self.evaluations if not item.passed]

    @property
    def missing_delivery(self) -> list[ChallengeEvaluation]:
        return [item for item in self.evaluations if item.delivery_dir is None]

    @property
    def required_missing(self) -> int:
        return sum(len(item.missing) for item in self.evaluations)

    @property
    def required_total(self) -> int:
        return sum(len(item.deliverables) for item in self.evaluations)

    @property
    def flag_count(self) -> int:
        return sum(len(item.flags) for item in self.evaluations)

    @property
    def score(self) -> int:
        """只统计「可自动验证维度」的得分 —— 不可验证的维度不进入分子分母。"""

        return sum(item.total_score for item in self.evaluations)

    @property
    def max_score(self) -> int:
        return sum(item.max_score for item in self.evaluations)

    @property
    def full_score(self) -> int:
        """全部维度的满分之和（含不可自动验证的维度），用来对比覆盖面。"""

        return sum(item.full_score for item in self.evaluations)

    @property
    def covered_dimensions(self) -> int:
        return sum(len(item.covered_dimensions) for item in self.evaluations)

    @property
    def total_dimensions(self) -> int:
        return sum(len(item.dimensions) for item in self.evaluations)

    @property
    def gate_ok(self) -> bool:
        """门禁结论：所有挑战的必需交付物齐全、且无红旗。"""

        return all(item.passed for item in self.evaluations)


def run(course_root: Path, repo_root: Path, mapping_path: Path | None = None) -> Report:
    course_root = Path(course_root)
    repo_root = Path(repo_root)
    if not course_root.is_dir():
        raise ToolError(f"课程目录不存在：{course_root}")
    if not repo_root.is_dir():
        raise ToolError(f"仓库目录不存在：{repo_root}")

    challenges = discover_course(course_root)
    if not challenges:
        raise ToolError(f"课程目录里没有 challenge.json：{course_root}")

    aliases = load_aliases(mapping_path)
    mapping = build_mapping(challenges, repo_root, aliases)
    evaluations = [
        evaluate_challenge(challenge, mapping.get(challenge.source_id), repo_root=repo_root)
        for challenge in challenges
    ]
    return Report(
        generated_at=datetime.now(),
        course_root=course_root,
        repo_root=repo_root,
        evaluations=evaluations,
        mapping=mapping,
        git_head=short_head(repo_root),
    )
