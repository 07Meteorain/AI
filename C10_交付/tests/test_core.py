"""UTIL / STORE / INDEX：三个最底层模块。

测试重点不是"能用"，而是"坏输入时不炸、不骗人"。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import ROOT  # noqa: F401  （确保 sys.path 就位）

from brain.memory.index import InvertedIndex
from brain.memory.store import JsonlStore, Record
from brain.util import (
    atomic_write_text,
    days_between,
    iso,
    new_id,
    read_jsonl,
    slugify,
    table,
    tokenize,
    truncate,
)


class TestTokenize(unittest.TestCase):
    def test_cjk_bigrams(self):
        self.assertEqual(tokenize("记忆系统"), ["记忆", "忆系", "系统"])

    def test_single_cjk_char(self):
        self.assertEqual(tokenize("脑"), ["脑"])

    def test_mixed(self):
        tokens = tokenize("用 BM25 检索记忆")
        self.assertIn("bm25", tokens)
        self.assertIn("检索", tokens)
        self.assertIn("记忆", tokens)

    def test_nfkc_and_lower(self):
        self.assertEqual(tokenize("ＡＩ Agent"), ["ai", "agent"])

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])

    def test_no_single_char_noise_for_runs(self):
        # 连续中文不该被切成单字（否则"的""了"会污染索引）
        self.assertNotIn("记", tokenize("记忆"))


class TestUtil(unittest.TestCase):
    def test_truncate_keeps_length(self):
        text = "一二三四五六七八九十" * 5
        out = truncate(text, 10)
        self.assertEqual(len(out), 10)
        self.assertTrue(out.endswith("…"))

    def test_truncate_short(self):
        self.assertEqual(truncate("短", 10), "短")

    def test_slugify_cjk(self):
        self.assertEqual(slugify("周复盘 Week 46"), "周复盘-week-46")

    def test_slugify_default(self):
        self.assertEqual(slugify("!!!"), "note")

    def test_new_id_prefix_and_date(self):
        rid = new_id("k")
        self.assertTrue(rid.startswith("k-"))
        self.assertEqual(len(rid.split("-")), 3)

    def test_new_id_unique(self):
        self.assertNotEqual(new_id("k"), new_id("k"))

    def test_days_between(self):
        self.assertGreaterEqual(days_between("2020-01-01T00:00:00+08:00"), 1)

    def test_days_between_bad_input_does_not_crash(self):
        self.assertGreaterEqual(days_between("不是时间"), 0)

    def test_atomic_write_and_read_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "b.jsonl"
            atomic_write_text(path, "x\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "x\n")
            with path.open("a", encoding="utf-8") as fh:
                fh.write('{"a": 1}\n坏行\n{"a": 2}\n')
            rows = read_jsonl(path)
            self.assertEqual([r["a"] for r in rows], [1, 2])

    def test_read_jsonl_missing_file(self):
        self.assertEqual(read_jsonl(Path("不存在的文件.jsonl")), [])

    def test_table_aligns_cjk(self):
        out = table([["中文", "b"], ["a", "dd"]], ["列一", "列二"])
        lines = out.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn("中文", lines[2])

    def test_iso_is_utc8(self):
        self.assertIn("+08:00", iso())


class TestRecord(unittest.TestCase):
    def test_roundtrip(self):
        rec = Record(id="k-1", layer="K", title="t", text="x", created=iso(), updated=iso(), importance=2)
        self.assertEqual(rec.importance, 1.0)  # 被夹到 0~1
        again = Record.from_dict(rec.to_dict())
        self.assertEqual(again.title, "t")

    def test_unknown_layer_raises(self):
        with self.assertRaises(ValueError):
            Record(id="x", layer="Z", title="", text="", created=iso(), updated=iso())

    def test_from_dict_ignores_extra_fields(self):
        rec = Record.from_dict({"layer": "S", "text": "hi", "future_field": 1})
        self.assertEqual(rec.text, "hi")

    def test_summary_and_haystack(self):
        rec = Record(id="x", layer="S", title="标题", text="正文", created=iso(), updated=iso(), tags=["a"])
        self.assertIn("正文", rec.summary())
        self.assertIn("标题", rec.keyword_haystack())


class TestJsonlStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "k.jsonl"
        self.store = JsonlStore(self.path, "K").load()

    def tearDown(self):
        self._tmp.cleanup()

    def _rec(self, rid="k-1", text="甲"):
        return Record(id=rid, layer="K", title=text, text=text, created=iso(), updated=iso())

    def test_put_appends_and_reloads(self):
        self.store.put(self._rec())
        again = JsonlStore(self.path, "K").load()
        self.assertEqual(len(again), 1)

    def test_update_rewrites(self):
        self.store.put(self._rec())
        rec = self.store.get("k-1")
        rec.text = "乙"
        self.store.put(rec)
        self.store.flush()
        reloaded = JsonlStore(self.path, "K").load()
        self.assertEqual(reloaded.get("k-1").text, "乙")
        self.assertEqual(len(reloaded), 1)

    def test_remove(self):
        self.store.put(self._rec())
        self.assertTrue(self.store.remove("k-1"))
        self.assertFalse(self.store.remove("k-1"))
        self.assertEqual(len(JsonlStore(self.path, "K").load()), 0)

    def test_stats(self):
        self.store.put(self._rec())
        stats = self.store.stats()
        self.assertEqual(stats["count"], 1)
        self.assertGreater(stats["bytes"], 0)


class TestInvertedIndex(unittest.TestCase):
    def setUp(self):
        self.index = InvertedIndex()

    def test_empty(self):
        self.assertEqual(self.index.search(["a"]), [])
        self.assertEqual(self.index.avgdl, 0.0)

    def test_rank_prefers_more_matches(self):
        self.index.add("d1", ["记忆", "系统"])
        self.index.add("d2", ["记忆", "系统", "技能"])
        ranked = self.index.search(["记忆", "系统", "技能"])
        self.assertEqual(ranked[0][0], "d2")

    def test_rare_term_weighs_more(self):
        self.index.add("d1", ["复盘", "的", "的", "的"])
        self.index.add("d2", ["流程", "的", "的", "的"])
        self.index.add("d3", ["的", "的"])
        top = self.index.search(["复盘"])[0]
        self.assertEqual(top[0], "d1")
        self.assertGreater(self.index.idf("复盘"), self.index.idf("的"))

    def test_remove_updates_postings(self):
        self.index.add("d1", ["甲"])
        self.index.remove("d1")
        self.assertEqual(self.index.search(["甲"]), [])
        self.assertEqual(self.index.size, 0)

    def test_add_same_id_replaces(self):
        self.index.add("d1", ["甲", "甲"])
        self.index.add("d1", ["乙"])
        self.assertEqual(self.index.search(["甲"]), [])
        self.assertTrue(self.index.search(["乙"]))

    def test_unknown_query_term_returns_empty(self):
        self.index.add("d1", ["甲"])
        self.assertEqual(self.index.search(["并不存在"]), [])

    def test_matched_terms_reported(self):
        self.index.add("d1", ["记忆", "系统"])
        _, _, matched = self.index.search(["记忆"])[0]
        self.assertEqual(matched, ["记忆"])


if __name__ == "__main__":
    unittest.main()
