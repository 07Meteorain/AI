"""循环层与接口层：分类、规划、执行、留痕、CLI 退出码。"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from support import BrainCase

from brain.interface.cli import main
from brain.loop.planner import Intent, RulePlanner


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.p = RulePlanner()

    def test_capture_keywords(self):
        for text in ("记一下 今天学到的", "记住这个", "note: something", "存档 这段"):
            self.assertEqual(self.p.classify(text).kind, "capture", text)

    def test_task_done(self):
        intent = self.p.classify("任务 完成 写测试")
        self.assertEqual(intent.kind, "task")
        self.assertEqual(intent.args.get("action"), "done")
        self.assertEqual(intent.query, "写测试")

    def test_task_add(self):
        self.assertEqual(self.p.classify("任务 明天交周报").kind, "task")

    def test_explicit_skill(self):
        intent = self.p.classify("技能 weekly-review 2026-W46")
        self.assertEqual(intent.kind, "skill")
        self.assertEqual(intent.args["skill"], "weekly-review")

    def test_review(self):
        self.assertEqual(self.p.classify("来个周复盘").kind, "review")

    def test_recall_question(self):
        self.assertEqual(self.p.classify("上次那个坑是什么？").kind, "recall")

    def test_empty_is_chat(self):
        self.assertEqual(self.p.classify("").kind, "chat")

    def test_plan_capture_default_s(self):
        intent = self.p.classify("记一下 普通笔记")
        steps = self.p.plan(intent, "记一下 普通笔记")
        self.assertEqual(steps[0].tool, "memory.write")
        self.assertEqual(steps[0].args["layer"], "S")

    def test_plan_capture_knowledge_keyword(self):
        intent = self.p.classify("记一下 结论：先写测试")
        steps = self.p.plan(intent, "记一下 结论：先写测试")
        self.assertEqual(steps[0].args["layer"], "K")

    def test_plan_capture_forced_layer(self):
        intent = Intent("capture", "x", "x", 1.0, "test", {"layer": "K"})
        self.assertEqual(self.p.plan(intent, "x")[0].args["layer"], "K")

    def test_plan_recall_single_step(self):
        intent = Intent("recall", "复盘", "复盘", 1.0, "test")
        self.assertEqual([s.tool for s in self.p.plan(intent, "复盘")], ["memory.search"])

    def test_plan_review_three_steps(self):
        intent = Intent("review", "", "复盘", 1.0, "test")
        self.assertEqual(
            [s.tool for s in self.p.plan(intent, "复盘")], ["memory.search", "skill.run", "memory.promote"]
        )

    def test_plan_chat_includes_time(self):
        intent = Intent("chat", "", "你好", 0.5, "test")
        self.assertEqual([s.tool for s in self.p.plan(intent, "你好")], ["time.now", "memory.search"])

    def test_strip_prefix(self):
        self.assertEqual(self.p._strip_prefix("记一下：今天下雨"), "今天下雨")


class TestEngine(BrainCase):
    def test_capture_writes_memory_and_trace(self):
        result = self.app.ask("记一下 循环层的第一个测试")
        self.assertEqual(result.trace.status, "ok")
        self.assertTrue(any(r.layer == "S" for r in self.app.memory.all("S")))
        self.assertEqual(self.app.traces.count(), 1)

    def test_every_run_reflects_ar_and_s(self):
        self.app.ask("你好")
        self.assertGreaterEqual(len(self.app.memory.all("AR")), 1)
        self.assertGreaterEqual(len(self.app.memory.all("S")), 1)
        ar = self.app.memory.all("AR")[0]
        self.assertIn("workflow", ar.meta)
        self.assertTrue(ar.meta["steps"])

    def test_readonly_mode_writes_nothing(self):
        result = self.app.ask("记一下 不应该被记住", allow_write=False)
        self.assertFalse(result.trace.meta.get("reflected"))
        self.assertEqual(len(self.app.memory.all()), 0)

    def test_recall_miss_is_stated(self):
        result = self.app.ask("回忆 完全没有的量子色动力学")
        self.assertIn("没有命中", result.answer)
        self.assertEqual(result.trace.recall_hits, 0)

    def test_recall_hit_reports_evidence(self):
        self.app.ask("记一下 复盘要在周末做")
        result = self.app.ask("回忆 复盘 周末")
        self.assertGreater(result.trace.recall_hits, 0)
        self.assertTrue(result.evidence)
        self.assertIn("score", result.answer)

    def test_force_intent_overrides_classifier(self):
        result = self.app.ask("这句话里没有关键词", force_intent=Intent("capture", "x", "x", 1.0, "test"))
        self.assertEqual(result.trace.intent, "capture")

    def test_task_add_and_done(self):
        self.app.ask("任务 写 C10 交付物")
        tasks = self.app.memory.all("T")
        self.assertEqual(len(tasks), 1)
        self.app.ask("", force_intent=Intent("task", tasks[0].id, "", 1.0, "test", {"action": "done"}))
        self.assertEqual(self.app.memory.get(tasks[0].id).status, "done")

    def test_trace_persisted_to_disk(self):
        self.app.ask("你好")
        rows = self.app.traces.all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "ok")
        self.assertIn("run_id", rows[0])
        self.assertIn("steps", rows[0])

    def test_persist_false_skips_trace(self):
        self.app.ask("你好", persist=False)
        self.assertEqual(self.app.traces.count(), 0)

    def test_skill_run_through_loop(self):
        result = self.app.ask("技能 note-to-knowledge 先写测试再写实现")
        self.assertEqual(result.trace.steps[0].tool, "skill.run")
        self.assertTrue(result.trace.steps[0].ok)

    def test_unknown_skill_reports_error(self):
        result = self.app.ask("技能 不存在的技能")
        self.assertEqual(result.trace.status, "failed")
        self.assertIn("没有技能", result.answer)

    def test_auto_skill_takes_over_review(self):
        draft = self.skills_dir / "_drafts" / "auto-review-test"
        draft.mkdir(parents=True)
        (draft / "SKILL.md").write_text(
            "---\nname: auto-review-test\ndescription: 自动接管测试\nversion: 0.1\n"
            "tags: auto, draft, review\nhandler: handler.py\n---\n",
            encoding="utf-8",
        )
        (draft / "handler.py").write_text(
            "def run(ctx, args=None):\n    return {'summary': '接管了'}\n", encoding="utf-8"
        )
        self.app.loader.load_all(force=True)
        result = self.app.ask("复盘")
        self.assertEqual(len(result.trace.steps), 1)
        self.assertEqual(result.trace.steps[0].tool, "skill.run")
        self.assertIn("接管", result.answer)

    def test_human_skill_does_not_take_over(self):
        result = self.app.ask("复盘")
        self.assertEqual(len(result.trace.steps), 3)


class TestCli(BrainCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_no_args_prints_help(self):
        code, out = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("第二大脑", out)

    def test_version(self):
        code, out = self._run(["version"])
        self.assertEqual(code, 0)
        self.assertIn("brain", out)

    def test_doctor(self):
        code, out = self._run(["doctor"])
        self.assertEqual(code, 0, out)
        self.assertIn("全部通过", out)

    def test_capture_and_recall_json(self):
        code, out = self._run(["capture", "第二大脑要有记忆"])
        self.assertEqual(code, 0)
        self.assertIn("已写入", out)

        code, out = self._run(["recall", "第二大脑", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["run"]["intent"], "recall")

    def test_ask(self):
        code, out = self._run(["ask", "记一下", "命令行测试"])
        self.assertEqual(code, 0)
        self.assertIn("执行回执", out)

    def test_task_commands(self):
        code, out = self._run(["task", "add", "交付 C10"])
        self.assertEqual(code, 0)
        self.assertIn("已建任务", out)
        code, out = self._run(["task", "list"])
        self.assertEqual(code, 0)
        self.assertIn("交付 C10", out)

    def test_skill_list_and_run(self):
        code, out = self._run(["skill", "list"])
        self.assertEqual(code, 0)
        self.assertIn("weekly-review", out)
        code, out = self._run(["skill", "run", "weekly-review", "2020-W01"])
        self.assertEqual(code, 0)
        self.assertIn("empty", out.replace("Empty", "empty").lower())

    def test_skill_show(self):
        code, out = self._run(["skill", "show", "decision-log"])
        self.assertEqual(code, 0)
        self.assertIn("决策", out)

    def test_review_command(self):
        code, out = self._run(["review"])
        self.assertEqual(code, 0)
        self.assertIn("周复盘", out)

    def test_metrics_and_trend(self):
        self._run(["ask", "你好"])
        code, out = self._run(["metrics"])
        self.assertEqual(code, 0)
        self.assertIn("检索命中率", out)
        code, out = self._run(["trend"])
        self.assertEqual(code, 0)
        self.assertIn("趋势", out)

    def test_trace_command(self):
        self._run(["ask", "你好"])
        code, out = self._run(["trace"])
        self.assertEqual(code, 0)
        self.assertIn("chat", out)

    def test_promote_dry_run(self):
        code, out = self._run(["promote"])
        self.assertEqual(code, 0)
        self.assertIn("没有需要沉淀", out)

    def test_import_notes(self):
        notes = self.root_notes()
        code, out = self._run(["import-notes", str(notes)])
        self.assertEqual(code, 0)
        self.assertIn("导入 2 篇", out)

    def root_notes(self):
        folder = self._tmp / "notes"
        folder.mkdir()
        (folder / "a.md").write_text("# 甲\n内容甲", encoding="utf-8")
        (folder / "b.md").write_text("内容乙", encoding="utf-8")
        return folder


def app_trace_count(app) -> int:  # 兼容旧写法，留给以后的用例
    return app.traces.count()


if __name__ == "__main__":
    unittest.main()
