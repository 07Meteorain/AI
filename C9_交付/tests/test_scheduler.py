"""SM-2 排程与队列测试。"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall.model import Card  # noqa: E402
from recall.scheduler import (  # noqa: E402
    State,
    build_queue,
    days_until,
    golden_vectors,
    is_due,
    parse_date,
    retentivity,
    review,
)

DAY1 = date(2026, 1, 1)


def card(card_id: str, status: str = "approved", line: int = 1) -> Card:
    return Card(
        id=card_id,
        kind="definition",
        prompt="问题" + card_id,
        answer="答案" * 4,
        source="a.md",
        heading="h",
        line=line,
        confidence=0.8,
        status=status,
    )


class TestSM2(unittest.TestCase):
    def test_four_good_intervals(self):
        state = State()
        intervals = []
        day = DAY1
        for _ in range(4):
            state = review(state, 3, day)
            intervals.append(state.interval)
            day = day + timedelta(days=1)
        self.assertEqual(intervals, [1, 6, 15, 38])

    def test_good_keeps_ef(self):
        state = review(State(), 3, DAY1)
        self.assertAlmostEqual(state.ef, 2.5)

    def test_grade_ef_values(self):
        expected = {1: 2.18, 2: 2.36, 3: 2.5, 4: 2.6}
        for grade, ef in expected.items():
            with self.subTest(grade=grade):
                self.assertAlmostEqual(review(State(), grade, DAY1).ef, ef)

    def test_lapse_resets(self):
        state = State(ef=2.5, reps=3, interval=15, due="2026-01-01")
        new = review(state, 1, DAY1)
        self.assertEqual(new.reps, 0)
        self.assertEqual(new.interval, 1)
        self.assertEqual(new.lapses, 1)
        self.assertEqual(new.due, "2026-01-02")
        self.assertLess(new.ef, state.ef)

    def test_hard_first_review_is_one_day(self):
        state = review(State(), 2, DAY1)
        self.assertEqual(state.interval, 1)
        self.assertEqual(state.reps, 1)
        self.assertAlmostEqual(state.ef, 2.36)

    def test_easy_first_review_is_one_day(self):
        state = review(State(), 4, DAY1)
        self.assertEqual(state.interval, 1)
        self.assertAlmostEqual(state.ef, 2.6)

    def test_ef_floor(self):
        state = State(ef=1.3, reps=0, interval=1)
        for _ in range(5):
            state = review(state, 1, DAY1)
        self.assertGreaterEqual(state.ef, 1.3)

    def test_interval_half_up(self):
        state = State(ef=2.5, reps=3, interval=5)
        self.assertEqual(review(state, 3, DAY1).interval, 13)

    def test_leech_suspends_at_eight(self):
        state = State(ef=2.5, reps=0, interval=1, lapses=7, due="2026-01-01")
        state = review(state, 1, DAY1)
        self.assertTrue(state.suspended)
        self.assertEqual(state.lapses, 8)

    def test_invalid_grade(self):
        for grade in (0, 5, -1):
            with self.subTest(grade=grade):
                with self.assertRaises(ValueError):
                    review(State(), grade, DAY1)

    def test_state_roundtrip(self):
        state = review(State(), 3, DAY1)
        clone = State.from_dict(state.to_dict())
        self.assertEqual(state, clone)

    def test_from_empty_dict(self):
        self.assertEqual(State.from_dict(None), State())
        self.assertEqual(State.from_dict({}).ef, 2.5)

    def test_due_date(self):
        state = review(State(), 3, DAY1)
        self.assertEqual(state.due, "2026-01-02")
        self.assertTrue(is_due(state, DAY1 + timedelta(days=1)))
        self.assertFalse(is_due(state, DAY1))

    def test_suspended_not_due(self):
        state = State(due="2026-01-01", suspended=True)
        self.assertFalse(is_due(state, DAY1))

    def test_days_until(self):
        self.assertEqual(days_until("2026-01-03", DAY1), 2)
        self.assertEqual(days_until("", DAY1), 0)
        self.assertEqual(days_until("not-a-date", DAY1), 0)

    def test_retentivity_range(self):
        state = review(State(), 3, DAY1)
        value = retentivity(state, DAY1 + timedelta(days=1))
        self.assertGreater(value, 0)
        self.assertLessEqual(value, 1.0)


class TestQueue(unittest.TestCase):
    def test_due_before_new(self):
        cards = [card("new1", line=1), card("due1", line=2), card("future", line=3)]
        states = {
            "due1": State(reps=1, interval=6, due="2026-01-01"),
            "future": State(reps=1, interval=6, due="2026-02-01"),
        }
        queue = build_queue(cards, states, DAY1, limit=10, new_limit=10)
        self.assertEqual([item[0].id for item in queue], ["due1", "new1"])
        self.assertFalse(queue[0][1])
        self.assertTrue(queue[1][1])

    def test_new_limit(self):
        cards = [card("n1"), card("n2"), card("n3")]
        queue = build_queue(cards, {}, DAY1, limit=10, new_limit=2)
        self.assertEqual(len(queue), 2)

    def test_limit(self):
        cards = [card("n1"), card("n2"), card("n3")]
        queue = build_queue(cards, {}, DAY1, limit=1, new_limit=10)
        self.assertEqual(len(queue), 1)

    def test_suspended_excluded(self):
        cards = [card("s1")]
        states = {"s1": State(due="2026-01-01", suspended=True)}
        self.assertEqual(build_queue(cards, states, DAY1), [])

    def test_candidate_excluded(self):
        cards = [card("c1", status="candidate")]
        self.assertEqual(build_queue(cards, {}, DAY1), [])
        queue = build_queue(cards, {}, DAY1, include_candidates=True)
        self.assertEqual(len(queue), 1)

    def test_rejected_excluded(self):
        cards = [card("r1", status="rejected")]
        self.assertEqual(build_queue(cards, {}, DAY1), [])


class TestVectors(unittest.TestCase):
    def test_vectors_match_engine(self):
        vectors = golden_vectors()
        self.assertGreaterEqual(len(vectors), 6)
        for vector in vectors:
            state = State.from_dict(vector["start"])
            for step in vector["steps"]:
                state = review(state, step["grade"], parse_date(step["day"]))
                for key in ("ef", "reps", "interval", "due", "lapses", "suspended"):
                    self.assertEqual(
                        getattr(state, key),
                        step["state"][key],
                        "{} / {}".format(vector["name"], key),
                    )

    def test_leech_vector(self):
        vector = [v for v in golden_vectors() if v["name"] == "leech"][0]
        self.assertTrue(vector["steps"][-1]["state"]["suspended"])


if __name__ == "__main__":
    unittest.main()
