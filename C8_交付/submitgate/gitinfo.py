"""git 信息：只取一个事实 —— 某个交付目录最后一次提交是什么时候。

「按时交付」这一条只能用版本历史来验证，不能用文件修改时间：
``git clone`` 会把所有文件的 mtime 重置成克隆时间，据此判断会全部误判。
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

_GIT_TIMEOUT = 20


def git_available() -> bool:
    return shutil.which("git") is not None


def _run(args: list[str], cwd: Path) -> str | None:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def last_commit_datetime(repo_root: Path, rel_path: str) -> datetime | None:
    """返回该路径最后一次提交时间（ISO 8601）；无 git / 无历史 / 出错时返回 None。"""

    if not git_available():
        return None
    raw = _run(["git", "-C", str(repo_root), "log", "-1", "--format=%cI", "--", rel_path], Path(repo_root))
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def short_head(repo_root: Path) -> str | None:
    if not git_available():
        return None
    return _run(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"], Path(repo_root))
