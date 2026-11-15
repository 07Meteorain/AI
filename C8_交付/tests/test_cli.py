"""cli.py：退出码、产物文件、错误处理。"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from submitgate.cli import EXIT_ERROR, EXIT_GATE_FAIL, EXIT_OK, main

from util import full_delivery, make_record, write_course, write_files


def _run(argv: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _empty_mapping(root: Path) -> Path:
    path = root / "mapping.json"
    path.write_text('{"aliases": {}}', encoding="utf-8")
    return path


class CliTest(unittest.TestCase):
    def test_version(self):
        code, out = _run(["version"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("submitgate", out)

    def test_selftest(self):
        code, out = _run(["selftest"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("自检通过", out)

    def test_check_gate_pass_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = write_course(root / "course", {"C9": make_record("C9", required_deliverables="*proposal*,*AI日志*,*AAR_W*")})
            repo = root / "repo"
            write_files(repo / "C9_交付", full_delivery())
            out_dir = root / "reports"
            code, output = _run(
                [
                    "check",
                    "--course", str(course),
                    "--repo", str(repo),
                    "--out", str(out_dir),
                    "--mapping", str(_empty_mapping(root)),
                    "--github-base", "",
                ]
            )
            files = sorted(path.name for path in out_dir.iterdir())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(files, sorted(["交付验收报告.md", "交付验收报告.json", "导航站.html"]))
        self.assertIn("结论：PASS", output)

    def test_check_gate_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = write_course(root / "course", {"C9": make_record("C9")})
            repo = root / "repo"
            (repo / "C9_交付").mkdir(parents=True)
            out_dir = root / "reports"
            code, output = _run(
                ["check", "--course", str(course), "--repo", str(repo), "--out", str(out_dir),
                 "--mapping", str(_empty_mapping(root)), "--formats", "md"]
            )
            files = [path.name for path in out_dir.iterdir()]
        self.assertEqual(code, EXIT_GATE_FAIL)
        self.assertEqual(files, ["交付验收报告.md"])
        self.assertIn("结论：FAIL", output)

    def test_bad_format_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = write_course(root / "course", {"C9": make_record("C9")})
            code, _ = _run(["check", "--course", str(course), "--repo", str(root), "--formats", "pdf"])
        self.assertEqual(code, EXIT_ERROR)

    def test_missing_course_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = _run(["check", "--course", str(Path(tmp) / "nope"), "--repo", tmp])
        self.assertEqual(code, EXIT_ERROR)

    def test_quiet_suppresses_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course = write_course(root / "course", {"C9": make_record("C9", required_deliverables="*proposal*,*AI日志*,*AAR_W*")})
            repo = root / "repo"
            write_files(repo / "C9_交付", full_delivery())
            code, output = _run(
                ["check", "--course", str(course), "--repo", str(repo), "--out", str(root / "r"),
                 "--mapping", str(_empty_mapping(root)), "--quiet", "--formats", "json"]
            )
        self.assertEqual(code, EXIT_OK)
        self.assertNotIn("[PASS]", output)


if __name__ == "__main__":
    unittest.main()
