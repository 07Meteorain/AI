"""scan.py / textscan.py：文件枚举、交付物匹配、文本特征。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from submitgate import scan, textscan
from submitgate.challenge import Deliverable


class IterFilesTest(unittest.TestCase):
    def test_relative_posix_and_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "a.md").write_text("x", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "a.pyc").write_text("x", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("x", encoding="utf-8")
            (root / "b.txt").write_text("yy", encoding="utf-8")
            files = scan.iter_files(root)
        rels = [entry.rel for entry in files]
        self.assertEqual(rels, ["b.txt", "docs/a.md"])
        self.assertEqual({entry.rel: entry.size for entry in files}["b.txt"], 2)

    def test_normalize(self):
        self.assertEqual(scan.normalize("ＡＩ 日志"), "ai日志")
        self.assertEqual(scan.normalize("AAR_W"), "aar_w")


class MatchDeliverableTest(unittest.TestCase):
    def test_wildcard_matches_path_segment(self):
        files = [scan.FileEntry("AI日志/AI使用日志.md", 10), scan.FileEntry("README.md", 10)]
        hits = scan.match_deliverable(Deliverable("*AI日志*", "AI日志", True), files)
        self.assertEqual([hit.rel for hit in hits], ["AI日志/AI使用日志.md"])

    def test_wildcard_matches_file_name_inside(self):
        files = [scan.FileEntry("07Meteorain_C8_AI日志.md", 10)]
        hits = scan.match_deliverable(Deliverable("*AI日志*", "AI日志", True), files)
        self.assertEqual(len(hits), 1)

    def test_exact_matches_only_file_name(self):
        files = [
            scan.FileEntry("README.md", 10),
            scan.FileEntry("docs/README.md", 10),
            scan.FileEntry("README2.md", 10),
        ]
        hits = scan.match_deliverable(Deliverable("README.md", "README.md", False), files)
        self.assertEqual([hit.rel for hit in hits], ["README.md", "docs/README.md"])

    def test_shortest_first(self):
        files = [scan.FileEntry("deep/nested/提案.md", 1), scan.FileEntry("提案.md", 1)]
        hits = scan.match_deliverable(Deliverable("*提案*", "提案", True), files)
        self.assertEqual(hits[0].rel, "提案.md")


class RoundMetricsTest(unittest.TestCase):
    def test_chinese_numerals(self):
        text = "## 第一轮\n## 第二轮\n## 第三轮\n"
        self.assertEqual(textscan.round_metrics(text), (3, 3))

    def test_large_arabic_number(self):
        self.assertEqual(textscan.round_metrics("## 2. 执行轮次（12 轮）")[0], 12)

    def test_round_and_r_heading(self):
        text = "Round 4 完成\n\n## R5 收尾\n"
        self.assertEqual(textscan.round_metrics(text)[0], 5)

    def test_iteration_count_phrase(self):
        self.assertEqual(textscan.round_metrics("三次 prompt 迭代之后")[0], 3)

    def test_steps_also_count(self):
        self.assertEqual(textscan.round_metrics("第 1 步\n第 4 步")[0], 4)

    def test_no_rounds(self):
        self.assertEqual(textscan.round_metrics("没有任何编号"), (0, 0))


class TextHelpersTest(unittest.TestCase):
    def test_count_quote_blocks(self):
        text = "> a\n> b\n\n正文\n\n> c\n"
        self.assertEqual(textscan.count_quote_blocks(text), 2)

    def test_template_marks(self):
        self.assertEqual(textscan.template_marks("# 表\n\n待填写\nTODO\n"), 2)
        self.assertEqual(textscan.template_marks("# 已完成\n"), 0)

    def test_has_command_block(self):
        self.assertTrue(textscan.has_command_block("```bash\npython -m demo\n```"))
        self.assertFalse(textscan.has_command_block("```\n只是代码\n```"))
        self.assertFalse(textscan.has_command_block("没有代码块"))

    def test_count_fences(self):
        self.assertEqual(textscan.count_fences("```\na\n```\n\n```bash\nb\n```"), 2)

    def test_strip_code_fences_removes_numbers(self):
        text = "正文 3 项\n```\nprint(123456)\n```\n"
        self.assertEqual(textscan.count_distinct_numbers(text), 1)

    def test_find_heading(self):
        text = "# 标题\n\n## 快速开始\n\n## 改进方案\n"
        self.assertEqual(textscan.find_heading(text, ("快速",)), "快速开始")
        self.assertIsNone(textscan.find_heading(text, ("安装",)))

    def test_heading_levels(self):
        self.assertEqual(textscan.headings("# a\n### b\n"), [(1, "a"), (3, "b")])

    def test_read_text_handles_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"\x00\x01\x02")
            self.assertEqual(textscan.read_text(path), "")
        self.assertEqual(textscan.read_text(Path(tmp) / "missing.md"), "")


if __name__ == "__main__":
    unittest.main()
