#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C6A 数据管线的不变量测试。

它们不测「页面长得好不好看」，只测「数字之间的账对不对」：
- 511 份净数据里不能有重复、不能有撤回；
- 每个总分必须等于五个分项的加权和；
- 提交率的分母必须是 636，且 按时 + 迟交 == 已交；
- 洞察里的关键数字必须与指标快照一致（防止文案与数据脱节）；
- 真实数据快照的结构不能变（防止 fetch 脚本改坏）。

跑法：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "data" / "metrics.json"
APP_DATA = ROOT / "app" / "js" / "data.js"
WEIGHTS = {"dataInsight": 25, "visualization": 20, "artifact": 15, "aiUsage": 20, "reflection": 20}


def load() -> dict:
    return json.loads(METRICS.read_text(encoding="utf-8"))


class TestDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load()
        cls.rows = cls.d["rows"]
        cls.k = cls.d["kpis"]

    def test_shapes(self):
        self.assertEqual(self.k["expected"], 636, "应交 = 106 在读 × 6 挑战")
        self.assertEqual(self.k["submitted"], 511)
        self.assertEqual(len(self.rows), 511)
        self.assertEqual(self.k["students"], 106)
        self.assertEqual(self.k["challenges"], 6)
        # 611 原始 = 511 净 + 18 撤回 + 82 重复
        log = self.d["meta"]["log"]
        self.assertEqual(log["raw_rows"], 611)
        self.assertEqual(log["raw_rows"] - log["dropped_withdrawn"] - log["dropped_duplicate_attempt"], 511)

    def test_no_duplicates(self):
        keys = [(r["student_id"], r["challenge_id"]) for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)), "每生每挑战只能有一条有效提交")

    def test_no_withdrawn_or_non_roster(self):
        self.assertTrue(all(r["status"] != "withdrawn" for r in self.rows))
        roster = {s["id"] for s in self.d["students"] if s["status"] == "在读"}
        self.assertTrue(all(r["student_id"] in roster for r in self.rows))

    def test_timezone_is_plus8(self):
        for r in self.rows:
            self.assertTrue(r["submitted_at"].endswith("+08:00"), r["submitted_at"])
            datetime.fromisoformat(r["submitted_at"])  # 必须可解析

    def test_late_flag_matches_early_hours(self):
        for r in self.rows:
            if r["is_late"]:
                self.assertLess(r["early_hours"], 0)
                self.assertAlmostEqual(r["late_hours"], -r["early_hours"], places=2)
            else:
                self.assertGreaterEqual(r["early_hours"], 0)
                self.assertEqual(r["late_hours"], 0)

    def test_totals_match_dimensions(self):
        for r in self.rows:
            if r["total"] is None:
                continue
            self.assertIsNotNone(r["scores"])
            expect = sum(r["scores"][k] * w / 100 for k, w in WEIGHTS.items())
            self.assertAlmostEqual(r["total"], expect, delta=0.15, msg=f"{r['submission_id']} 总分与分项不符")

    def test_late_partition(self):
        self.assertEqual(self.k["onTime"] + self.k["late"], self.k["submitted"])
        self.assertAlmostEqual(self.k["lateShare"], self.k["late"] / self.k["submitted"] * 100, places=1)

    def test_rates_within_bounds(self):
        for key in ("rate", "onTimeRate", "lateShare", "redFlagRate"):
            self.assertGreaterEqual(self.k[key], 0)
            self.assertLessEqual(self.k[key], 100)

    def test_alt_denominators_ordered(self):
        a = self.d["alt"]
        # 只算已截止 > 含进行中 > 全员含退课：分母越大比率越低
        self.assertGreater(a["rateExcludeInProgress"], a["rateRoster"])
        self.assertGreater(a["rateRoster"], a["rateAllStudents"])
        self.assertGreater(a["avgReviewed"], a["avgZeroFilled"])

    def test_reviewer_cross_table(self):
        rows = [r for r in self.rows if r["total"] is not None]
        for rv in self.d["reviewers"]:
            sub = [r["total"] for r in rows if r["reviewer"] == rv["id"]]
            self.assertEqual(len(sub), rv["n"])
            if sub:
                self.assertAlmostEqual(sum(sub) / len(sub), rv["avg"], delta=0.15)

    def test_flags_consistent(self):
        for r in self.rows:
            self.assertEqual(r["flag_count"], len(r["flags"]))
            for f in r["flags"]:
                self.assertIn(f, {"缺 README", "缺 demo", "缺数据", "缺 AI 日志", "空目录"})


