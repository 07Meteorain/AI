"""候选抽取与质量门测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall.generate import (  # noqa: E402
    Gate,
    Options,
    build_deck,
    generate_from_note,
    rule_cloze,
    rule_explicit_qa,
    rule_gist,
    rule_heading_question,
    rule_inline_definition,
    rule_term_list,
)
from recall.mdparse import parse_note  # noqa: E402
from recall.model import Card, make_id  # noqa: E402

from typing import Optional  # noqa: E402

EXAMPLES = ROOT / "examples" / "notes"


def write_notes(files: dict, base: str) -> None:
    for name, text in files.items():
        path = os.path.join(base, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


class NoteCase(unittest.TestCase):
    def note(self, text: str):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = os.path.join(self._tmp.name, "n.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return parse_note(path)


class TestRules(NoteCase):
    def test_term_list(self):
        note = self.note("## 术语\n\n- **切分**：把长文档拆成片段。\n- **召回**：从索引里找相关片段。\n")
        cards = rule_term_list(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].prompt, "「切分」是什么？")
        self.assertEqual(cards[0].answer, "把长文档拆成片段。")
        self.assertEqual(cards[0].line, 3)
        self.assertEqual(cards[1].line, 4)

    def test_heading_question(self):
        note = self.note("## 什么是 RAG？\n\nRAG 是检索增强生成，先取回材料再回答。\n")
        cards = rule_heading_question(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].kind, "heading-question")
        self.assertTrue(cards[0].prompt.endswith("？"))
        self.assertIn("检索增强生成", cards[0].answer)

    def test_heading_not_question(self):
        note = self.note("## 原理\n\nRAG 是检索增强生成，先取回材料再回答。\n")
        self.assertEqual(rule_heading_question(note, note.sections[0], Options(), set()), [])

    def test_explicit_qa_same_line(self):
        note = self.note("## 问答\n\n问：RAG 能消除幻觉吗？答：不能完全消除，但能降低概率。\n")
        cards = rule_explicit_qa(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].prompt, "RAG 能消除幻觉吗？")
        self.assertIn("不能完全消除", cards[0].answer)

    def test_explicit_qa_newline(self):
        note = self.note("## 问答\n\n问：什么是召回？\n答：从索引里取回相关片段。\n")
        cards = rule_explicit_qa(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].answer, "从索引里取回相关片段。")

    def test_inline_definition(self):
        note = self.note("## 概念\n\n**缓存**是指把计算结果暂存起来，以便下次直接复用。\n")
        cards = rule_inline_definition(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].prompt, "「缓存」是什么？")
        self.assertTrue(cards[0].answer.startswith("把计算结果暂存"))

    def test_cloze(self):
        note = self.note("## 原理\n\n缓存的核心是**用空间换时间**，把重复计算的结果存起来，避免重复计算。\n")
        cards = rule_cloze(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 1)
        self.assertIn("____", cards[0].prompt)
        self.assertEqual(cards[0].answer, "用空间换时间")

    def test_cloze_short_term_still_allowed(self):
        note = self.note("## 方法\n\n这个方法的要点是把**重复**的步骤合并起来，减少无效的来回切换，从而节省很多时间。\n")
        cards = rule_cloze(note, note.sections[0], Options(), set())
        self.assertTrue(cards)
        self.assertEqual(cards[0].answer, "重复")

    def test_gist_disabled_by_default(self):
        note = self.note("## 原理\n\n" + "这是一段足够长的正文，用来说明这一节到底在讲什么。" * 3 + "\n")
        self.assertEqual(rule_gist(note, note.sections[0], Options(), set()), [])

    def test_gist_when_enabled(self):
        note = self.note("## 原理\n\n" + "这是一段足够长的正文，用来说明这一节到底在讲什么。" * 3 + "\n")
        cards = rule_gist(note, note.sections[0], Options(include_gist=True), set())
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].kind, "gist")

    def test_noise_paragraph_skipped(self):
        note = self.note(
            "## 什么是测试？\n\nCookie 设置：我们使用 Cookie 改善体验，点击同意继续浏览本站内容。\n\n"
            "测试是验证断言是否成立的过程，它需要可重复的输入与明确的判定标准。\n"
        )
        cards = rule_heading_question(note, note.sections[0], Options(), set())
        self.assertEqual(len(cards), 1)
        self.assertNotIn("Cookie", cards[0].answer)

    def test_code_and_table_not_used(self):
        note = self.note("## 代码\n\n```py\ndef f():\n    return 1\n```\n\n| a | b |\n| - | - |\n")
        cards = generate_from_note(note, Options())
        self.assertEqual(cards, [])


class TestBuild(unittest.TestCase):
    def build(self, files: dict, opts: Optional[Options] = None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_notes(files, tmp.name)
        return build_deck(tmp.name, opts or Options(), generated="2026-01-01")

    def test_examples_deck(self):
        result = build_deck(str(EXAMPLES), Options(), generated="2026-01-01")
        self.assertGreaterEqual(len(result.cards), 15)
        kinds = {card.kind for card in result.cards}
        self.assertIn("term-list", kinds)
        self.assertIn("heading-question", kinds)
        self.assertIn("explicit-qa", kinds)
        for card in result.cards:
            self.assertEqual(len(card.id), 16)
            self.assertTrue(card.source.endswith(".md"))
            self.assertGreater(card.line, 0)
            self.assertEqual(card.status, "approved")
            self.assertEqual(card.created, "2026-01-01")

    def test_ids_are_stable(self):
        first = build_deck(str(EXAMPLES), Options()).cards
        second = build_deck(str(EXAMPLES), Options()).cards
        self.assertEqual([c.id for c in first], [c.id for c in second])

    def test_duplicate_prompt_across_files(self):
        result = self.build(
            {
                "a.md": "## 什么是缓存？\n\n缓存是把结果暂存起来以便复用的一种机制。\n",
                "b.md": "## 什么是缓存？\n\n缓存也可以理解为用空间换时间的做法，把昂贵的结果存下来复用。\n",
            }
        )
        self.assertEqual(len(result.cards), 1)
        self.assertGreaterEqual(result.stats.rejected.get("duplicate-prompt", 0), 1)

    def test_kinds_filter(self):
        result = self.build(
            {"a.md": "## 什么是缓存？\n\n缓存是把结果暂存起来以便复用的机制。\n\n- **命中率**：命中次数除以总查询次数。\n"},
            Options(kinds=("term-list",)),
        )
        self.assertTrue(result.cards)
        self.assertTrue(all(card.kind == "term-list" for card in result.cards))

    def test_max_per_file(self):
        items = "\n".join("- **术语{}**：这是第{}个术语的解释文本。".format(i, i) for i in range(10))
        result = self.build({"a.md": "## 术语\n\n" + items + "\n"}, Options(max_per_file=3))
        self.assertEqual(len(result.cards), 3)

    def test_stats_shape(self):
        result = self.build({"a.md": "## 什么是缓存？\n\n缓存是把结果暂存起来以便复用的机制。\n"})
        stats = result.stats.to_dict()
        self.assertEqual(stats["files"], 1)
        self.assertEqual(stats["accepted"], len(result.cards))
        self.assertIn("by_kind", stats)


class TestGate(unittest.TestCase):
    def card(self, **kwargs):
        base = dict(
            id=make_id("a.md", "definition", "什么是缓存？"),
            kind="definition",
            prompt="什么是缓存？",
            answer="缓存是把结果暂存起来以便复用的机制。",
            source="a.md",
            heading="概念",
            line=1,
            confidence=0.8,
        )
        base.update(kwargs)
        return Card(**base)

    def test_accepts_good_card(self):
        self.assertIsNone(Gate(0.5).check(self.card()))

    def test_rejects_url(self):
        gate = Gate(0.5)
        self.assertEqual(gate.check(self.card(answer="详见 https://example.com 的说明文字。")), "format")

    def test_rejects_duplicate_prompt(self):
        gate = Gate(0.5)
        self.assertIsNone(gate.check(self.card()))
        self.assertEqual(gate.check(self.card()), "duplicate-prompt")

    def test_rejects_duplicate_long_answer(self):
        gate = Gate(0.5)
        long_answer = "缓存是把结果暂存起来以便复用的机制，它用空间换时间，能显著减少重复计算带来的等待。" * 2
        self.assertIsNone(gate.check(self.card(answer=long_answer)))
        other = self.card(id="x", prompt="缓存的定义是什么？", answer=long_answer)
        self.assertEqual(gate.check(other), "duplicate-answer")

    def test_rejects_low_confidence(self):
        self.assertEqual(Gate(0.9).check(self.card(confidence=0.6)), "low-confidence")

    def test_rejects_thin_answer(self):
        self.assertEqual(Gate(0.5).check(self.card(answer="是。")), "answer-length")

    def test_rejects_boilerplate(self):
        self.assertEqual(
            Gate(0.5).check(self.card(answer="本文档由机器翻译生成，仅供内部参考使用。")),
            "boilerplate",
        )

    def test_cloze_allows_short_answer(self):
        card = self.card(kind="cloze", prompt="填空：缓存的关键是____。", answer="复用")
        self.assertIsNone(Gate(0.5).check(card))


if __name__ == "__main__":
    unittest.main()
