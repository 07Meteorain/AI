"""duolog 的单元与集成测试（标准库 unittest，不依赖 pytest）。

运行方式（两种都可以）::

    python -m unittest discover -s tests -v
    cd tests && python -m unittest discover -s . -v

为什么在导入前手动改 ``sys.path``：``discover -s tests`` 只会把 ``tests/``
放进 ``sys.path``，而 ``duolog`` 包在上一级。显式插入项目根，测试就不依赖
"在哪个目录执行"这种环境运气。

为什么渲染测试用轻量假对象：``render`` 按契约只做属性访问，用假对象可以在
Aster 的 merge/analyze 合入之前先验收渲染层；真正跑 R0~R3 的集成测试则
显式依赖他的模块，缺失时整类 skip，而不是假装通过。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from duolog.model import Entry, eid_key, fingerprint_of, parse_log  # noqa: E402
from duolog.render import _fmt_tags, display_width, render_markdown, render_terminal  # noqa: E402

try:  # pragma: no cover - 取决于 Aster 的模块是否已合入
    from duolog.analyze import profile as build_profile  # noqa: E402
    from duolog.merge import merge  # noqa: E402
except ImportError as exc:
    # 只有在"模块本身还没合入"时才优雅 skip；模块存在但签名/内部导入错了
    # 必须原样抛出来，否则契约违例会被 skip 掩盖成"测试通过"。
    _missing = getattr(exc, "name", None)
    if _missing not in ("duolog.analyze", "duolog.merge"):
        raise
    build_profile = None
    merge = None
    _ASTER_IMPORT_ERROR = exc
else:
    _ASTER_IMPORT_ERROR = None

_HAS_ALGO = merge is not None and build_profile is not None
_NEEDS_ALGO = unittest.skipUnless(
    _HAS_ALGO, "Aster 的 merge/analyze 尚未就位：{0}".format(_ASTER_IMPORT_ERROR)
)

_EXAMPLES = os.path.join(_ROOT, "examples")
_SAMPLE_A = os.path.join(_EXAMPLES, "sample_a.md")
_SAMPLE_B = os.path.join(_EXAMPLES, "sample_b.md")
_SAMPLES_READY = os.path.isfile(_SAMPLE_A) and os.path.isfile(_SAMPLE_B)
_NEEDS_CLI = unittest.skipUnless(
    _HAS_ALGO and _SAMPLES_READY, "需要 merge/analyze 与 examples 夹具同时就位"
)


def _entry(eid, author, clock, text, tags=()):
    """直接构造 Entry：规则测试需要精确控制原始正文，绕开 parse_log 的规范化。"""
    return Entry(eid=eid, author=author, clock=clock, tags=tuple(tags), text=text, line=1)


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _fake_result():
    """渲染用的最小合法结果（字段形状严格按契约 §2/§5/§6）。"""
    versions = (
        SimpleNamespace(author="Aster", clock=2),
        SimpleNamespace(author="Bramble", clock=2),
    )
    items = [
        SimpleNamespace(
            eid="E-001",
            authors=("Aster", "Bramble"),
            tags=("类型:分工",),
            text="同一条正文",
            status="confirmed",
            rule="R0",
            versions=(),
        ),
        SimpleNamespace(
            eid="E-006",
            authors=("Aster", "Bramble"),
            tags=("类型:互检",),
            text="甲版本\n乙版本",
            status="needs_review",
            rule="R3-无法裁决",
            versions=versions,
        ),
    ]
    conflicts = [
        SimpleNamespace(
            eid="E-006",
            versions=versions,
            winner=None,
            rule="R3-无法裁决",
            resolution="needs_review",
            note="双方时钟相同，\n没有决策标签，无法裁决。",
        )
    ]
    stats = {
        "total_items": 2,
        "single": 0,
        "confirmed": 1,
        "resolved": 0,
        "needs_review": 1,
        "conflicts": 1,
        "authors": 2,
        "entries": 4,
    }
    return SimpleNamespace(
        items=items,
        conflicts=conflicts,
        fingerprint="0123456789abcdef",
        stats=stats,
    )


def _fake_profile():
    return SimpleNamespace(
        authors=("Aster", "Bramble"),
        skill_tags={"Aster": {"SEL-1": 2}, "Bramble": {"SEL-2": 1}},
        type_tags={"Aster": {"分工": 1, "互检": 1}, "Bramble": {"实现": 1}},
        transfers=(
            SimpleNamespace(
                src="Aster", dst="Bramble", skill="SEL-1", evidence=("E-002", "E-006")
            ),
        ),
        share={"Aster": 0.5, "Bramble": 0.5},
    )


def _table_blocks(text):
    """把终端输出里的连续框线块切出来，用于逐表检查宽度一致性。"""
    blocks = []
    current = []
    for line in text.splitlines():
        if line and line[0] in "┌│├└":
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


class DisplayWidthTest(unittest.TestCase):
    """显示宽度是中文对齐的地基，先把它测死。"""

    def test_ascii(self):
        self.assertEqual(display_width("abc"), 3)
        self.assertEqual(display_width(""), 0)

    def test_cjk_is_two_columns(self):
        self.assertEqual(display_width("中文"), 4)
        self.assertEqual(display_width("协作日志"), 8)

    def test_mixed_text(self):
        self.assertEqual(display_width("中文abc"), 7)
        # U+00B7 属于 East Asian Width = Ambiguous，本项目按 1 列计
        self.assertEqual(display_width("SEL-1·协作"), 10)

    def test_fullwidth_forms(self):
        self.assertEqual(display_width("ＡＢ"), 4)

    def test_combining_mark_is_zero(self):
        self.assertEqual(display_width("e\u0301"), 1)
        self.assertEqual(display_width("a\u0308\u0301b"), 2)

    def test_newline_is_not_counted(self):
        self.assertEqual(display_width("a\nb"), 2)
        self.assertEqual(display_width("中\n文"), 4)

    def test_emoji_is_wide(self):
        self.assertEqual(display_width("\U0001f600"), 2)


class ParseModelTest(unittest.TestCase):
    """解析是唯一数据源的入口，合法/非法表头与重复 eid 必须有明确信号。"""

    def test_parse_sample_a(self):
        entries, issues = parse_log(_read(_SAMPLE_A), "Aster")
        self.assertEqual(len(entries), 6)
        self.assertEqual({entry.author for entry in entries}, {"Aster"})
        self.assertEqual([issue for issue in issues if issue.level == "error"], [])
        self.assertEqual(entries[0].eid, "E-001")
        self.assertEqual(entries[0].tags, ("类型:分工",))

    def test_parse_keeps_normalized_text(self):
        entries, _ = parse_log("## E-001 | 1 | 类型:分工\n正文  \n\n", "Aster")
        self.assertEqual(entries[0].text, "正文")
        self.assertEqual(entries[0].norm_text, "正文")

    def test_bad_header_reports_error(self):
        entries, issues = parse_log("## E-001 | 1 | 类型:分工 | 多余字段\n正文", "Aster")
        self.assertEqual(entries, [])
        self.assertTrue(any(issue.level == "error" for issue in issues))

    def test_duplicate_eid_reports_error(self):
        text = "## E-001 | 1 | 类型:分工\n一\n## E-001 | 2 | 类型:分工\n二\n"
        entries, issues = parse_log(text, "Aster")
        self.assertEqual(len(entries), 2)
        self.assertTrue(any(issue.level == "error" for issue in issues))

    def test_empty_author_rejected(self):
        with self.assertRaises(ValueError):
            parse_log("## E-001 | 1 | 类型:分工\n正文", "  ")


@_NEEDS_ALGO
class MergeRulesTest(unittest.TestCase):
    """契约 §3 的四种裁决，是两个人并行开发时最容易理解偏差的地方。"""

    def _one(self, entries):
        result = merge(entries)
        self.assertEqual(len(result.items), 1)
        return result, result.items[0]

    def test_r0_confirmed_takes_longest_raw_text(self):
        short_text = "第一段\n\n第二段"
        long_text = "第一段\n\n\n第二段"
        result, item = self._one(
            [
                _entry("E-001", "Aster", 1, short_text),
                _entry("E-001", "Bramble", 2, long_text),
            ]
        )
        self.assertEqual(item.status, "confirmed")
        self.assertEqual(item.rule, "R0")
        self.assertEqual(item.text, long_text)
        self.assertEqual(result.conflicts, [])
        self.assertEqual(item.authors, ("Aster", "Bramble"))

    def test_r0_three_versions_is_not_a_conflict(self):
        result, item = self._one(
            [
                _entry("E-001", "Aster", 1, "同一件事"),
                _entry("E-001", "Bramble", 2, "同一件事"),
                _entry("E-001", "Cora", 3, "同一件事"),
            ]
        )
        self.assertEqual(item.status, "confirmed")
        self.assertEqual(item.rule, "R0")
        self.assertEqual(item.authors, ("Aster", "Bramble", "Cora"))
        self.assertEqual(result.conflicts, [])

    def test_r1_decision_beats_newer_clock(self):
        result, item = self._one(
            [
                _entry("E-003", "Aster", 1, "按决策执行", ("类型:决策",)),
                _entry("E-003", "Bramble", 5, "按时钟走", ("类型:实现",)),
            ]
        )
        self.assertEqual(item.status, "resolved")
        self.assertEqual(item.rule, "R1-决策优先")
        self.assertEqual(item.text, "按决策执行")
        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertEqual(conflict.resolution, "resolved")
        self.assertEqual(conflict.rule, "R1-决策优先")
        self.assertIsNotNone(conflict.winner)
        self.assertEqual(conflict.winner.author, "Aster")

    def test_r2_newer_clock_wins(self):
        result, item = self._one(
            [
                _entry("E-005", "Aster", 1, "旧版本"),
                _entry("E-005", "Bramble", 4, "新版本"),
            ]
        )
        self.assertEqual(item.status, "resolved")
        self.assertEqual(item.rule, "R2-时钟较新")
        self.assertEqual(item.text, "新版本")
        self.assertEqual(len(result.conflicts), 1)
        self.assertIsNotNone(result.conflicts[0].winner)
        self.assertEqual(result.conflicts[0].winner.author, "Bramble")

    def test_r3_equal_clocks_needs_review(self):
        result, item = self._one(
            [
                _entry("E-009", "Bramble", 3, "乙的说法"),
                _entry("E-009", "Aster", 3, "甲的说法"),
            ]
        )
        self.assertEqual(item.status, "needs_review")
        self.assertEqual(item.rule, "R3-无法裁决")
        self.assertIsNone(result.conflicts[0].winner)
        self.assertEqual(result.conflicts[0].resolution, "needs_review")
        self.assertIn("【Aster】", item.text)
        self.assertIn("【Bramble】", item.text)
        self.assertLess(item.text.index("Aster"), item.text.index("Bramble"))

    def test_single_version_is_not_a_conflict(self):
        result, item = self._one([_entry("E-004", "Bramble", 2, "只有一条")])
        self.assertEqual(item.status, "single")
        self.assertEqual(item.rule, "")
        self.assertEqual(result.conflicts, [])
        self.assertEqual(item.authors, ("Bramble",))

    def test_versions_sorted_by_author_then_clock(self):
        result, item = self._one(
            [
                _entry("E-009", "Bramble", 3, "乙"),
                _entry("E-009", "Aster", 3, "甲"),
            ]
        )
        self.assertEqual([entry.author for entry in item.versions], ["Aster", "Bramble"])
        self.assertEqual(
            [entry.author for entry in result.conflicts[0].versions], ["Aster", "Bramble"]
        )


@_NEEDS_ALGO
class MergeFingerprintTest(unittest.TestCase):
    """指纹与 JSON 形状必须可复现：这是"确定性合并"能被验证的关键。"""

    def _mixed_entries(self):
        return [
            _entry("E-001", "Aster", 1, "单条"),
            _entry("E-002", "Aster", 1, "确认"),
            _entry("E-002", "Bramble", 2, "确认"),
            _entry("E-003", "Aster", 1, "决策版", ("类型:决策",)),
            _entry("E-003", "Bramble", 2, "实现版"),
            _entry("E-004", "Aster", 2, "甲说"),
            _entry("E-004", "Bramble", 2, "乙说"),
        ]

    def test_fingerprint_order_independent(self):
        entries = self._mixed_entries()
        first = merge(entries)
        second = merge(list(reversed(entries)))
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual([item.eid for item in first.items], [item.eid for item in second.items])

    def test_items_sorted_by_eid_key(self):
        result = merge(self._mixed_entries())
        expected = sorted(result.items, key=lambda item: (eid_key(item.eid), item.authors))
        self.assertEqual([item.eid for item in result.items], [item.eid for item in expected])

    def test_fingerprint_matches_contract_payload(self):
        result = merge(self._mixed_entries())
        payload = {"version": 1, "items": [item.to_dict() for item in result.items]}
        self.assertEqual(result.fingerprint, fingerprint_of(payload))

    def test_stats_keys_and_consistency(self):
        result = merge(self._mixed_entries())
        expected_keys = {
            "total_items",
            "single",
            "confirmed",
            "resolved",
            "needs_review",
            "conflicts",
            "authors",
            "entries",
        }
        self.assertEqual(set(result.stats), expected_keys)
        self.assertTrue(all(isinstance(value, int) for value in result.stats.values()))
        stats = result.stats
        self.assertEqual(stats["total_items"], len(result.items))
        self.assertEqual(
            stats["single"] + stats["confirmed"] + stats["resolved"] + stats["needs_review"],
            stats["total_items"],
        )
        self.assertEqual(stats["conflicts"], len(result.conflicts))
        self.assertEqual(stats["entries"], 7)
        self.assertEqual(stats["authors"], 2)

    def test_to_dict_json_shape(self):
        result = merge(self._mixed_entries())
        payload = result.to_dict()
        self.assertEqual(payload["version"], 1)
        self.assertIn("fingerprint", payload)
        self.assertIn("stats", payload)
        self.assertIsInstance(payload["items"], list)
        for item in payload["items"]:
            self.assertEqual(
                set(item), {"eid", "authors", "tags", "status", "rule", "text"}
            )
            self.assertIsInstance(item["authors"], list)
            self.assertIsInstance(item["tags"], list)
        json.dumps(payload, ensure_ascii=False)


@_NEEDS_ALGO
class ProfileTest(unittest.TestCase):
    """协作画像的迁移边与占比是交付物里的"人"的部分。"""

    def _profile(self):
        entries = [
            _entry("E-010", "Aster", 1, "A 写", ("技能:SEL-1", "类型:实现")),
            _entry("E-011", "Bramble", 1, "B 用", ("技能:SEL-1", "类型:互检")),
            _entry("E-012", "Bramble", 2, "B 自己的", ("技能:SEL-2", "类型:实现")),
        ]
        items = merge(entries).items
        return build_profile(items, {"SEL-1": "Aster", "SEL-2": "Bramble"})

    def test_transfer_edge(self):
        prof = self._profile()
        self.assertEqual(prof.authors, ("Aster", "Bramble"))
        self.assertEqual(len(prof.transfers), 1)
        edge = prof.transfers[0]
        self.assertEqual((edge.src, edge.dst, edge.skill), ("Aster", "Bramble", "SEL-1"))
        self.assertEqual(tuple(edge.evidence), ("E-011",))

    def test_share_and_dict(self):
        prof = self._profile()
        self.assertAlmostEqual(prof.share["Aster"], 0.3333, places=4)
        self.assertAlmostEqual(prof.share["Bramble"], 0.6667, places=4)
        self.assertAlmostEqual(sum(prof.share.values()), 1.0, places=4)
        payload = prof.to_dict()
        for key in ("authors", "skill_tags", "type_tags", "transfers", "share"):
            self.assertIn(key, payload)
        self.assertEqual(payload["transfers"][0]["skill"], "SEL-1")


class RenderTest(unittest.TestCase):
    """渲染层单测用假对象，不依赖 Aster 的模块，便于先验收中文对齐。"""

    def setUp(self):
        self.result = _fake_result()
        self.prof = _fake_profile()

    def test_terminal_has_three_sections(self):
        text = render_terminal(self.result, self.prof, color=False)
        self.assertIn("概览", text)
        self.assertIn("冲突清单", text)
        self.assertIn("协作画像", text)

    def test_terminal_no_ansi_when_color_false(self):
        text = render_terminal(self.result, self.prof, color=False)
        self.assertNotIn("\x1b", text)

    def test_terminal_scrubs_escape_from_data(self):
        self.result.conflicts[0].note = "危险\x1b[31m文本"
        text = render_terminal(self.result, self.prof, color=False)
        self.assertNotIn("\x1b", text)

    def test_terminal_has_ansi_when_color_true(self):
        text = render_terminal(self.result, self.prof, color=True)
        self.assertIn("\x1b[", text)

    def test_terminal_has_no_trailing_newline(self):
        text = render_terminal(self.result, self.prof, color=False)
        self.assertFalse(text.endswith("\n"))
        self.assertFalse(text.endswith("\r"))

    def test_terminal_tables_aligned_by_display_width(self):
        text = render_terminal(self.result, self.prof, color=False)
        blocks = _table_blocks(text)
        self.assertGreaterEqual(len(blocks), 3)
        for block in blocks:
            widths = {display_width(line) for line in block}
            self.assertEqual(len(widths), 1, "表格行宽不一致：{0}".format(block))

    def test_tag_summary_counts_remaining_not_total(self):
        # 4 类只展示 3 类时，"等 N 类"必须是 1（剩余），不是 4（总数）。
        text = _fmt_tags({"实现": 2, "互检": 2, "决策": 1, "分工": 1})
        self.assertIn("决策×1 等 1 类", text)
        self.assertNotIn("、等", text)
        self.assertNotIn("等 4 类", text)

    def test_tag_summary_absent_at_exact_limit(self):
        # 恰好 3 类时全部展示，不能出现"等 0 类"。
        text = _fmt_tags({"A": 3, "B": 2, "C": 1})
        self.assertNotIn("等 ", text)

    def test_terminal_shows_rule_status_and_reason(self):
        text = render_terminal(self.result, self.prof, color=False)
        self.assertIn("R3-无法裁决", text)
        self.assertIn("needs_review", text)
        self.assertIn("没有决策标签", text)

    def test_terminal_flattens_multiline_note(self):
        # max_col 放宽到 60，避免长理由被截断后无法断言完整句子
        text = render_terminal(self.result, self.prof, color=False, max_col=60)
        self.assertIn("双方时钟相同， / 没有决策标签，无法裁决。", text)

    def test_terminal_truncates_to_max_col(self):
        text = render_terminal(self.result, self.prof, color=False, max_col=8)
        self.assertIn("…", text)

    def test_terminal_without_conflicts(self):
        self.result.conflicts = []
        self.result.stats["conflicts"] = 0
        text = render_terminal(self.result, self.prof, color=False)
        self.assertIn("（无冲突", text)

    def test_terminal_without_profile(self):
        text = render_terminal(self.result, None, color=False)
        self.assertIn("（未提供协作画像）", text)

    def test_markdown_sections(self):
        text = render_markdown(self.result, self.prof)
        for heading in ("## 概览", "## 冲突清单", "## 协作画像", "### 技能迁移"):
            self.assertIn(heading, text)
        self.assertIn("| 事件 | 裁决 | 规则 | 参与版本 | 理由 |", text)
        self.assertIn("| 作者 | 原始条目 | 占比 | 技能标签 | 类型标签 |", text)

    def test_markdown_has_fingerprint(self):
        text = render_markdown(self.result, self.prof)
        self.assertIn(self.result.fingerprint, text)
        self.assertIn("R3-无法裁决", text)

    def test_markdown_escapes_pipe_and_newline(self):
        self.result.conflicts[0].note = "甲|乙\n丙"
        text = render_markdown(self.result, self.prof)
        self.assertIn("甲\\|乙<br>丙", text)

    def test_markdown_no_ansi(self):
        text = render_markdown(self.result, self.prof)
        self.assertNotIn("\x1b", text)

    def test_markdown_scrubs_escape_from_data(self):
        self.result.conflicts[0].note = "危险\x1b[31m文本"
        text = render_markdown(self.result, self.prof)
        self.assertNotIn("\x1b", text)

    def test_markdown_review_callout(self):
        text = render_markdown(self.result, self.prof)
        self.assertIn("需要人工复核", text)
        self.assertIn("E-006", text)


@_NEEDS_CLI
class CliTest(unittest.TestCase):
    """退出码与 stdout 洁净度是契约 §9 的硬接口，必须走真实子进程验证。"""

    def _run_cli(self, *args, cwd=None):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONPATH"] = _ROOT + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "duolog"] + list(args),
            cwd=cwd or _ROOT,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    def _merge_args(self, *extra):
        return ("merge", "--a", _SAMPLE_A, "--b", _SAMPLE_B) + extra

    def test_selfcheck_ok(self):
        proc = self._run_cli("selfcheck")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("selfcheck: ok "))
        self.assertNotIn("\x1b", proc.stdout)

    def test_selfcheck_ignores_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run_cli("selfcheck", cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_help_lists_subcommands(self):
        proc = self._run_cli("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("merge", proc.stdout)
        self.assertIn("selfcheck", proc.stdout)

    def test_json_is_clean(self):
        proc = self._run_cli(*self._merge_args("--json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("\x1b", proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["stats"]["total_items"], len(payload["items"]))
        for item in payload["items"]:
            self.assertNotIn("versions", item)

    def test_strict_with_needs_review_returns_1(self):
        proc = self._run_cli(*self._merge_args("--json", "--strict"))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertGreaterEqual(payload["stats"]["needs_review"], 1)

    def test_without_strict_returns_0(self):
        proc = self._run_cli(*self._merge_args("--json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_input_file_returns_2(self):
        missing = os.path.join(_EXAMPLES, "does_not_exist.md")
        proc = self._run_cli("merge", "--a", missing, "--b", _SAMPLE_B)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("无法读取", proc.stderr)

    def test_missing_required_option_returns_2(self):
        proc = self._run_cli("merge", "--a", _SAMPLE_A)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--b", proc.stderr)

    def test_no_color_has_no_ansi(self):
        proc = self._run_cli(*self._merge_args("--no-color"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("\x1b", proc.stdout)
        self.assertIn("概览", proc.stdout)

    def test_out_roundtrips_through_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "merged.md")
            proc = self._run_cli(*self._merge_args("--out", out_path, "--json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = _read(out_path)
        entries, issues = parse_log(text, "merged")
        errors = [issue for issue in issues if issue.level == "error"]
        self.assertEqual(errors, [])
        payload = json.loads(proc.stdout)
        self.assertEqual(len(entries), payload["stats"]["total_items"])
        self.assertIn(payload["fingerprint"], text)

    def test_report_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = os.path.join(tmp, "report.md")
            proc = self._run_cli(*self._merge_args("--report", report_path, "--json"))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = _read(report_path)
        self.assertIn("# duolog 协作日志合并报告", text)
        self.assertIn("## 概览", text)
        self.assertIn("## 冲突清单", text)
        self.assertIn("## 协作画像", text)
        self.assertNotIn("\x1b", text)

    def test_parse_error_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = os.path.join(tmp, "bad.md")
            with open(bad_path, "w", encoding="utf-8") as handle:
                handle.write("## E-001 | 1 | 类型:分工 | 多余字段\n正文\n")
            proc = self._run_cli("merge", "--a", bad_path, "--b", _SAMPLE_B, "--json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("解析出现 error", proc.stderr)

    def test_parse_issues_reported_before_read_failure(self):
        # 前一个文件的坏表头必须先于后一个文件的"读不了"出现在 stderr：
        # 否则用户只能看到次要错误，根因被吞掉。退出码仍为 2。
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = os.path.join(tmp, "bad.md")
            missing_path = os.path.join(tmp, "nope.md")
            with open(bad_path, "w", encoding="utf-8") as handle:
                handle.write("## BAD HEADER\n正文\n")
            proc = self._run_cli("merge", "--a", bad_path, "--b", missing_path)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("条目标题格式不合法", proc.stderr)
        self.assertIn("无法读取输入文件", proc.stderr)
        self.assertLess(
            proc.stderr.index("条目标题格式不合法"),
            proc.stderr.index("无法读取输入文件"),
            "坏表头告警必须排在读文件错误之前",
        )

    def test_out_relative_to_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run_cli(*self._merge_args("--out", "merged.md", "--json"), cwd=tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "merged.md")))


if __name__ == "__main__":
    unittest.main()
