"""进化层：挖掘、脚手架、周期、度量，以及一条端到端的"它真的变了"。

E2E 用例是整个项目最该看的一条测试：它证明**同一个命令，在 evolve 之后步数变少**。
"""

from __future__ import annotations

import unittest

from support import BrainCase

from brain.evolve import compute, evolve_once, render_trend, trend
from brain.evolve.miner import alias_candidates, failure_stats, signature, unused_skills, workflows
from brain.evolve.scaffold import draft_skill
from brain.loop.planner import Intent


def fake_trace(
    sig="memory.search>memory.write",
    *,
    status="ok",
    session="s",
    text="做点什么",
    hits=2,
    run_id="r1",
    started="2026-11-15T10:00:00+08:00",
    intent="review",
):
    return {
        "run_id": run_id,
        "session": session,
        "input": text,
        "intent": intent,
        "started": started,
        "status": status,
        "recall_hits": hits,
        "steps": [{"tool": t, "args": {}, "ok": True} for t in sig.split(">")],
    }


class TestMiner(unittest.TestCase):
    def test_signature(self):
        self.assertEqual(signature(fake_trace("a>b>c")), "a>b>c")

    def test_workflow_threshold(self):
        traces = [fake_trace(run_id=f"r{i}") for i in range(2)]
        self.assertEqual(workflows(traces, min_runs=3), [])
        traces.append(fake_trace(run_id="r3"))
        found = workflows(traces, min_runs=3)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].count, 3)
        self.assertEqual(found[0].tools, ["memory.search", "memory.write"])

    def test_single_step_ignored(self):
        traces = [fake_trace("memory.search", run_id=f"r{i}") for i in range(5)]
        self.assertEqual(workflows(traces), [])

    def test_failed_runs_ignored(self):
        traces = [fake_trace(status="failed", run_id=f"r{i}") for i in range(5)]
        self.assertEqual(workflows(traces), [])

    def test_skill_only_workflow_ignored(self):
        traces = [fake_trace("skill.run", run_id=f"r{i}") for i in range(5)]
        self.assertEqual(workflows(traces), [])

    def test_failure_stats(self):
        traces = [
            {"steps": [{"tool": "fs.read", "ok": False, "error": "FileNotFoundError: x"}]},
            {"steps": [{"tool": "fs.read", "ok": True}]},
        ]
        stats = failure_stats(traces)
        self.assertEqual(stats["fs.read"]["calls"], 2)
        self.assertEqual(stats["fs.read"]["failed"], 1)
        self.assertEqual(stats["fs.read"]["success_rate"], 0.5)
        self.assertEqual(stats["fs.read"]["top_error"], "FileNotFoundError")

    def test_alias_candidates_from_miss_then_hit(self):
        miss = fake_trace("memory.search", session="s1", text="周会纪要怎么写的", hits=0, run_id="r1", intent="recall")
        hit = fake_trace(
            "memory.search",
            session="s1",
            text="复盘 怎么写",
            hits=2,
            run_id="r2",
            started="2026-11-15T10:05:00+08:00",
            intent="recall",
        )
        known = {"复盘"}
        found = alias_candidates([miss, hit], known)
        self.assertEqual(len(found), 1)
        self.assertIn("周会", found[0]["key"])
        self.assertIn("复盘", found[0]["targets"])

    def test_alias_requires_success_after_miss(self):
        miss = fake_trace("memory.search", session="s1", text="周会纪要", hits=0, run_id="r1", intent="recall")
        miss2 = fake_trace(
            "memory.search",
            session="s1",
            text="另一个说法",
            hits=0,
            run_id="r2",
            started="2026-11-15T10:05:00+08:00",
            intent="recall",
        )
        self.assertEqual(alias_candidates([miss, miss2], {"复盘"}), [])

    def test_alias_uses_curated_vocabulary(self):
        """回归：提问本身会被写进 S 层，于是"没问到的词"立刻变成索引里有的词。

        如果拿全量索引当"学过没有"的标尺，同义词学习永远学不到东西。
        """

        miss = fake_trace("memory.search", session="s1", text="周会纪要", hits=0, run_id="r1", intent="recall")
        hit = fake_trace(
            "memory.search",
            session="s1",
            text="复盘",
            hits=1,
            run_id="r2",
            started="2026-11-15T10:05:00+08:00",
            intent="recall",
        )
        indexed = {"周会", "会纪", "纪要", "复盘"}  # 全部已在索引里
        found = alias_candidates([miss, hit], indexed, {"复盘"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "周会纪要")

    def test_unused_skills(self):
        stale = unused_skills(
            {"old": {"last": "2020-01-01T00:00:00+08:00"}, "fresh": {"last": "2026-11-14T00:00:00+08:00"}},
            ["old", "never", "fresh"],
        )
        self.assertIn("old", stale)
        self.assertIn("never", stale)
        self.assertNotIn("fresh", stale)


class TestScaffold(BrainCase):
    def test_draft_created_and_importable(self):
        runs = [fake_trace(run_id=f"r{i}") for i in range(3)]
        info = draft_skill(
            self.app.config,
            workflow="memory.search>memory.write",
            label="review",
            count=3,
            runs=runs,
        )
        self.assertTrue(info["ok"], info)
        folder = self.app.config.drafts_dir / info["name"]
        self.assertTrue((folder / "SKILL.md").is_file())
        handler = (folder / "handler.py").read_text(encoding="utf-8")
        compile(handler, "handler.py", "exec")  # 生成的代码必须语法正确
        self.app.loader.load_all(force=True)
        self.assertEqual(self.app.loader.get(info["name"]).status, "draft")

    def test_generated_handler_runs(self):
        runs = [fake_trace(run_id=f"r{i}") for i in range(3)]
        info = draft_skill(self.app.config, workflow="memory.search>memory.write", label="review", count=3, runs=runs)
        result = self.app.skills.run(info["name"], {"query": "测试"}, ctx=self.app.context())
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.outputs["workflow"], "memory.search>memory.write")

    def test_unsafe_tool_refused(self):
        info = draft_skill(self.app.config, workflow="shell.run>memory.write", label="x", count=3, runs=[fake_trace()])
        self.assertFalse(info["ok"])
        self.assertIn("不可自动化", info["reason"])

    def test_duplicate_draft_refused(self):
        runs = [fake_trace(run_id=f"r{i}") for i in range(3)]
        first = draft_skill(self.app.config, workflow="a.tool>b.tool", label="x", count=3, runs=runs)
        self.assertFalse(first["ok"])  # a.tool 不在白名单
        ok = draft_skill(self.app.config, workflow="memory.search>memory.write", label="x", count=3, runs=runs)
        self.assertTrue(ok["ok"])
        again = draft_skill(self.app.config, workflow="memory.search>memory.write", label="x", count=3, runs=runs)
        self.assertFalse(again["ok"])


