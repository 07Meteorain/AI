"""profiles.py：维度 → 证据类别。"""

from __future__ import annotations

import unittest

from submitgate.challenge import RubricDimension
from submitgate.profiles import DIMENSION_PROFILES, PROFILE_SPECS, profile_for

SPECIAL = {"artifact", "delivery", "problem", "ai", "reflection", "docs"}


def dim(dim_id: str, label: str = "", description: str = "") -> RubricDimension:
    return RubricDimension(id=dim_id, label=label, description=description, max_points=10)


class ProfileForTest(unittest.TestCase):
    def test_known_ids(self):
        self.assertEqual(profile_for(dim("artifactCompleteness")), "artifact")
        self.assertEqual(profile_for(dim("aiUsage")), "ai")
        self.assertEqual(profile_for(dim("reflectionQuality")), "reflection")
        self.assertEqual(profile_for(dim("delivery")), "delivery")
        self.assertEqual(profile_for(dim("problemSolving")), "problem")
        self.assertEqual(profile_for(dim("repoQuality")), "repo")
        self.assertEqual(profile_for(dim("community")), "community")
        self.assertEqual(profile_for(dim("technicalExecution")), "engineering")
        self.assertEqual(profile_for(dim("productQuality")), "product")
        self.assertEqual(profile_for(dim("dataInsight")), "data")
        self.assertEqual(profile_for(dim("contentQuality")), "content")
        self.assertEqual(profile_for(dim("collaboration")), "collab")
        self.assertEqual(profile_for(dim("skillTransfer")), "transfer")

    def test_keyword_fallback(self):
        self.assertEqual(profile_for(dim("brandNew", label="仓库专业度")), "repo")
        self.assertEqual(profile_for(dim("brandNew", label="技术方案")), "engineering")
        self.assertEqual(profile_for(dim("brandNew", label="可视化看板")), "data")

    def test_unknown_falls_back_to_docs(self):
        self.assertEqual(profile_for(dim("whatever", label="别的")), "docs")


class SpecsTest(unittest.TestCase):
    def test_every_mapped_profile_has_spec_or_is_special(self):
        for profile in DIMENSION_PROFILES.values():
            self.assertTrue(profile in PROFILE_SPECS or profile in SPECIAL, profile)

    def test_specs_have_items(self):
        for name, items in PROFILE_SPECS.items():
            self.assertTrue(items, name)
            for item in items:
                self.assertTrue(item.label)
                self.assertTrue(item.patterns)


if __name__ == "__main__":
    unittest.main()
