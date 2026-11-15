"""挑战记录（challenge.json）的解析层。

平台原始记录里的字段是「人写的半结构化文本」：
- ``required_deliverables`` 形如 ``*AI日志*,*AAR*,*反思*``，逗号分隔，星号表示模糊匹配；
- ``rubric_dimensions`` 是一段嵌套 JSON 字符串，含 5 个维度与各自分值；
- ``red_flags`` 同样是一段 JSON 字符串，含触发条件与封顶分值。

本模块只做一件事：把这三段文本变成可断言的数据结构，不做任何文件系统判断。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

_DEADLINE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)

_ID_SORT_RE = re.compile(r"^(C)(\d+)([A-Z]*)$", re.IGNORECASE)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


@dataclass(frozen=True)
class Deliverable:
    """一条必需交付物要求。

    ``wildcard=True`` 表示平台写成 ``*AI日志*``：按「路径包含该片段」匹配；
    ``wildcard=False`` 表示写成 ``README.md``：按「文件名完全相等」匹配。
    """

    raw: str
    name: str
    wildcard: bool

    def __str__(self) -> str:  # pragma: no cover - 仅用于报告排版
        return self.name


@dataclass(frozen=True)
class RubricDimension:
    id: str
    label: str
    description: str
    max_points: int


@dataclass(frozen=True)
class RedFlag:
    id: str
    description: str
    dimension: str
    max_score: int


@dataclass(frozen=True)
class Challenge:
    source_id: str
    challenge_id: str
    title: str
    brief: str
    objective: str
    deadline: str
    deliverables: tuple[Deliverable, ...]
    dimensions: tuple[RubricDimension, ...]
    red_flags: tuple[RedFlag, ...]
    record_path: Path

    @property
    def deadline_dt(self) -> datetime | None:
        return parse_deadline(self.deadline)

    @property
    def max_points(self) -> int:
        return sum(d.max_points for d in self.dimensions)

    def dimension(self, dim_id: str) -> RubricDimension | None:
        for dim in self.dimensions:
            if dim.id == dim_id:
                return dim
        return None

    @property
    def deliverable_names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.deliverables)


def parse_deliverables(text: str) -> tuple[Deliverable, ...]:
    """把 ``*AI日志*,*AAR*,*反思*`` 解析成结构化列表（容忍全角逗号与多余空格）。"""

    out: list[Deliverable] = []
    for chunk in re.split(r"[,，]", text or ""):
        item = chunk.strip().strip("`").strip()
        if not item:
            continue
        wildcard = item.startswith("*") and item.endswith("*")
        name = item.strip("*").strip()
        if not name:
            continue
        out.append(Deliverable(raw=item, name=name, wildcard=wildcard))
    return tuple(out)


def parse_deadline(text: str) -> datetime | None:
    value = (text or "").strip()
    if not value:
        return None
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _loads_maybe(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def parse_rubric(value: Any) -> tuple[RubricDimension, ...]:
    data = _loads_maybe(value) or {}
    dims: list[RubricDimension] = []
    for item in data.get("dimensions", []) or []:
        if not isinstance(item, dict):
            continue
        dim_id = _clean(item.get("id"))
        if not dim_id:
            continue
        try:
            points = int(item.get("maxPoints") or 0)
        except (TypeError, ValueError):
            points = 0
        dims.append(
            RubricDimension(
                id=dim_id,
                label=_clean(item.get("label")) or dim_id,
                description=_clean(item.get("description")),
                max_points=points,
            )
        )
    return tuple(dims)


def parse_red_flags(value: Any) -> tuple[RedFlag, ...]:
    data = _loads_maybe(value) or {}
    flags: list[RedFlag] = []
    for item in data.get("flags", []) or []:
        if not isinstance(item, dict):
            continue
        flag_id = _clean(item.get("id"))
        if not flag_id:
            continue
        try:
            cap = int(item.get("maxScore") or 0)
        except (TypeError, ValueError):
            cap = 0
        flags.append(
            RedFlag(
                id=flag_id,
                description=_clean(item.get("description")),
                dimension=_clean(item.get("affectedDimension")),
                max_score=cap,
            )
        )
    return tuple(flags)


def load_challenge(record_path: Path) -> Challenge:
    """读取一份 ``challenge.json``。缺失字段按空值处理，不抛异常。"""

    data = json.loads(Path(record_path).read_text(encoding="utf-8"))
    deliverables_text = data.get("required_deliverables") or data.get("deliverables") or ""
    source_id = _clean(data.get("source_id"))
    if not source_id:
        # 目录名兜底：challenges/C3/challenge.json -> C3
        source_id = Path(record_path).resolve().parent.name
    return Challenge(
        source_id=source_id,
        challenge_id=_clean(data.get("challenge_id")),
        title=_clean(data.get("title")),
        brief=_clean(data.get("brief")),
        objective=_clean(data.get("objective")),
        deadline=_clean(data.get("deadline")),
        deliverables=parse_deliverables(str(deliverables_text)),
        dimensions=parse_rubric(data.get("rubric_dimensions")),
        red_flags=parse_red_flags(data.get("red_flags")),
        record_path=Path(record_path),
    )


def challenge_sort_key(source_id: str) -> tuple[int, str]:
    """``C8`` 排在 ``C10`` 之前，``C3`` 排在 ``C3C`` 之前。"""

    match = _ID_SORT_RE.match(source_id.strip())
    if not match:
        return (10_000, source_id.upper())
    return (int(match.group(2)), match.group(3).upper())


def discover_course(course_root: Path) -> list[Challenge]:
    """扫描课程根目录：``<root>/<Cx>/challenge.json``（也允许根本身就是一条记录）。"""

    root = Path(course_root)
    records: list[Path] = []
    direct = root / "challenge.json"
    if direct.is_file():
        records.append(direct)
    for child in sorted(root.iterdir() if root.is_dir() else [], key=lambda p: p.name):
        candidate = child / "challenge.json"
        if child.is_dir() and candidate.is_file():
            records.append(candidate)
    challenges = [load_challenge(path) for path in records]
    return sorted(challenges, key=lambda ch: challenge_sort_key(ch.source_id))
