"""测试公共设施：每个用例一套独立的记忆库 + 技能目录。

为什么不用 setUpClass 共享：记忆是会互相影响的。一个用例写了三条 AR，
另一个用例的"工作流重复 3 次"就会被误判成立——这种测试会先绿后红，
而且红的时候没人知道是代码坏了还是顺序变了。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in os.sys.path:  # 允许从任意目录运行
    os.sys.path.insert(0, str(ROOT))

from brain.app import App  # noqa: E402
from brain.config import Config  # noqa: E402


class BrainCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="brain-test-"))
        self.home = self._tmp / "memory"
        self.skills_dir = self._tmp / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        for child in (ROOT / "skills").iterdir():
            if child.is_dir() and not child.name.startswith("_") and (child / "SKILL.md").is_file():
                shutil.copytree(child, self.skills_dir / child.name)

        self._old_env = {k: os.environ.get(k) for k in ("BRAIN_HOME", "BRAIN_SKILLS", "BRAIN_PROVIDER", "BRAIN_NO_WRITE")}
        os.environ["BRAIN_HOME"] = str(self.home)
        os.environ["BRAIN_SKILLS"] = str(self.skills_dir)
        os.environ["BRAIN_PROVIDER"] = "offline"
        os.environ.pop("BRAIN_NO_WRITE", None)

        self.config = Config.load(ROOT)
        self.app = App(self.config)

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)

    # -- 便捷 ----------------------------------------------------------
    def fresh_app(self) -> App:
        """模拟"关掉进程再打开"：重新读盘，验证持久化。"""

        return App(Config.load(ROOT))
