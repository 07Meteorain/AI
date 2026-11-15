"""KSTAR 记忆：写入、检索、同义词、镜像、沉淀规则。

这一层如果出错，症状是"东西存了但找不到"——所以测试里最重的是**检索**。
"""

from __future__ import annotations

import unittest

from support import BrainCase

from brain.memory.promote import apply_proposal, collect_proposals, task_done_to_action


class TestKstarWrite(BrainCase):
    def test_write_all_layers(self):
        for layer in ("K", "S", "T", "AR"):
            rec = self.app.memory.write(layer, f"{layer} 层内容", title=f"{layer} 标题")
            self.assertEqual(rec.layer, layer)
        self.assertEqual(len(self.app.memory.all()), 4)

    def test_invalid_layer(self):
        with self.assertRaises(ValueError):
            self.app.memory.write("Q", "x")

    def test_auto_title(self):
        rec = self.app.memory.write("S", "第一句话。第二句话。")
        self.assertEqual(rec.title, "第一句话")

    def test_dedupe_same_text(self):
        a = self.app.memory.write("S", "完全一样的一段话", dedupe=True)
        b = self.app.memory.write("S", "完全一样的一段话", dedupe=True)
        self.assertEqual(a.id, b.id)
        self.assertEqual(len(self.app.memory.all("S")), 1)

    def test_no_dedupe_creates_two(self):
        self.app.memory.write("S", "同样的话")
        self.app.memory.write("S", "同样的话")
        self.assertEqual(len(self.app.memory.all("S")), 2)

    def test_persistence_across_processes(self):
        rec = self.app.memory.write("K", "持久化测试", title="持久化")
        again = self.fresh_app()
        self.assertIsNotNone(again.memory.get(rec.id))


class TestKstarSearch(BrainCase):
    def setUp(self):
        super().setUp()
        self.k = self.app.memory.write("K", "复盘要在周末做，因为那时记忆最完整", title="复盘时机", tags=["复盘"])
        self.s = self.app.memory.write("S", "今天写了一段关于复盘的草稿", title="草稿")
        self.ar = self.app.memory.write("AR", "复盘的技能跑了一次，失败在路径上", title="失败", status="failed")

    def test_search_returns_hits(self):
        hits = self.app.memory.search("复盘", top_k=5)
        self.assertGreaterEqual(len(hits), 2)
        self.assertTrue(all(h.record.layer in ("K", "S", "AR") for h in hits))

    def test_layer_prior_favours_knowledge(self):
        hits = self.app.memory.search("复盘", top_k=3, touch=False)
        self.assertEqual(hits[0].record.layer, "K")

    def test_layer_filter(self):
        hits = self.app.memory.search("复盘", layers=["AR"])
        self.assertEqual([h.record.layer for h in hits], ["AR"])

    def test_empty_query(self):
        self.assertEqual(self.app.memory.search(""), [])
        self.assertEqual(self.app.memory.search("   "), [])

    def test_no_hit_returns_empty(self):
        self.assertEqual(self.app.memory.search("量子色动力学"), [])

    def test_touch_increments_hits(self):
        self.app.memory.search("复盘")
        again = self.fresh_app()
        self.assertGreater(again.memory.get(self.k.id).hits, 0)

    def test_touch_false_does_not_increment(self):
        self.app.memory.search("复盘", touch=False)
        self.assertEqual(self.app.memory.get(self.k.id).hits, 0)

    def test_matched_terms_exposed(self):
        hit = self.app.memory.search("复盘", top_k=1)[0]
        self.assertTrue(hit.matched)
        self.assertIn("命中", hit.why)

    def test_alias_expands_recall(self):
        # "周会" 不曾出现在任何记录里，同义词表把它指到"复盘"
        self.assertEqual(self.app.memory.search("周会", touch=False), [])
        self.assertTrue(self.app.memory.add_alias("周会", ["复盘"]))
        self.assertGreaterEqual(len(self.app.memory.search("周会", touch=False)), 1)

    def test_add_alias_is_idempotent(self):
        self.assertTrue(self.app.memory.add_alias("周会", ["复盘"]))
        self.assertFalse(self.app.memory.add_alias("周会", ["复盘"]))

    def test_alias_persists(self):
        self.app.memory.add_alias("周会", ["复盘"])
        again = self.fresh_app()
        self.assertIn("周会", again.memory.aliases["map"])

    def test_echo_records_excluded_by_default(self):
        echo = self.app.memory.write("S", "这是上周问过的一句话", title="问句", meta={"echo": True})
        self.assertEqual(self.app.memory.search("问过的一句话", touch=False), [])
        self.assertEqual(self.app.memory.search("问过的一句话", touch=False, include_echo=True)[0].record.id, echo.id)


