"""交付目录的文件枚举与交付物解析。

只做「看到了哪些文件」这一层事实，不做质量判断。
排除目录是显式的：``.git`` / ``__pycache__`` / ``node_modules`` / 虚拟环境，
否则一次检查会把几万个无关文件算进交付量。
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .challenge import Deliverable

EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".idea",
        ".vscode",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
        "dist",
        "build",
        ".next",
    }
)

_MAX_FILES = 20_000


@dataclass(frozen=True)
class FileEntry:
    rel: str  # 相对交付目录、POSIX 风格
    size: int

    @property
    def name(self) -> str:
        return self.rel.rsplit("/", 1)[-1]


def normalize(text: str) -> str:
    """匹配用的归一化：全角转半角、大小写折叠、去掉空白（下划线保留）。"""

    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if not ch.isspace())


def iter_files(root: Path) -> list[FileEntry]:
    root = Path(root)
    files: list[FileEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            rel = path.relative_to(root).as_posix()
            files.append(FileEntry(rel=rel, size=size))
            if len(files) >= _MAX_FILES:
                return files
    return files


def match_deliverable(deliverable: Deliverable, files: list[FileEntry]) -> list[FileEntry]:
    """按平台写法匹配文件。

    星号写法匹配「相对路径包含」，因此 ``AI日志/AI使用日志.md`` 也能被 ``*AI日志*`` 认领；
    无星号写法只比对文件名，避免 ``README.md`` 被 ``docs/README.md`` 之外的路径误伤。
    """

    target = normalize(deliverable.name)
    hits: list[FileEntry] = []
    for entry in files:
        if deliverable.wildcard:
            if target in normalize(entry.rel):
                hits.append(entry)
        elif normalize(entry.name) == target:
            hits.append(entry)
    hits.sort(key=lambda item: (len(item.rel), item.rel))
    return hits
