"""engine.py / report.py：汇总、报告序列化、HTML 自包含性。"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from submitgate import report as rp
from submitgate.engine import ToolError, run

from util import full_delivery, make_record, write_course, write_files


def _fixture(tmp: Path, *, second_delivered: bool = False):
    course = write_course(
        tmp / "course",
        {
            "C9": make_record("C9", required_deliverables="*proposal*,*AI日志*,*AAR_W*"),
            "C10": make_record("C10", required_deliverables="AGENT.md,*architecture*,*AAR*,*AI日志*"),
        },
    )
    repo = tmp / "repo"
    write_files(repo / "C9_交付", full_delivery())
    write_files(repo / "C4A_交付", {"旧交付.md": "历史内容"})
    if second_delivered:
        delivery = full_delivery()
        delivery["AGENT.md"] = "# Agent\n\n" + "说明。" * 200
        delivery["architecture.md"] = "# 架构\n\n" + "分层的理由。" * 200
        write_files(repo / "C10_交付", delivery)
    mapping = tmp / "mapping.json"
    mapping.write_text(json.dumps({"aliases": {}}), encoding="utf-8")
    return course, repo, mapping


class RunTest(unittest.TestCase):
    def test_summary_and_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            course, repo, mapping = _fixture(Path(tmp))
            report = run(course, repo, mapping)
        self.assertEqual(report.total, 2)
        self.assertEqual(len(report.passed), 1)
        self.assertEqual(len(report.failed), 1)
        self.assertEqual([p.name for p in report.mapping.orphans], ["C4A_交付"])
        self.assertFalse(report.gate_ok)
        self.assertEqual(report.max_score, 100)
        self.assertEqual(report.covered_dimensions, 5)

    def test_gate_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            course, repo, mapping = _fixture(Path(tmp), second_delivered=True)
            report = run(course, repo, mapping)
        self.assertTrue(report.gate_ok)
        self.assertEqual(len(report.passed), 2)

    def test_missing_course_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ToolError):
                run(Path(tmp) / "nope", Path(tmp))
            empty = Path(tmp) / "empty"
            empty.mkdir()
            with self.assertRaises(ToolError):
                run(empty, Path(tmp))


class ReportFormatsTest(unittest.TestCase):
    def _report(self, tmp: Path):
        course, repo, mapping = _fixture(tmp)
        return run(course, repo, mapping)

    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._report(Path(tmp))
            payload = json.loads(rp.to_json(report))
        self.assertEqual(payload["summary"]["challenges"], 2)
        self.assertEqual(payload["summary"]["gate"], "FAIL")
        self.assertEqual(payload["challenges"][0]["source_id"], "C9")
        self.assertIn("dimensions", payload["challenges"][0])
        self.assertTrue(payload["challenges"][0]["deliverables"][0]["files"])
        self.assertTrue(payload["challenges"][0]["deliverables"][0]["files"][0].startswith("C9_交付/"))

    def test_markdown_contains_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._report(Path(tmp))
            text = rp.to_markdown(report, "https://example.com/tree/master")
        for needle in ("# 挑战交付验收报告", "## 一、总览", "## 二、缺口清单", "## 三、逐挑战明细", "## 五、方法与边界"):
            self.assertIn(needle, text)
        self.assertIn("C10", text)
        self.assertIn("example.com/tree/master/C9_%E4%BA%A4%E4%BB%98/proposal.md", text)

    def test_markdown_without_base_has_no_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._report(Path(tmp))
            text = rp.to_markdown(report, None)
        self.assertNotIn("](" , text)

    def test_html_is_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._report(Path(tmp))
            page = rp.to_html(report, "https://example.com/tree/master")
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("<style>", page)
        self.assertNotIn("<script src=", page)
        self.assertNotIn("<link ", page)
        self.assertNotIn("http://", page)
        self.assertIn("C9", page)
        self.assertIn("需人工" if "需人工" in page else "可验证", page)

    def test_html_escapes_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            course = write_course(
                Path(tmp) / "course",
                {"C9": make_record("C9", title="<img src=x onerror=alert(1)>")},
            )
            repo = Path(tmp) / "repo"
            write_files(repo / "C9_交付", full_delivery())
            report = run(course, repo, None)
            page = rp.to_html(report, None)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img", page)

    def test_uncovered_dimension_shows_manual_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._report(Path(tmp))
            page = rp.to_html(report, None)
            text = rp.to_markdown(report, None)
        self.assertIn("可验证维度", page)
        self.assertIn("全部维度满分", text)


if __name__ == "__main__":
    unittest.main()
