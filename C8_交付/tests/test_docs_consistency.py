"""文档与代码的一致性：防止评分映射表与 profiles.py 漂移。"""

from __future__ import annotations

import unittest
from pathlib import Path

from submitgate.profiles import DIMENSION_PROFILES, PROFILE_SPECS

ROOT = Path(__file__).resolve().parent.parent


class DocsConsistencyTest(unittest.TestCase):
    def test_every_dimension_id_documented(self):
        text = (ROOT / "docs" / "评分映射.md").read_text(encoding="utf-8")
        missing = [dim_id for dim_id in DIMENSION_PROFILES if f"`{dim_id}`" not in text]
        self.assertEqual(missing, [], f"评分映射.md 缺少维度：{missing}")

    def test_every_profile_documented(self):
        text = (ROOT / "docs" / "评分映射.md").read_text(encoding="utf-8")
        for profile in PROFILE_SPECS:
            self.assertIn(f"`{profile}`", text, profile)

    def test_readme_lists_required_deliverables(self):
        """C8 自己的 4 条必需交付物必须在提交说明里逐条出现。"""
        import json

        record = json.loads((ROOT / "challenges" / "C8" / "challenge.json").read_text(encoding="utf-8"))
        names = [item.strip("* ") for item in record["required_deliverables"].split(",")]
        text = (ROOT / "提交说明.md").read_text(encoding="utf-8")
        for name in names:
            self.assertIn(name, text, f"提交说明.md 未提到必需交付物：{name}")

    def test_challenge_snapshots_are_real(self):
        snapshots = sorted((ROOT / "challenges").glob("*/challenge.json"))
        self.assertEqual(len(snapshots), 11)
        for path in snapshots:
            self.assertGreater(path.stat().st_size, 200, path)


if __name__ == "__main__":
    unittest.main()
