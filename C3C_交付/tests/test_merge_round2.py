"""第二轮 SEL-1 迁移测试：R4-补充合并 与 契约 §3.1 标签语义（v1.3）。

为什么单独一个文件：第一轮的 ``test_duolog.py`` 已被主持人用于验收
v1.0 契约，保持它不动才能确认"新改动没有破坏旧行为"；第二轮新增的
规则（R4）与标签语义（v1.3）在这里独立断言，失败时能立刻定位到本轮。

运行方式::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from duolog.merge import merge  # noqa: E402
from duolog.model import Entry, fingerprint_of  # noqa: E402


def _entry(eid, author, clock, text, tags=()):
    """直接构造 Entry，精确控制原始正文与标签，绕开 parse_log 的规范化。"""
    return Entry(eid=eid, author=author, clock=clock, tags=tuple(tags), text=text, line=1)


def _only_item(result):
    if len(result.items) != 1:
        raise AssertionError("期望恰好一个合并条目，实际 %d 个" % len(result.items))
    return result.items[0]


class R4RuleTest(unittest.TestCase):
    """R4：一方规范化正文按行**严格包含**另一方时取更完整者。"""

    def test_r4_hit_when_longer_covers_shorter_by_lines(self):
        result = merge(
            [
                _entry("E-101", "Aster", 1, "实现登录"),
                _entry("E-101", "Bramble", 1, "实现登录\n补充失败重试"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "resolved")
        self.assertEqual(item.rule, "R4-补充合并")
        self.assertEqual(item.text, "实现登录\n补充失败重试")
        self.assertEqual(result.stats["conflicts"], 1)
        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertIsNotNone(conflict.winner)
        self.assertEqual(conflict.winner.author, "Bramble")
        self.assertEqual(conflict.rule, "R4-补充合并")
        self.assertEqual(conflict.resolution, "resolved")

    def test_r4_hit_when_extra_line_in_middle(self):
        result = merge(
            [
                _entry("E-102", "Aster", 1, "第一段\n第三段"),
                _entry("E-102", "Bramble", 1, "第一段\n第二段\n第三段"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.rule, "R4-补充合并")
        self.assertEqual(item.text, "第一段\n第二段\n第三段")

    def test_r4_requires_line_order(self):
        # 行集合相同/局部命中都不够，必须"按顺序整体出现"。
        result = merge(
            [
                _entry("E-103", "Aster", 1, "第三段\n第一段"),
                _entry("E-103", "Bramble", 1, "第一段\n第二段\n第三段"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "needs_review")
        self.assertEqual(item.rule, "R3-无法裁决")

    def test_r4_substring_but_not_whole_line_is_not_hit(self):
        # "实现" 是 "实现细节" 的子串，但不是整行；两个方向都必须判不命中。
        for first, second in (("实现", "实现细节"), ("实现细节", "实现")):
            with self.subTest(first=first, second=second):
                result = merge(
                    [
                        _entry("E-104", "Aster", 1, first),
                        _entry("E-104", "Bramble", 1, second),
                    ]
                )
                item = _only_item(result)
                self.assertEqual(item.status, "needs_review")
                self.assertEqual(item.rule, "R3-无法裁决")
                self.assertIsNone(result.conflicts[0].winner)

    def test_r4_three_versions_unique_cover(self):
        result = merge(
            [
                _entry("E-105", "Aster", 1, "a\nb\nc"),
                _entry("E-105", "Bramble", 1, "a\nb"),
                _entry("E-105", "Cora", 1, "b\nc"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.rule, "R4-补充合并")
        self.assertEqual(item.text, "a\nb\nc")
        self.assertEqual(result.conflicts[0].winner.author, "Aster")

    def test_r4_three_versions_partial_coverage_falls_to_r3(self):
        # 只覆盖了一部分版本，说明还有独立说法，R4 不能替人吞掉。
        result = merge(
            [
                _entry("E-106", "Aster", 1, "a\nb\nc"),
                _entry("E-106", "Bramble", 1, "a\nb"),
                _entry("E-106", "Cora", 1, "x"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "needs_review")
        self.assertEqual(item.rule, "R3-无法裁决")


class RulePriorityTest(unittest.TestCase):
    """执行顺序 R0 → R1 → R2 → R4 → R3 必须严格成立。"""

    def test_r0_precedes_r4(self):
        result = merge(
            [
                _entry("E-111", "Aster", 1, "同一句话"),
                _entry("E-111", "Bramble", 2, "同一句话"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "confirmed")
        self.assertEqual(item.rule, "R0")
        self.assertEqual(result.conflicts, [])

    def test_r1_decision_precedes_r4(self):
        # 决策版更短，若 R4 抢先，长版本会赢；契约要求 R1 先命中。
        result = merge(
            [
                _entry("E-112", "Aster", 1, "先做最小实现", ("类型:决策",)),
                _entry("E-112", "Bramble", 1, "先做最小实现\n再补测试", ("类型:实现",)),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "resolved")
        self.assertEqual(item.rule, "R1-决策优先")
        self.assertEqual(item.text, "先做最小实现")
        self.assertEqual(item.authors, ("Aster", "Bramble"))

    def test_r2_clock_precedes_r4(self):
        # 时钟较新的是短版本；若 R4 抢先，更完整的长版本会赢。
        result = merge(
            [
                _entry("E-113", "Aster", 3, "先做最小实现", ("类型:实现",)),
                _entry("E-113", "Bramble", 1, "先做最小实现\n再补测试", ("类型:方案",)),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "resolved")
        self.assertEqual(item.rule, "R2-时钟较新")
        self.assertEqual(item.text, "先做最小实现")
        # v1.3：类型跟 R2 的终裁版本（Aster），不是更长的那版。
        self.assertEqual(item.tags, ("类型:实现",))

    def test_r3_still_reachable(self):
        result = merge(
            [
                _entry("E-114", "Aster", 2, "甲的说法"),
                _entry("E-114", "Bramble", 2, "乙的说法"),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "needs_review")
        self.assertEqual(item.rule, "R3-无法裁决")
        self.assertIsNone(result.conflicts[0].winner)
        self.assertIn("【Aster】", item.text)
        self.assertIn("【Bramble】", item.text)


class TagSemanticsTest(unittest.TestCase):
    """v1.3：技能并集、类型跟终裁版本。"""

    def test_resolved_types_follow_winner_skills_union(self):
        result = merge(
            [
                _entry("E-121", "Aster", 1, "方案 A", ("类型:决策", "技能:SEL-1")),
                _entry("E-121", "Bramble", 1, "方案 B", ("类型:实现", "技能:SEL-2")),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.rule, "R1-决策优先")
        self.assertEqual(
            item.tags, ("技能:SEL-1", "技能:SEL-2", "类型:决策")
        )
        self.assertNotIn("类型:实现", item.tags)

    def test_r4_types_follow_winner(self):
        result = merge(
            [
                _entry("E-122", "Aster", 1, "基础实现", ("类型:实现", "技能:SEL-1")),
                _entry("E-122", "Bramble", 1, "基础实现\n补充边界", ("类型:方案", "技能:SEL-2")),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.rule, "R4-补充合并")
        self.assertEqual(
            item.tags, ("技能:SEL-1", "技能:SEL-2", "类型:方案")
        )
        self.assertNotIn("类型:实现", item.tags)

    def test_r3_types_union_and_skills_union(self):
        result = merge(
            [
                _entry("E-123", "Aster", 2, "甲说", ("类型:实现", "技能:SEL-1")),
                _entry("E-123", "Bramble", 2, "乙说", ("类型:互检", "技能:SEL-2")),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.rule, "R3-无法裁决")
        self.assertEqual(set(item.tags), {"类型:实现", "类型:互检", "技能:SEL-1", "技能:SEL-2"})
        self.assertEqual(list(item.tags), sorted(item.tags))

    def test_confirmed_types_union(self):
        result = merge(
            [
                _entry("E-124", "Aster", 1, "确认", ("类型:分工",)),
                _entry("E-124", "Bramble", 2, "确认 ", ("类型:互检",)),
            ]
        )
        item = _only_item(result)
        self.assertEqual(item.status, "confirmed")
        self.assertEqual(item.rule, "R0")
        self.assertEqual(set(item.tags), {"类型:分工", "类型:互检"})

    def test_single_keeps_its_tags(self):
        result = merge([_entry("E-125", "Bramble", 1, "只有一条", ("技能:SEL-2", "类型:实现"))])
        item = _only_item(result)
        self.assertEqual(item.status, "single")
        self.assertEqual(item.tags, ("技能:SEL-2", "类型:实现"))

    def test_tags_sorted_and_deduplicated(self):
        result = merge(
            [
                _entry("E-126", "Aster", 1, "决策版", ("类型:决策", "技能:SEL-1")),
                _entry("E-126", "Bramble", 1, "实现版", ("类型:实现", "技能:SEL-1")),
            ]
        )
        item = _only_item(result)
        self.assertEqual(list(item.tags), sorted(set(item.tags)))
        self.assertEqual(item.tags.count("技能:SEL-1"), 1)


class DeterminismAndStatsTest(unittest.TestCase):
    """改标签、加 R4 之后，指纹与 stats 的契约不能变。"""

    def _entries(self):
        return [
            _entry("E-201", "Aster", 1, "单条", ("类型:分工",)),
            _entry("E-202", "Aster", 1, "确认", ("类型:分工",)),
            _entry("E-202", "Bramble", 2, "确认 ", ("类型:互检",)),
            _entry("E-203", "Aster", 1, "基础", ("类型:实现", "技能:SEL-1")),
            _entry("E-203", "Bramble", 1, "基础\n补充", ("类型:方案", "技能:SEL-2")),
            _entry("E-204", "Aster", 2, "甲说", ("类型:实现",)),
            _entry("E-204", "Bramble", 2, "乙说", ("类型:互检",)),
            _entry("E-205", "Aster", 1, "决策版", ("类型:决策",)),
            _entry("E-205", "Bramble", 2, "实现版", ("类型:实现",)),
        ]

    def test_fingerprint_order_independent(self):
        entries = self._entries()
        first = merge(entries)
        second = merge(list(reversed(entries)))
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual([item.eid for item in first.items], [item.eid for item in second.items])
        self.assertEqual([item.tags for item in first.items], [item.tags for item in second.items])

    def test_fingerprint_matches_contract_payload(self):
        result = merge(self._entries())
        payload = {"version": 1, "items": [item.to_dict() for item in result.items]}
        self.assertEqual(result.fingerprint, fingerprint_of(payload))

    def test_stats_unchanged(self):
        result = merge(self._entries())
        self.assertEqual(
            set(result.stats),
            {
                "total_items",
                "single",
                "confirmed",
                "resolved",
                "needs_review",
                "conflicts",
                "authors",
                "entries",
            },
        )
        self.assertEqual(result.stats["total_items"], 5)
        self.assertEqual(result.stats["single"], 1)
        self.assertEqual(result.stats["confirmed"], 1)
        self.assertEqual(result.stats["resolved"], 2)   # R4 + R1
        self.assertEqual(result.stats["needs_review"], 1)
        self.assertEqual(result.stats["conflicts"], 3)  # R4 + R3 + R1
        self.assertEqual(result.stats["authors"], 2)
        self.assertEqual(result.stats["entries"], 9)

    def test_conflict_rules_include_r4(self):
        result = merge(self._entries())
        rules = {conflict.eid: conflict.rule for conflict in result.conflicts}
        self.assertEqual(
            rules,
            {
                "E-203": "R4-补充合并",
                "E-204": "R3-无法裁决",
                "E-205": "R1-决策优先",
            },
        )
        self.assertEqual(result.stats["conflicts"], len(result.conflicts))


if __name__ == "__main__":
    unittest.main()
