"""SQLite 存储测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall.model import Card  # noqa: E402
from recall.scheduler import State, review  # noqa: E402
from recall.store import (  # noqa: E402
    apply_decisions,
    connect,
    export_payload,
    get_card,
    get_meta,
    list_cards,
    next_due_preview,
    record_review,
    set_meta,
    states_for,
    stats,
    upsert_cards,
)


def make_card(card_id: str = "c1", **kwargs) -> Card:
    data = dict(
        id=card_id,
        kind="definition",
        prompt="什么是缓存？",
        answer="缓存是把结果暂存起来以便复用的机制。",
        source="a.md",
        heading="概念",
        line=3,
        confidence=0.8,
        tags=("示例",),
        status="approved",
        created="2026-01-01",
    )
    data.update(kwargs)
    return Card(**data)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.conn = connect(self.db)
        self.addCleanup(self.conn.close)

    def test_schema_version(self):
        self.assertEqual(get_meta(self.conn, "schema_version"), "1")

    def test_meta_roundtrip(self):
        set_meta(self.conn, "k", "v")
        self.assertEqual(get_meta(self.conn, "k"), "v")

    def test_insert_and_read(self):
        inserted, updated = upsert_cards(self.conn, [make_card()])
        self.assertEqual((inserted, updated), (1, 0))
        card = get_card(self.conn, "c1")
        self.assertIsNotNone(card)
        self.assertEqual(card.tags, ("示例",))
        self.assertEqual(card.status, "approved")

    def test_upsert_preserves_status(self):
        upsert_cards(self.conn, [make_card()])
        apply_decisions(self.conn, rejected=["c1"])
        inserted, updated = upsert_cards(self.conn, [make_card(answer="新的答案内容，足够长。")])
        self.assertEqual((inserted, updated), (0, 1))
        card = get_card(self.conn, "c1")
        self.assertEqual(card.status, "rejected")
        self.assertEqual(card.answer, "新的答案内容，足够长。")

    def test_list_filters(self):
        upsert_cards(self.conn, [make_card("a"), make_card("b", kind="cloze")])
        apply_decisions(self.conn, rejected=["b"])
        self.assertEqual([c.id for c in list_cards(self.conn)], ["a", "b"])
        self.assertEqual([c.id for c in list_cards(self.conn, status="rejected")], ["b"])
        self.assertEqual([c.id for c in list_cards(self.conn, kinds=["cloze"])], ["b"])

    def test_record_review_and_stats(self):
        upsert_cards(self.conn, [make_card()])
        state = review(State(), 3, date(2026, 1, 1))
        record_review(self.conn, "c1", 3, state, "2026-01-01")
        states = states_for(self.conn)
        self.assertEqual(states["c1"].due, "2026-01-02")
        data = stats(self.conn, "2026-01-02")
        self.assertEqual(data["due"], 1)
        self.assertEqual(data["reviewed_today"], 0)
        data = stats(self.conn, "2026-01-01")
        self.assertEqual(data["reviewed_today"], 1)
        self.assertEqual(data["due"], 0)

    def test_stats_new(self):
        upsert_cards(self.conn, [make_card("a"), make_card("b")])
        data = stats(self.conn, "2026-01-01")
        self.assertEqual(data["new"], 2)
        self.assertEqual(data["approved"], 2)
        self.assertEqual(data["total"], 2)

    def test_apply_decisions_counts(self):
        upsert_cards(self.conn, [make_card("a"), make_card("b")])
        result = apply_decisions(self.conn, approved=["a", "missing"], rejected=["b"])
        self.assertEqual(result, {"approved": 1, "rejected": 1, "missing": 1})

    def test_export_payload(self):
        upsert_cards(self.conn, [make_card()])
        state = review(State(), 3, date(2026, 1, 1))
        record_review(self.conn, "c1", 3, state, "2026-01-01")
        payload = export_payload(self.conn)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(payload["cards"]), 1)
        self.assertIn("state", payload["cards"][0])
        self.assertEqual(payload["cards"][0]["state"]["due"], "2026-01-02")

    def test_export_only_approved(self):
        upsert_cards(self.conn, [make_card("a"), make_card("b")])
        apply_decisions(self.conn, rejected=["b"])
        self.assertEqual([c["id"] for c in export_payload(self.conn)["cards"]], ["a"])
        self.assertEqual(len(export_payload(self.conn, status=None)["cards"]), 2)

    def test_next_due_preview(self):
        upsert_cards(self.conn, [make_card()])
        state = review(State(), 3, date(2026, 1, 1))
        record_review(self.conn, "c1", 3, state, "2026-01-01")
        preview = next_due_preview(self.conn, "2026-01-01", 3)
        self.assertEqual(len(preview), 3)
        self.assertEqual(preview[1], ("2026-01-02", 1))

    def test_states_for_subset(self):
        upsert_cards(self.conn, [make_card("a"), make_card("b")])
        record_review(self.conn, "a", 3, review(State(), 3, date(2026, 1, 1)), "2026-01-01")
        self.assertEqual(set(states_for(self.conn, ["a"]).keys()), {"a"})
        self.assertEqual(states_for(self.conn, []), {})


if __name__ == "__main__":
    unittest.main()
