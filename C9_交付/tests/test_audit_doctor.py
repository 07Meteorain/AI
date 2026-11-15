"""抽样审核与笔记诊断测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall.audit import render_audit_markdown, sample_cards  # noqa: E402
from recall.doctor import diagnose_path, render_report  # noqa: E402
from recall.generate import Options  # noqa: E402
from recall.model import Card  # noqa: E402

EXAMPLES = ROOT / "examples" / "notes"


def card(index: int, kind: str = "definition") -> Card:
    return Card(
        id="c{:02d}".format(index),
        kind=kind,
        prompt="问题 {}？".format(index),
        answer="答案 {}，足够长以便展示。".format(index),
        source="a.md",
        heading="h",
        line=index,
        confidence=0.8,
    )


class TestAudit(unittest.TestCase):
    def test_sample_deterministic(self):
        cards = [card(i) for i in range(20)]
        first = [c.id for c in sample_cards(cards, n=5, seed=7)]
        second = [c.id for c in sample_cards(cards, n=5, seed=7)]
        self.assertEqual(first, second)
        self.assertNotEqual(first, [c.id for c in sample_cards(cards, n=5, seed=8)])

    def test_sample_larger_than_pool(self):
        cards = [card(i) for i in range(3)]
        self.assertEqual(len(sample_cards(cards, n=30)), 3)

    def test_sample_kinds_filter(self):
        cards = [card(1, "definition"), card(2, "cloze"), card(3, "cloze")]
        result = sample_cards(cards, n=10, kinds=["cloze"])
        self.assertEqual([c.kind for c in result], ["cloze", "cloze"])

    def test_render_markdown(self):
        cards = [card(1), card(2, "cloze")]
        text = render_audit_markdown(cards, seed=7, generated="2026-11-15")
        self.assertIn("# Recall 抽样审核", text)
        self.assertIn("| # | 类型 | 问题 |", text)
        self.assertIn("| 1 |", text)
        self.assertIn("| 2 |", text)
        self.assertIn("总计：2 张", text)
        self.assertIn("随机种子 `7`", text)

    def test_render_escapes_pipe(self):
        bad = card(1)
        bad.prompt = "A | B 的问题？"
        text = render_audit_markdown([bad])
        self.assertIn("A \\| B", text)

    def test_render_empty(self):
        text = render_audit_markdown([])
        self.assertIn("总计：0 张", text)


class TestDoctor(unittest.TestCase):
    def test_examples_diagnosis(self):
        diagnoses = diagnose_path(str(EXAMPLES))
        self.assertEqual(len(diagnoses), 3)
        self.assertTrue(all(item.score >= 40 for item in diagnoses))
        self.assertTrue(any(item.cards >= 10 for item in diagnoses))
        self.assertTrue(all(item.words > 0 for item in diagnoses))

    def test_low_score_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "plain.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# 一篇没有结构的笔记\n\n就是一段普通的文字，没有列表，也没有术语和问句标题。\n")
            diagnoses = diagnose_path(path)
        self.assertEqual(len(diagnoses), 1)
        self.assertLess(diagnoses[0].score, 60)
        self.assertTrue(diagnoses[0].issues)
        self.assertEqual(diagnoses[0].cards, 0)

    def test_report(self):
        diagnoses = diagnose_path(str(EXAMPLES))
        text = render_report(diagnoses)
        self.assertTrue(text.startswith("# 笔记可出卡性诊断"))
        self.assertIn("| 笔记 | 字数 |", text)
        self.assertIn("01-rag-basics.md", text)

    def test_report_empty(self):
        self.assertIn("没有找到", render_report([]))

    def test_diagnosis_dict(self):
        item = diagnose_path(str(EXAMPLES), Options())[0]
        data = item.to_dict()
        for key in ("source", "words", "sections", "list_items", "bold_terms", "cards", "score", "issues"):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
