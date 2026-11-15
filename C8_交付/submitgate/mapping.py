"""挑战记录 → 仓库交付目录的映射。

真实仓库里的目录名并不总是 ``Cx_交付``：

- ``C3C_交付`` vs ``C3_交付``：前缀必须按「``C`` + 数字 + 字母后缀」整体匹配，
  否则 C3 会把 C3C 认成自己；
- ``C5A_仓库分析`` / ``C4B_公众号文章生成技能``：后缀是中文，不能靠 ``_交付`` 判断；
- ``C9`` 的交付物实际放在 ``C2A_C9_交付``：这是人工约定，必须允许用
  ``mapping.json`` 声明别名，而不是把某一次的特例写死在代码里。

映射结果分三类：已匹配、有歧义（同前缀多目录）、孤立目录（仓库里有、课程里没有记录）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .challenge import Challenge

_FOLDER_ID_RE = re.compile(r"^(C\d+[A-Z]*)", re.IGNORECASE)
_SKIP_DIRS = frozenset({".git", ".github", ".idea", ".vscode"})


def folder_id(name: str) -> str | None:
    """从目录名提取挑战编号：``C3C_交付`` → ``C3C``，``C2A_C9_交付`` → ``C2A``。"""

    match = _FOLDER_ID_RE.match(name.strip())
    return match.group(1).upper() if match else None


def discover_dirs(repo_root: Path) -> list[Path]:
    root = Path(repo_root)
    if not root.is_dir():
        return []
    dirs = [
        child
        for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(".") and child.name not in _SKIP_DIRS
    ]
    return sorted(dirs, key=lambda p: p.name)


def load_aliases(mapping_path: Path | None) -> dict[str, str]:
    """读取 ``mapping.json``：``{"aliases": {"C9": "C2A_C9_交付"}}``。"""

    if not mapping_path:
        return {}
    path = Path(mapping_path)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    aliases = data.get("aliases", {}) if isinstance(data, dict) else {}
    return {str(k).upper(): str(v) for k, v in aliases.items()}


@dataclass
class Mapping:
    entries: dict[str, Path | None] = field(default_factory=dict)
    ambiguous: dict[str, list[Path]] = field(default_factory=dict)
    orphans: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    aliased: dict[str, str] = field(default_factory=dict)

    def get(self, source_id: str) -> Path | None:
        return self.entries.get(source_id.upper())


def build_mapping(
    challenges: list[Challenge],
    repo_root: Path,
    aliases: dict[str, str] | None = None,
) -> Mapping:
    root = Path(repo_root)
    aliases = {k.upper(): v for k, v in (aliases or {}).items()}
    dirs = discover_dirs(root)

    by_id: dict[str, list[Path]] = {}
    for path in dirs:
        ident = folder_id(path.name)
        if ident:
            by_id.setdefault(ident, []).append(path)

    mapping = Mapping()
    used_names: set[str] = set()
    challenge_ids = {ch.source_id.upper() for ch in challenges}

    for challenge in challenges:
        source_id = challenge.source_id.upper()
        alias = aliases.get(source_id)
        candidates = by_id.get(source_id, [])

        # 真实目录优先于别名：C9 曾经只能映射到 C2A_C9_交付/，但仓库后来补了 C9_交付/。
        # 若让别名抢先，新补的交付会被静默忽略 —— 这是交付期间真实发生过的一次误判。
        if candidates:
            if len(candidates) == 1:
                mapping.entries[source_id] = candidates[0]
                used_names.add(candidates[0].name)
            else:
                mapping.entries[source_id] = candidates[0]
                mapping.ambiguous[source_id] = candidates
                used_names.add(candidates[0].name)
                names = "、".join(p.name for p in candidates)
                mapping.notes.append(f"{source_id} 命中多个目录（{names}），暂取 {candidates[0].name}/")
            if alias:
                note = f"{source_id} 存在同名目录 {candidates[0].name}/，忽略 mapping.json 里的别名 {alias}/"
                mapping.notes.append(note)
            continue

        if alias:
            target = root / alias
            if target.is_dir():
                mapping.entries[source_id] = target
                mapping.aliased[source_id] = alias
                used_names.add(alias)
                mapping.notes.append(f"{source_id} 按 mapping.json 声明映射到 {alias}/")
            else:
                mapping.entries[source_id] = None
                mapping.notes.append(f"{source_id} 声明的别名 {alias}/ 不存在")
            continue

        mapping.entries[source_id] = None

    mapping.orphans = [
        path
        for path in dirs
        if path.name not in used_names
        and (folder_id(path.name) or "") not in challenge_ids
        and folder_id(path.name) is not None
    ]
    return mapping