class TestEvolveCycle(BrainCase):
    def _three_reviews(self):
        for i in range(3):
            self.app.ask("复盘", force_intent=Intent("review", "", "复盘", 1.0, f"run{i}"))

    def test_dry_run_changes_nothing(self):
        self._three_reviews()
        before = len(self.app.loader.load_all())
        report = evolve_once(self.app.config, self.app.memory, self.app.loader, self.app.skills, apply=False)
        self.assertEqual(report.applied, 0)
        self.assertEqual(len(self.app.loader.load_all(force=True)), before)
        self.assertTrue(any("memory.search>skill.run" in p for p in report.patterns))

    def test_apply_creates_draft_and_knowledge(self):
        self._three_reviews()
        report = evolve_once(self.app.config, self.app.memory, self.app.loader, self.app.skills, apply=True)
        self.assertGreaterEqual(report.applied, 2)
        drafts = [s for s in self.app.loader.load_all(force=True) if s.status == "draft"]
        self.assertEqual(len(drafts), 1)
        self.assertTrue(any(r.meta.get("kind") == "playbook" for r in self.app.memory.all("K")))
        self.assertTrue(self.app.config.evolution_log.is_file())

    def test_after_evolve_review_takes_one_step(self):
        self._three_reviews()
        evolve_once(self.app.config, self.app.memory, self.app.loader, self.app.skills, apply=True)
        result = self.app.ask("复盘", force_intent=Intent("review", "", "复盘", 1.0, "after"))
        self.assertEqual(len(result.trace.steps), 1)
        self.assertIn("auto-", result.trace.steps[0].args.get("name", ""))

    def test_evolution_survives_restart(self):
        self._three_reviews()
        evolve_once(self.app.config, self.app.memory, self.app.loader, self.app.skills, apply=True)
        again = self.fresh_app()
        drafts = [s for s in again.loader.load_all() if s.status == "draft"]
        self.assertEqual(len(drafts), 1)

    def test_report_render(self):
        self._three_reviews()
        report = evolve_once(self.app.config, self.app.memory, self.app.loader, self.app.skills, apply=False)
        text = report.render()
        self.assertIn("进化周期", text)
        self.assertIn("重复工作流", text)


class TestMetrics(BrainCase):
    def test_empty_metrics(self):
        metrics = compute(self.app.config, self.app.memory, [], self.app.skills)
        self.assertEqual(metrics.runs, 0)
        self.assertIn("记忆", metrics.render())

    def test_metrics_counts(self):
        self.app.ask("你好")
        self.app.ask("记一下 一条笔记")
        metrics = compute(self.app.config, self.app.memory, self.app.traces.all(), self.app.skills)
        self.assertEqual(metrics.runs, 2)
        self.assertEqual(metrics.tool_calls, 3)
        self.assertGreater(metrics.memory["layers"]["total"]["count"], 0)

    def test_trend_insufficient(self):
        self.assertTrue(trend([])["insufficient"])
        self.assertTrue(trend([fake_trace()])["insufficient"])

    def test_trend_detects_step_drop(self):
        traces = [fake_trace("a>b>c", run_id=f"r{i}", started=f"2026-11-1{i}T10:00:00+08:00") for i in range(3)]
        traces += [fake_trace("a", run_id=f"x{i}", started=f"2026-11-2{i}T10:00:00+08:00") for i in range(3)]
        data = trend(traces)
        self.assertFalse(data["insufficient"])
        self.assertLess(data["second"]["avg_steps"], data["first"]["avg_steps"])
        self.assertEqual(data["per_intent"]["review"]["before_steps"], 3.0)
        self.assertEqual(data["per_intent"]["review"]["after_steps"], 1.0)
        self.assertTrue(any("固化生效" in v for v in data["verdict"]))
        self.assertIn("按意图看", render_trend(data))

    def test_trend_ignores_mixed_intents(self):
        traces = [fake_trace("a", run_id="1", intent="capture")]
        traces += [fake_trace("a>b>c", run_id="2", intent="review")]
        traces += [fake_trace("a", run_id="3", intent="capture")]
        traces += [fake_trace("a", run_id="4", intent="review")]
        data = trend(traces)
        # capture 一直是 1 步，不该因为 review 混进来而显示"变化"
        self.assertEqual(data["per_intent"]["capture"]["delta"], 0.0)


if __name__ == "__main__":
    unittest.main()
