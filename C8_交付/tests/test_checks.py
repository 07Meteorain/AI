"""checks.py：交付物解析、维度信号、红旗封顶、不可验证维度。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from submitgate.challenge import load_challenge
from submitgate.checks import evaluate_challenge

from util import AAR, AI_LOG, FULL_DIMENSIONS, make_record, full_delivery, write_course, write_files


def _load(tmp: Path, record: dict, delivery: dict[str, str] | None):
    course = write_course(tmp / "course", {record["source_id"]: record})
    challenge = load_challenge(course / record["source_id"] / "challenge.json")
    if delivery is None:
        return challenge, None
    delivery_dir = write_files(tmp / "repo" / f"{record['source_id']}_交付", delivery)
    return challenge, delivery_dir


class MissingDeliveryTest(unittest.TestCase):
    def test_all_missing_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9"), None)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        self.assertIsNone(evaluation.delivery_dir)
        self.assertEqual(evaluation.missing, ["proposal", "AI日志"])
        self.assertEqual({flag.id for flag in evaluation.flags}, {"missing_artifacts", "no_ai_log"})
        self.assertEqual(evaluation.max_score, 0)
        self.assertFalse(evaluation.passed)


class FullDeliveryTest(unittest.TestCase):
    def test_passes_with_all_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9", required_deliverables="*proposal*,*AI日志*,*AAR_W*"), full_delivery())
            evaluation = evaluate_challenge(challenge, delivery_dir)
        self.assertEqual(evaluation.missing, [])
        self.assertEqual(evaluation.flags, [])
        self.assertTrue(evaluation.passed)
        self.assertEqual(evaluation.total_score, evaluation.max_score)
        self.assertEqual(evaluation.max_score, 100)
        self.assertEqual(len(evaluation.covered_dimensions), 5)

    def test_check_statuses_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9"), full_delivery())
            evaluation = evaluate_challenge(challenge, delivery_dir)
        ids = {check.id for check in evaluation.checks}
        self.assertTrue({"req:proposal", "req:AI日志", "acceptance", "submit_note", "ai_log", "aar"} <= ids)
        statuses = {check.status for check in evaluation.checks}
        self.assertTrue(statuses <= {"pass", "fail", "unverified"})
        self.assertIn("on_time", ids)


class EmptyFileTest(unittest.TestCase):
    def test_zero_byte_file_counts_as_missing(self):
        delivery = full_delivery()
        delivery["proposal.md"] = ""
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9"), delivery)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        self.assertIn("proposal", evaluation.missing)
        flag_ids = {flag.id for flag in evaluation.flags}
        self.assertIn("missing_artifacts", flag_ids)


class OneShotAiTest(unittest.TestCase):
    def test_single_round_gets_capped(self):
        delivery = full_delivery()
        delivery["AI日志.md"] = "# AI 日志\n\n## 第 1 轮\n\n> 帮我写一个工具\n\n一次就成了。\n" + "补充。" * 400
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9"), delivery)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        self.assertIn("one_shot_ai", {flag.id for flag in evaluation.flags})
        ai_dim = [dim for dim in evaluation.dimensions if dim.id == "aiUsage"][0]
        self.assertLessEqual(ai_dim.score, 5)

    def test_no_log_gets_reflection_cap(self):
        delivery = full_delivery()
        del delivery["AI日志.md"]
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9"), delivery)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        self.assertIn("no_ai_log", {flag.id for flag in evaluation.flags})
        reflection = [dim for dim in evaluation.dimensions if dim.id == "reflectionQuality"][0]
        self.assertLessEqual(reflection.score, 5)

    def test_phase_style_log_with_two_prompts_counts_as_iteration(self):
        delivery = full_delivery()
        delivery["AI日志.md"] = (
            "# AI 使用日志\n\n"
            "## 1. 需求\n\n> 帮我做交付门禁\n\n"
            "## 2. 实现\n\n> 加一个离线自检\n\n"
            "第一版失败：正则写错，返工一次。\n"
            "第二次也出错：中文数字没处理。\n" + "补充说明。" * 300
        )
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), make_record("C9"), delivery)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        self.assertNotIn("one_shot_ai", {flag.id for flag in evaluation.flags})


class UncoveredDimensionTest(unittest.TestCase):
    def test_participation_is_unverified_not_zero(self):
        record = make_record("C3")
        record["rubric_dimensions"] = json.dumps({"dimensions": FULL_DIMENSIONS}, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), record, full_delivery())
            evaluation = evaluate_challenge(challenge, delivery_dir)
        participation = [dim for dim in evaluation.dimensions if dim.id == "participationQuality"][0]
        self.assertFalse(participation.covered)
        self.assertEqual(participation.score, 0)
        self.assertNotIn(participation.max_points, [dim.max_points for dim in evaluation.covered_dimensions])
        self.assertEqual(evaluation.max_score, sum(dim.max_points for dim in evaluation.covered_dimensions))

    def test_template_doc_is_not_full_credit(self):
        record = make_record("C3")
        record["rubric_dimensions"] = json.dumps({"dimensions": FULL_DIMENSIONS}, ensure_ascii=False)
        delivery = full_delivery()
        delivery["参与记录表.md"] = "# 参与记录表\n\n| 时间 | 内容 |\n| --- | --- |\n| 待填 | 待填 |\n" + "模板占位。\n" * 60
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), record, delivery)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        participation = [dim for dim in evaluation.dimensions if dim.id == "participationQuality"][0]
        self.assertTrue(participation.covered)
        self.assertLess(participation.score, participation.max_points)


class SpecProfileTest(unittest.TestCase):
    def test_repo_profile_counts_files(self):
        record = make_record("C5")
        record["rubric_dimensions"] = json.dumps(
            {"dimensions": [
                {"id": "repoQuality", "label": "仓库质量", "description": "开源仓库的专业度", "maxPoints": 25},
                {"id": "artifactCompleteness", "label": "产物完整性", "description": "齐全", "maxPoints": 15},
            ]},
            ensure_ascii=False,
        )
        delivery = full_delivery()
        delivery.update(
            {
                "LICENSE": "MIT\n",
                ".github/workflows/ci.yml": "on: push\n",
                "docs/guide.md": "# 指南\n",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            challenge, delivery_dir = _load(Path(tmp), record, delivery)
            evaluation = evaluate_challenge(challenge, delivery_dir)
        repo_dim = [dim for dim in evaluation.dimensions if dim.id == "repoQuality"][0]
        self.assertTrue(repo_dim.covered)
        self.assertEqual(repo_dim.score, 25)


if __name__ == "__main__":
    unittest.main()