class TestKstarMirror(BrainCase):
    def test_knowledge_markdown_written(self):
        rec = self.app.memory.write("K", "知识正文", title="知识标题")
        path = self.app.config.knowledge_dir / f"{rec.id}.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("知识标题", text)
        self.assertIn("知识正文", text)

    def test_index_md_regenerated(self):
        self.app.memory.write("K", "甲", title="甲标题")
        self.app.memory.write("K", "乙", title="乙标题")
        index = (self.app.config.knowledge_dir / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("共 2 条", index)
        self.assertIn("乙标题", index)

    def test_s_layer_has_no_mirror(self):
        rec = self.app.memory.write("S", "情境不进镜像")
        self.assertFalse((self.app.config.knowledge_dir / f"{rec.id}.md").exists())


class TestKstarUpdate(BrainCase):
    def test_update_persists(self):
        rec = self.app.memory.write("K", "可更新", title="更新测试")
        self.app.memory.update(rec.id, importance=0.9, title="新标题")
        again = self.fresh_app()
        loaded = again.memory.get(rec.id)
        self.assertEqual(loaded.importance, 0.9)
        self.assertEqual(loaded.title, "新标题")

    def test_update_missing(self):
        self.assertIsNone(self.app.memory.update("k-不存在", title="x"))

    def test_stats_counts(self):
        self.app.memory.write("K", "a")
        self.app.memory.write("S", "b")
        stats = self.app.memory.stats()
        self.assertEqual(stats["layers"]["K"]["count"], 1)
        self.assertEqual(stats["layers"]["total"]["count"], 2)


class TestPromote(BrainCase):
    def _ar(self, workflow="memory.search>memory.write", ok=True, error=""):
        return self.app.memory.write(
            "AR",
            "一次行动",
            title="行动",
            status="ok" if ok else "failed",
            meta={"intent": "review", "workflow": workflow, "error": error, "steps": ["memory.search", "memory.write"]},
        )

    def test_p1_task_done_creates_action(self):
        task = self.app.memory.write("T", "写测试", title="写测试", status="open", meta={"started": "2026-01-01T00:00:00+08:00"})
        ar = task_done_to_action(self.app.memory, task)
        self.assertEqual(ar.layer, "AR")
        self.assertEqual(ar.meta["task_id"], task.id)
        self.assertGreater(ar.meta["days"], 0)

    def test_p2_needs_three_repeats(self):
        self._ar()
        self._ar()
        self.assertEqual([p for p in collect_proposals(self.app.memory) if p.kind == "ar→k"], [])
        self._ar()
        proposals = [p for p in collect_proposals(self.app.memory) if p.kind == "ar→k"]
        self.assertEqual(len(proposals), 1)

    def test_p2_ignores_single_step(self):
        for _ in range(3):
            self._ar(workflow="memory.write")
        self.assertEqual([p for p in collect_proposals(self.app.memory) if p.kind == "ar→k"], [])

    def test_p2_apply_writes_knowledge(self):
        for _ in range(3):
            self._ar()
        proposal = [p for p in collect_proposals(self.app.memory) if p.kind == "ar→k"][0]
        self.assertTrue(apply_proposal(self.app.memory, proposal))
        self.assertEqual(len(self.app.memory.all("K")), 1)
        self.assertTrue(self.app.memory.all("K")[0].text.startswith("已验证流程"))

    def test_p2_not_proposed_twice_after_apply(self):
        for _ in range(3):
            self._ar()
        for proposal in collect_proposals(self.app.memory):
            apply_proposal(self.app.memory, proposal)
        self.assertEqual([p for p in collect_proposals(self.app.memory) if p.kind == "ar→k"], [])

    def test_p3_repeated_failure(self):
        self._ar(ok=False, error="FileNotFoundError")
        self._ar(ok=False, error="FileNotFoundError")
        proposals = [p for p in collect_proposals(self.app.memory) if p.kind == "failure→k"]
        self.assertEqual(len(proposals), 1)
        apply_proposal(self.app.memory, proposals[0])
        self.assertIn("已知坑", self.app.memory.all("K")[0].title)

    def test_p4_cold_situation_archived(self):
        old = self.app.memory.write("S", "很久以前的一次会话")
        self.app.memory.update(old.id, created="2020-01-01T00:00:00+08:00")
        proposals = [p for p in collect_proposals(self.app.memory) if p.kind == "s→archive"]
        self.assertEqual(len(proposals), 1)
        apply_proposal(self.app.memory, proposals[0])
        rec = self.app.memory.get(old.id)
        self.assertTrue(rec.meta.get("archived"))
        self.assertIsNotNone(rec, "归档必须保留原文，不能删除")

    def test_p4_skips_hot_situation(self):
        rec = self.app.memory.write("S", "刚发生的")
        self.app.memory.update(rec.id, created="2020-01-01T00:00:00+08:00", hits=3)
        self.assertEqual([p for p in collect_proposals(self.app.memory) if p.kind == "s→archive"], [])

    def test_apply_is_not_repeatable(self):
        for _ in range(3):
            self._ar()
        proposal = [p for p in collect_proposals(self.app.memory) if p.kind == "ar→k"][0]
        self.assertTrue(apply_proposal(self.app.memory, proposal))
        self.assertFalse(apply_proposal(self.app.memory, proposal))


if __name__ == "__main__":
    unittest.main()
