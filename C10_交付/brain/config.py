"""路径与运行参数。

设计取舍：**所有路径都由 ``Config`` 算出来，不用模块级全局变量**。

原因很实际——测试需要把记忆库指到临时目录，否则一次 ``unittest`` 会把
真实记忆写脏。用环境变量 ``BRAIN_HOME`` 覆盖即可，不需要 monkeypatch 模块。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    """一次运行需要的全部路径与开关。"""

    root: Path
    home: Path
    skills_dir: Path
    traces_dir: Path
    drafts_dir: Path

    # 循环参数
    max_steps: int = 8
    max_budget: int = 12000  # 步数预算（粗略，不是 token 数）

    # 记忆参数
    default_top_k: int = 5
    half_life_days: float = 30.0

    # 行为开关
    write_memory: bool = True
    verbose: bool = False
    llm_provider: str = "offline"
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | Path | None = None) -> "Config":
        if root is None:
            root = Path(__file__).resolve().parents[1]
        root = Path(root).resolve()

        home = Path(os.environ.get("BRAIN_HOME") or (root / "memory")).resolve()
        skills_dir = Path(os.environ.get("BRAIN_SKILLS") or (root / "skills")).resolve()

        return cls(
            root=root,
            home=home,
            skills_dir=skills_dir,
            traces_dir=home / "db" / "traces",
            drafts_dir=skills_dir / "_drafts",
            max_steps=int(os.environ.get("BRAIN_MAX_STEPS") or 8),
            default_top_k=int(os.environ.get("BRAIN_TOP_K") or 5),
            write_memory=not _bool_env("BRAIN_NO_WRITE", False),
            verbose=_bool_env("BRAIN_VERBOSE", False),
            llm_provider=os.environ.get("BRAIN_PROVIDER", "offline"),
        )

    # -- 目录 ----------------------------------------------------------
    @property
    def db_dir(self) -> Path:
        return self.home / "db"

    @property
    def knowledge_dir(self) -> Path:
        return self.home / "knowledge"

    @property
    def aliases_path(self) -> Path:
        return self.db_dir / "aliases.json"

    @property
    def evolution_log(self) -> Path:
        return self.db_dir / "evolution.jsonl"

    def ensure_dirs(self) -> None:
        for p in (self.home, self.db_dir, self.knowledge_dir, self.traces_dir, self.skills_dir):
            p.mkdir(parents=True, exist_ok=True)

    def rel(self, path: str | Path) -> str:
        """把绝对路径转成相对项目根的展示路径，方便写进 trace 与回执。"""
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except (ValueError, OSError):
            return str(path)
