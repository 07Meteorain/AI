"""离线站点导出测试。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall.model import Card  # noqa: E402
from recall.store import apply_decisions, connect, upsert_cards  # noqa: E402
from recall.web import render_site  # noqa: E402


def card(card_id: str = "c1") -> Card:
    return Card(
        id=card_id,
        kind="definition",
        prompt="什么是缓存？",
        answer="缓存是把结果暂存起来以便复用的机制。",
        source="notes/a.md",
        heading="概念",
        line=7,
        confidence=0.8,
        tags=("示例",),
    )


class TestWeb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = connect(os.path.join(self.tmp.name, "t.db"))
        self.addCleanup(self.conn.close)
        upsert_cards(self.conn, [card(), card("c2")])

    def render(self, **kwargs):
        out = os.path.join(self.tmp.name, "site")
        return render_site(self.conn, out, **kwargs), out

    def test_files_created(self):
        result, out = self.render()
        for name in ("index.html", "styles.css", "lib.js", "app.js", "deck.js", "vectors.js", "selftest.html", "selftest.js"):
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        self.assertEqual(result["cards"], 2)

    def test_deck_payload(self):
        _, out = self.render()
        text = Path(out, "deck.js").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("window.RECALL_DECK = "))
        payload = json.loads(text[len("window.RECALL_DECK = "):].rstrip().rstrip(";"))
        self.assertEqual(len(payload["cards"]), 2)
        self.assertEqual(payload["cards"][0]["source"], "notes/a.md")
        self.assertEqual(payload["app_version"], "1.0.0")

    def test_vectors_payload(self):
        _, out = self.render()
        text = Path(out, "vectors.js").read_text(encoding="utf-8")
        vectors = json.loads(text[len("window.RECALL_VECTORS = "):].rstrip().rstrip(";"))
        self.assertTrue(any(v["name"] == "new-good-x4" for v in vectors))

    def test_index_contract(self):
        _, out = self.render()
        html = Path(out, "index.html").read_text(encoding="utf-8")
        for marker in ("deck.js", "lib.js", "app.js", "card-prompt", "study-tip", "selftest.html"):
            self.assertIn(marker, html)

    def test_title_override(self):
        _, out = self.render(title="我的卡组")
        html = Path(out, "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>我的卡组</title>", html)

    def test_only_approved_by_default(self):
        apply_decisions(self.conn, rejected=["c2"])
        result, out = self.render()
        self.assertEqual(result["cards"], 1)
        text = Path(out, "deck.js").read_text(encoding="utf-8")
        self.assertNotIn("c2", text)
        self.assertIn("c1", text)

    def test_empty_deck_still_renders(self):
        apply_decisions(self.conn, rejected=["c1", "c2"])
        result, out = self.render()
        self.assertEqual(result["cards"], 0)
        self.assertTrue(os.path.isfile(os.path.join(out, "index.html")))

    def test_script_close_is_escaped(self):
        upsert_cards(
            self.conn,
            [
                Card(
                    id="x1",
                    kind="definition",
                    prompt="什么是 </script> 注入？",
                    answer="卡片正文里出现结束标签时不能被当成 HTML 执行。",
                    source="a.md",
                    heading="h",
                    line=1,
                    confidence=0.8,
                )
            ],
        )
        _, out = self.render()
        text = Path(out, "deck.js").read_text(encoding="utf-8")
        self.assertNotIn("</script>", text)
        self.assertIn("<\\/script>", text)


if __name__ == "__main__":
    unittest.main()