class TestInsights(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load()

    def test_each_insight_complete(self):
        self.assertGreaterEqual(len(self.d["insights"]), 7)
        for it in self.d["insights"]:
            for key in ("id", "title", "claim", "evidence", "caveat", "action", "level"):
                self.assertIn(key, it, f"{it.get('id')} 缺 {key}")
            self.assertGreaterEqual(len(it["evidence"]), 3, f"{it['id']} 证据不足 3 条")

    def test_insight_numbers_match_metrics(self):
        by_id = {i["id"]: i for i in self.d["insights"]}
        late, alt, k = self.d["late"], self.d["alt"], self.d["kpis"]
        # I1 的标题必须带上真实的最后 24 小时占比与峰值
        self.assertIn(f"{late['last24Share']}%", by_id["I1"]["title"])
        self.assertIn(str(late["peakCount"]), by_id["I1"]["claim"])
        # I2 必须带三个分母的比率
        for key in ("rateExcludeInProgress", "rateRoster", "rateAllStudents"):
            self.assertIn(f"{alt[key]}%", by_id["I2"]["title"])
        # I4 必须带上真实相关系数
        self.assertIn(str(late["corr"]), by_id["I4"]["title"])
        # I6 必须带真实的缺 demo 占比
        self.assertIn(f"{self.d['artifact']['noDemoShare']}%", by_id["I6"]["title"])

    def test_no_hardcoded_stale_numbers(self):
        """洞察文案里不允许出现与快照不符的旧数字（如 68.x 这类占位）。"""
        blob = json.dumps(self.d["insights"], ensure_ascii=False)
        for bad in ("68.x", "TODO", "XXX", "{", "}"):
            self.assertNotIn(bad, blob.replace("{", "").replace("}", "") if bad in "{}" else blob)


class TestDictionaryAndAppendix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load()

    def test_dictionary_covers_core_metrics(self):
        keys = {d["key"] for d in self.d["dictionary"]}
        for need in ("expected", "rate", "onTime", "late", "avg", "redFlag"):
            self.assertIn(need, keys)
        self.assertGreaterEqual(len(self.d["dictionary"]), 10)
        for d in self.d["dictionary"]:
            self.assertTrue(d["formula"] and d["denominator"] and d["why"], d["key"])

    def test_reflection_bimodal_detected(self):
        c5 = self.d["reflectionC5"]
        self.assertEqual(len(c5["peaks"]), 2, f"应识别出两个峰，实际 {c5['peaks']}")
        self.assertGreater(c5["highShare"], 30)

    def test_real_snapshot(self):
        real = self.d.get("real")
        self.assertIsNotNone(real, "真实数据快照缺失")
        delivery = [i for i in real["items"] if i["kind"] == "delivery"]
        self.assertEqual(len(delivery), 13)
        self.assertEqual(sum(i["commits"] for i in delivery), 93)
        for i in delivery:
            self.assertTrue(i["first_commit"].endswith("+08:00"))
            self.assertGreaterEqual(i["span_hours"], 0)
        self.assertGreaterEqual(sum(1 for i in delivery if i["squashed"]), 1, "至少应识别出一个疑似一次性推送")

    def test_app_data_embedded(self):
        text = APP_DATA.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("/* 自动生成"), "data.js 应由 build_dataset.py 生成")
        self.assertIn("window.C6A_DATA", text)
        self.assertIn('"submitted":511', text.replace(" ", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
