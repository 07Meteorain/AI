"""challenge.py 的解析测试：平台文本 → 结构化数据。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from submitgate import challenge as ch


class ParseDeliverablesTest(unittest.TestCase):
    def test_wildcard_and_exact(self):
        items = ch.parse_deliverables("README.md,*repo链接*,*AI日志*,*拿来说明*")
        self.assertEqual([item.name for item in items], ["README.md", "repo链接", "AI日志", "拿来说明"])
        self.assertEqual([item.wildcard for item in items], [False, True, True, True])

    def test_fullwidth_comma_and_spaces(self):
        items = ch.parse_deliverables(" *proposal* ， *AAR_W* , *AI日志* ")
        self.assertEqual([item.name for item in items], ["proposal", "AAR_W", "AI日志"])

    def test_empty(self):
        self.assertEqual(ch.parse_deliverables(""), ())
        self.assertEqual(ch.parse_deliverables(" , , "), ())

    def test_star_only_chunk_ignored(self):
        self.assertEqual(ch.parse_deliverables("*"), ())


class DeadlineTest(unittest.TestCase):
    def test_formats(self):
        self.assertIsNotNone(ch.parse_deadline("2026-12-31T23:59"))
        self.assertIsNotNone(ch.parse_deadline("2026-12-31"))
        self.assertIsNone(ch.parse_deadline(""))
        self.assertIsNone(ch.parse_deadline("下个月"))

    def test_deadline_dt(self):
        record = {"source_id": "C8", "deadline": "2026-12-31T23:59", "required_deliverables": "*AI日志*"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "challenge.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            loaded = ch.load_challenge(path)
        self.assertEqual(loaded.deadline_dt.year, 2026)
        self.assertEqual(loaded.deadline_dt.hour, 23)


class RubricTest(unittest.TestCase):
    def test_parse_json_string(self):
        payload = json.dumps(
            {"dimensions": [{"id": "delivery", "label": "交付质量", "description": "d", "maxPoints": 25}]}
        )
        dims = ch.parse_rubric(payload)
        self.assertEqual(len(dims), 1)
        self.assertEqual(dims[0].id, "delivery")
        self.assertEqual(dims[0].max_points, 25)

    def test_parse_dict_and_broken(self):
        self.assertEqual(ch.parse_rubric(None), ())
        self.assertEqual(ch.parse_rubric("{not json"), ())
        dims = ch.parse_rubric({"dimensions": [{"id": "x", "maxPoints": "7"}]})
        self.assertEqual(dims[0].max_points, 7)

    def test_red_flags(self):
        flags = ch.parse_red_flags(
            json.dumps({"flags": [{"id": "no_ai_log", "description": "无日志", "affectedDimension": "reflectionQuality", "maxScore": 5}]})
        )
        self.assertEqual(flags[0].id, "no_ai_log")
        self.assertEqual(flags[0].dimension, "reflectionQuality")
        self.assertEqual(flags[0].max_score, 5)


class LoadAndSortTest(unittest.TestCase):
    def test_load_minimal(self):
        record = {
            "source_id": "C8",
            "challenge_id": "ch-1",
            "title": "真实项目",
            "required_deliverables": "*proposal*,*AAR_W*",
            "rubric_dimensions": json.dumps({"dimensions": [{"id": "delivery", "maxPoints": 25}]}),
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "challenge.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            loaded = ch.load_challenge(path)
        self.assertEqual(loaded.source_id, "C8")
        self.assertEqual(loaded.deliverable_names, ("proposal", "AAR_W"))
        self.assertEqual(loaded.max_points, 25)

    def test_source_id_falls_back_to_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "C10H"
            folder.mkdir()
            path = folder / "challenge.json"
            path.write_text(json.dumps({"title": "t"}), encoding="utf-8")
            loaded = ch.load_challenge(path)
        self.assertEqual(loaded.source_id, "C10H")

    def test_sort_key(self):
        ids = ["C10", "C3", "C3C", "C5A", "C5", "C8"]
        ordered = sorted(ids, key=ch.challenge_sort_key)
        self.assertEqual(ordered, ["C3", "C3C", "C5", "C5A", "C8", "C10"])

    def test_discover_course(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for sid in ("C9", "C3"):
                folder = root / sid
                folder.mkdir()
                (folder / "challenge.json").write_text(json.dumps({"source_id": sid}), encoding="utf-8")
            (root / "no-record").mkdir()
            found = ch.discover_course(root)
        self.assertEqual([item.source_id for item in found], ["C3", "C9"])


if __name__ == "__main__":
    unittest.main()
