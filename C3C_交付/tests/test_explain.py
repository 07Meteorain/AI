"""duolog explain 子命令的测试（unittest，零第三方依赖）。

为什么 CLI 测试直接调 ``main`` 而不是起子进程：explain 没有颜色/编码这类
终端耦合，``main`` 已经是一个返回退出码的纯函数；用 ``redirect_stdout``
捕获输出比 ``subprocess`` 快，也不会受测试机 Python 路径影响。真正需要
子进程验证的编码问题由 Bramble 的 CLI 测试覆盖，这里不重复。

为什么宽度测试用 ``display_width`` 而不是 ``len``：explain 的输出是中文
框线，``len`` 会把"事件：E-003"算成 8 列而终端实际占 10 列；用渲染层的
``display_width`` 校验，才和用户看到的对齐方式一致。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from duolog.cli import main  # noqa: E402
from duolog.explain import _wrap, explain, explain_dict  # noqa: E402
from duolog.merge import merge  # noqa: E402
from duolog.model import Entry, parse_log  # noqa: E402
from duolog.render import display_width  # noqa: E402

_EXAMPLES = os.path.join(_ROOT, "examples")
_SAMPLE_A = os.path.join(_EXAMPLES, "sample_a.md")
_SAMPLE_B = os.path.join(_EXAMPLES, "sample_b.md")

#: 与 explain 的行首禁则集合保持一致的测试副本：断言"这些标点不能开头"。
_FORBIDDEN_LINE_START = frozenset("，。、；：！？）〕〉》」』】”’…,.;:!?)]}")


def _box_contents(text):
    """取出框内每一行的正文（去掉左右边框与补白），供禁则断言使用。"""
    for line in text.splitlines():
        if line.startswith("│ ") and line.endswith(" │"):
            content = line[2:-2].strip()
            if content:
                yield content


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _sample_result():
    """用 examples 夹具跑一次真实合并；E-003 是 R1、E-006 是 R3。"""
    entries_a, _ = parse_log(_read(_SAMPLE_A), "Aster")
    entries_b, _ = parse_log(_read(_SAMPLE_B), "Bramble")
    return merge(entries_a + entries_b)


class ExplainDictTest(unittest.TestCase):
    """结构化溯源必须与 merge 的内部证据逐字段对得上。"""

    @classmethod
    def setUpClass(cls):
        cls.result = _sample_result()
        cls.item = next(item for item in cls.result.items if item.eid == "E-003")

    def test_resolved_event_has_winner(self):
        payload = explain_dict(self.result, "E-003")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["eid"], "E-003")
        self.assertEqual(payload["status"], "resolved")
        self.assertEqual(payload["rule"], "R1-决策优先")
        self.assertEqual(payload["winner"], "Aster")
        self.assertEqual(payload["text"], self.item.text)

    def test_versions_match_merge_order_and_fields(self):
        payload = explain_dict(self.result, "E-003")
        expected = [
            {
                "author": version.author,
                "clock": version.clock,
                "tags": list(version.tags),
                "text": version.text,
            }
            for version in self.item.versions
        ]
        self.assertEqual(payload["versions"], expected)
        self.assertEqual(
            [version["author"] for version in payload["versions"]],
            [version.author for version in self.item.versions],
        )

    def test_dict_has_exact_contract_keys(self):
        payload = explain_dict(self.result, "E-003")
        self.assertEqual(
            set(payload), {"eid", "status", "rule", "winner", "text", "versions"}
        )
        for version in payload["versions"]:
            self.assertEqual(set(version), {"author", "clock", "tags", "text"})

    def test_single_version_has_no_winner(self):
        payload = explain_dict(self.result, "E-002")
        self.assertEqual(payload["status"], "single")
        self.assertEqual(payload["rule"], "")
        self.assertIsNone(payload["winner"])
        self.assertEqual(len(payload["versions"]), 1)

    def test_confirmed_is_not_a_winner(self):
        payload = explain_dict(self.result, "E-001")
        self.assertEqual(payload["status"], "confirmed")
        self.assertEqual(payload["rule"], "R0")
        self.assertIsNone(payload["winner"])

    def test_needs_review_has_no_winner(self):
        payload = explain_dict(self.result, "E-006")
        self.assertEqual(payload["status"], "needs_review")
        self.assertIsNone(payload["winner"])

    def test_missing_eid_returns_none(self):
        self.assertIsNone(explain_dict(self.result, "E-999"))


class ExplainTextTest(unittest.TestCase):
    """终端文本：无 ANSI、逐行等宽、证据齐全。"""

    @classmethod
    def setUpClass(cls):
        cls.result = _sample_result()

    def test_contains_versions_rule_and_verdict(self):
        text = explain(self.result, "E-003")
        self.assertIn("E-003", text)
        self.assertIn("R1-决策优先", text)
        self.assertIn("Aster", text)
        self.assertIn("Bramble", text)
        self.assertIn("原始版本", text)
        self.assertIn("终裁", text)
        self.assertIn("合并正文", text)

    def test_no_ansi(self):
        text = explain(self.result, "E-003")
        self.assertNotIn("\x1b", text)

    def test_escape_in_source_text_is_scrubbed(self):
        entries = [
            Entry(eid="E-100", author="Aster", clock=1, tags=(), text="危险\x1b[31m文本", line=1)
        ]
        text = explain(merge(entries), "E-100")
        self.assertNotIn("\x1b", text)

    def test_every_line_has_same_display_width(self):
        text = explain(self.result, "E-003")
        lines = text.splitlines()
        self.assertGreaterEqual(len(lines), 5)
        widths = {display_width(line) for line in lines}
        self.assertEqual(len(widths), 1, "行宽不一致：{0}".format(sorted(widths)))

    def test_long_text_still_aligned(self):
        long_text = "很长的中文正文" * 40
        entries = [
            Entry(eid="E-101", author="Aster", clock=1, tags=(), text=long_text, line=1),
            Entry(eid="E-101", author="Bramble", clock=2, tags=(), text=long_text + "（另一版）", line=1),
        ]
        text = explain(merge(entries), "E-101")
        widths = {display_width(line) for line in text.splitlines()}
        self.assertEqual(len(widths), 1)

    def test_wrap_makes_progress_when_limit_narrower_than_char(self):
        # limit=1 放不下一个汉字：必须无条件吐出该字符并前进，不能原地死循环。
        self.assertEqual(_wrap("中", 1), ["中"])
        self.assertEqual(_wrap("中中", 1), ["中", "中"])

    def test_missing_eid_is_a_notice_not_a_crash(self):
        text = explain(self.result, "E-999")
        self.assertIn("未找到", text)
        widths = {display_width(line) for line in text.splitlines()}
        self.assertEqual(len(widths), 1)

    def test_no_line_starts_with_forbidden_punctuation(self):
        # E-006 的 R3 理由足够长，旧实现在这里会把"、"折到下一行行首。
        text = explain(self.result, "E-006")
        offenders = [
            content
            for content in _box_contents(text)
            if content[0] in _FORBIDDEN_LINE_START
        ]
        self.assertEqual(offenders, [], "这些行以禁则标点开头：{0}".format(offenders))
        widths = {display_width(line) for line in text.splitlines()}
        self.assertEqual(len(widths), 1, "禁则处理后出现超宽行：{0}".format(sorted(widths)))

    def test_kinsoku_keeps_long_paragraph_aligned(self):
        # 用一段密集标点的长文本压测：多轮"下移"后仍必须每行等宽。
        text = "甲、乙，丙。丁；戊：己！庚？辛）壬”癸…" * 8
        entries = [
            Entry(eid="E-102", author="Aster", clock=1, tags=(), text=text, line=1),
            Entry(eid="E-102", author="Bramble", clock=2, tags=(), text=text + "补充", line=1),
        ]
        rendered = explain(merge(entries), "E-102")
        widths = {display_width(line) for line in rendered.splitlines()}
        self.assertEqual(len(widths), 1)
        offenders = [
            content
            for content in _box_contents(rendered)
            if content[0] in _FORBIDDEN_LINE_START
        ]
        self.assertEqual(offenders, [], "这些行以禁则标点开头：{0}".format(offenders))


class ExplainCliTest(unittest.TestCase):
    """退出码 0/1/2 与 stdout 洁净度是 explain 的硬接口。"""

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def _args(self, *extra):
        return (
            "explain",
            "--a",
            _SAMPLE_A,
            "--b",
            _SAMPLE_B,
            "--author-a",
            "Aster",
            "--author-b",
            "Bramble",
        ) + extra

    def test_json_output_is_parsable_and_clean(self):
        code, out, err = self._run(self._args("--eid", "E-003", "--json"))
        self.assertEqual(code, 0, err)
        self.assertNotIn("\x1b", out)
        payload = json.loads(out)
        self.assertEqual(payload["eid"], "E-003")
        self.assertEqual(payload["winner"], "Aster")
        self.assertEqual(payload["rule"], "R1-决策优先")

    def test_text_output_works(self):
        code, out, err = self._run(self._args("--eid", "E-003"))
        self.assertEqual(code, 0, err)
        self.assertNotIn("\x1b", out)
        self.assertIn("E-003", out)
        self.assertIn("R1-决策优先", out)

    def test_no_color_flag_is_accepted(self):
        # merge 有这个通用开关；explain 本来就不上色，接受它只为命令模板一致。
        code, out, err = self._run(self._args("--eid", "E-003", "--no-color"))
        self.assertEqual(code, 0, err)
        self.assertNotIn("\x1b", out)
        self.assertIn("E-003", out)

    def test_missing_eid_exit_1(self):
        code, out, err = self._run(self._args("--eid", "E-999"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("未找到", err)

    def test_missing_eid_json_exit_1(self):
        code, out, err = self._run(self._args("--eid", "E-999", "--json"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("未找到", err)

    def test_missing_input_file_exit_2(self):
        code, out, err = self._run(
            ("explain", "--a", os.path.join(_EXAMPLES, "missing.md"), "--b", _SAMPLE_B, "--eid", "E-003")
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("无法读取", err)

    def test_parse_error_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = os.path.join(tmp, "bad.md")
            with open(bad_path, "w", encoding="utf-8") as handle:
                handle.write("## E-001 | 1 | 类型:分工 | 多余字段\n正文\n")
            code, out, err = self._run(
                ("explain", "--a", bad_path, "--b", _SAMPLE_B, "--eid", "E-001")
            )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("解析出现 error", err)

    def test_missing_eid_option_exit_2(self):
        code, out, err = self._run(("explain", "--a", _SAMPLE_A, "--b", _SAMPLE_B))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_help_lists_explain(self):
        code, out, err = self._run(("--help",))
        self.assertEqual(code, 0, err)
        self.assertIn("explain", out)


if __name__ == "__main__":
    unittest.main()
