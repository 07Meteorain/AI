"""工具层与技能层：契约、权限、熔断、加载、执行。

这两层的失败方式不一样：工具层坏在"该拒绝的没拒绝"，技能层坏在"该发现的没发现"。
所以测试分别针对这两点。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from support import BrainCase

from brain.skills.model import parse_front_matter
from brain.skills.scaffold import create_skill
from brain.tools.base import ToolSpec


class TestRegistry(BrainCase):
    def test_tool_count(self):
        names = self.app.tools.names()
        for expected in ("time.now", "memory.search", "memory.write", "task.add", "skill.run", "git.status"):
            self.assertIn(expected, names)

    def test_unknown_tool(self):
        res = self.app.tools.call("nope.tool", {}, self.app.context())
        self.assertFalse(res.ok)
        self.assertIn("未知工具", res.error)

    def test_missing_required_param(self):
        res = self.app.tools.call("memory.search", {}, self.app.context())
        self.assertFalse(res.ok)
        self.assertIn("缺少必填参数", res.error)

    def test_unknown_param_rejected(self):
        res = self.app.tools.call("time.now", {"随便": 1}, self.app.context())
        self.assertFalse(res.ok)
        self.assertIn("未知参数", res.error)

    def test_read_tool_allowed_in_readonly(self):
        ctx = self.app.context(allow_write=False)
        self.assertTrue(self.app.tools.call("time.now", {}, ctx).ok)

    def test_write_tool_blocked_in_readonly(self):
        ctx = self.app.context(allow_write=False)
        res = self.app.tools.call("memory.write", {"text": "x"}, ctx)
        self.assertFalse(res.ok)
        self.assertIn("只读模式", res.error)
        self.assertEqual(len(self.app.memory.all()), 0, "只读模式下真的不能写入")

    def test_breaker_after_three_failures(self):
        ctx = self.app.context()
        for _ in range(3):
            self.app.tools.call("memory.get", {"id": "k-不存在"}, ctx)
        self.assertIn("memory.get", self.app.tools.disabled())
        res = self.app.tools.call("memory.get", {"id": "k-不存在"}, ctx)
        self.assertIn("熔断", res.error)

    def test_breaker_reset(self):
        ctx = self.app.context()
        for _ in range(3):
            self.app.tools.call("memory.get", {"id": "x"}, ctx)
        self.app.tools.enable_all()
        self.assertEqual(self.app.tools.disabled(), [])

    def test_stats(self):
        ctx = self.app.context()
        self.app.tools.call("time.now", {}, ctx)
        self.app.tools.call("memory.get", {"id": "x"}, ctx)
        stats = self.app.tools.stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["success_rate"], 0.5)

    def test_toolspec_rejects_bad_danger(self):
        with self.assertRaises(ValueError):
            ToolSpec(name="x", description="d", handler=lambda: None, danger="rm -rf")


class TestBuiltinTools(BrainCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.app.context()

    def test_time_now(self):
        res = self.app.tools.call("time.now", {}, self.ctx)
        self.assertTrue(res.ok)
        self.assertTrue(res.data["weekday"].startswith("周"))

    def test_memory_write_and_search(self):
        write = self.app.tools.call("memory.write", {"text": "工具层写入测试", "layer": "K", "tags": "测试,工具"}, self.ctx)
        self.assertTrue(write.ok)
        found = self.app.tools.call("memory.search", {"query": "工具层写入"}, self.ctx)
        self.assertTrue(found.ok)
        self.assertEqual(found.data[0]["id"], write.data["id"])

    def test_memory_write_bad_layer(self):
        res = self.app.tools.call("memory.write", {"text": "x", "layer": "Z"}, self.ctx)
        self.assertFalse(res.ok)

    def test_memory_get(self):
        rec = self.app.memory.write("K", "按 id 取", title="取")
        res = self.app.tools.call("memory.get", {"id": rec.id}, self.ctx)
        self.assertTrue(res.ok)
        self.assertEqual(res.data["title"], "取")

    def test_memory_promote_dry_run(self):
        res = self.app.tools.call("memory.promote", {"apply": False}, self.ctx)
        self.assertTrue(res.ok)
        self.assertEqual(res.data["applied"], 0)

    def test_task_flow(self):
        add = self.app.tools.call("task.add", {"title": "写 C10", "due": "2026-12-31"}, self.ctx)
        self.assertTrue(add.ok)
        listed = self.app.tools.call("task.list", {"status": "open"}, self.ctx)
        self.assertEqual(len(listed.data), 1)
        done = self.app.tools.call("task.done", {"id": add.data["id"]}, self.ctx)
        self.assertTrue(done.ok)
        self.assertEqual(self.app.memory.get(add.data["id"]).status, "done")
        self.assertEqual(self.app.tools.call("task.list", {"status": "open"}, self.ctx).data, [])

    def test_task_done_by_title_prefix(self):
        self.app.tools.call("task.add", {"title": "整理记忆库"}, self.ctx)
        res = self.app.tools.call("task.done", {"id": "整理"}, self.ctx)
        self.assertTrue(res.ok)

    def test_task_done_missing(self):
        res = self.app.tools.call("task.done", {"id": "不存在的任务"}, self.ctx)
        self.assertFalse(res.ok)

    def test_fs_read_and_escape(self):
        ok = self.app.tools.call("fs.read", {"path": "brain/config.py", "lines": 40}, self.ctx)
        self.assertTrue(ok.ok)
        self.assertIn("class Config", ok.data["text"])

        bad = self.app.tools.call("fs.read", {"path": "../../etc/passwd"}, self.ctx)
        self.assertFalse(bad.ok)
        self.assertIn("越界", bad.error)

    def test_fs_list(self):
        res = self.app.tools.call("fs.list", {"path": "brain"}, self.ctx)
        self.assertTrue(res.ok)
        self.assertTrue(any(row["name"] == "memory" for row in res.data))

    def test_git_status_does_not_crash(self):
        res = self.app.tools.call("git.status", {"sub": "status"}, self.ctx)
        self.assertIsNotNone(res)

    def test_git_rejects_unknown_subcommand(self):
        res = self.app.tools.call("git.status", {"sub": "push"}, self.ctx)
        self.assertFalse(res.ok)
        self.assertIn("只允许", res.error)

    def test_skill_run_unknown(self):
        res = self.app.tools.call("skill.run", {"name": "不存在的技能"}, self.ctx)
        self.assertFalse(res.ok)


class TestFrontMatter(unittest.TestCase):
    def test_scalars(self):
        meta, body = parse_front_matter("---\nname: a\nversion: 2\nflag: true\n---\n正文")
        self.assertEqual(meta["name"], "a")
        self.assertEqual(meta["version"], 2)
        self.assertIs(meta["flag"], True)
        self.assertEqual(body, "正文")

    def test_list_block(self):
        meta, _ = parse_front_matter("---\ntags:\n  - a\n  - b\n---\n")
        self.assertEqual(meta["tags"], ["a", "b"])

    def test_map_block(self):
        meta, _ = parse_front_matter("---\ninputs:\n  week: 周\n  out: 路径\n---\n")
        self.assertEqual(meta["inputs"], {"week": "周", "out": "路径"})

    def test_no_front_matter(self):
        meta, body = parse_front_matter("# 标题\n正文")
        self.assertEqual(meta, {})
        self.assertIn("标题", body)

    def test_unclosed_raises(self):
        with self.assertRaises(ValueError):
            parse_front_matter("---\nname: a\n正文")

    def test_bad_line_raises(self):
        with self.assertRaises(ValueError):
            parse_front_matter("---\n这不是键值对\n---\n")


class TestSkillLoader(BrainCase):
    def test_loads_three_shipped_skills(self):
        skills = self.app.loader.load_all()
        names = [s.name for s in skills]
        for expected in ("weekly-review", "decision-log", "note-to-knowledge"):
            self.assertIn(expected, names)
        self.assertTrue(all(s.executable for s in skills))
        self.assertFalse(any(s.status == "broken" for s in skills))

    def test_catalog_lists_descriptions(self):
        catalog = self.app.loader.catalog()
        self.assertIn("weekly-review", catalog)
        self.assertIn("复盘", catalog)

    def test_show_includes_body(self):
        text = self.app.loader.show("weekly-review")
        self.assertIn("解决什么问题", text)
        self.assertIn("handler.py", text)

    def test_require_missing(self):
        with self.assertRaises(KeyError):
            self.app.loader.require("没有这个")

    def test_broken_skill_detected(self):
        bad = self.skills_dir / "broken-one"
        bad.mkdir()
        (bad / "SKILL.md").write_text(
            "---\nname: broken-one\ndescription: 坏的\nhandler: handler.py\n---\n", encoding="utf-8"
        )
        self.app.loader.load_all(force=True)
        self.assertEqual(self.app.loader.get("broken-one").status, "broken")

    def test_missing_required_field_skipped(self):
        bad = self.skills_dir / "no-desc"
        bad.mkdir()
        (bad / "SKILL.md").write_text("---\nname: no-desc\n---\n", encoding="utf-8")
        self.app.loader.load_all(force=True)
        self.assertIsNone(self.app.loader.get("no-desc"))
        self.assertTrue(any("缺少必填字段" in w for w in self.app.loader.warnings))

    def test_duplicate_name_warns(self):
        dup = self.skills_dir / "dup"
        dup.mkdir()
        (dup / "SKILL.md").write_text("---\nname: weekly-review\ndescription: 重复\n---\n", encoding="utf-8")
        skills = self.app.loader.load_all(force=True)
        self.assertEqual(sum(1 for s in skills if s.name == "weekly-review"), 1)
        self.assertTrue(any("重复" in w for w in self.app.loader.warnings))


class TestSkillRuntime(BrainCase):
    def test_weekly_review_empty_week(self):
        result = self.app.skills.run("weekly-review", {"week": "2020-W01"}, ctx=self.app.context())
        self.assertTrue(result.ok)
        self.assertTrue(result.outputs.get("empty"))

    def test_weekly_review_rejects_bad_week(self):
        result = self.app.skills.run("weekly-review", {"week": "上周"}, ctx=self.app.context())
        self.assertFalse(result.ok)
        self.assertIn("周编号", result.error)

    def test_weekly_review_writes_report(self):
        ctx = self.app.context()
        self.app.memory.write("AR", "一次行动", status="ok", meta={"intent": "capture", "workflow": "memory.write"})
        result = self.app.skills.run("weekly-review", {}, ctx=ctx)
        self.assertTrue(result.ok)
        path = self.app.config.root / result.outputs["path"]
        self.assertTrue(path.is_file())
        self.assertIn("周复盘", path.read_text(encoding="utf-8"))

    def test_note_to_knowledge(self):
        ctx = self.app.context()
        result = self.app.skills.run("note-to-knowledge", {"query": "经验：先写测试再写实现"}, ctx=ctx)
        self.assertTrue(result.ok)
        self.assertEqual(len(self.app.memory.all("K")), 1)

    def test_note_to_knowledge_dedupes(self):
        ctx = self.app.context()
        first = self.app.skills.run("note-to-knowledge", {"query": "同一条笔记内容"}, ctx=ctx)
        second = self.app.skills.run("note-to-knowledge", {"query": "同一条笔记内容"}, ctx=ctx)
        self.assertEqual(first.outputs["id"], second.outputs["id"])
        self.assertEqual(len(self.app.memory.all("K")), 1)

    def test_decision_log(self):
        ctx = self.app.context()
        result = self.app.skills.run(
            "decision-log", {"query": "用纯 Python 实现索引", "reason": "零依赖", "options": "sqlite-fts5, whoosh"}, ctx=ctx
        )
        self.assertTrue(result.ok)
        self.assertIn("ADR-", result.outputs["path"])
        self.assertEqual(len(self.app.memory.all("K")), 1)

    def test_prompt_only_skill(self):
        doc = self.skills_dir / "just-words"
        doc.mkdir()
        (doc / "SKILL.md").write_text("---\nname: just-words\ndescription: 只有说明\n---\n步骤一二三", encoding="utf-8")
        result = self.app.skills.run("just-words", {}, ctx=self.app.context())
        self.assertTrue(result.ok)
        self.assertEqual(result.mode, "prompt")

    def test_handler_exception_captured(self):
        bad = self.skills_dir / "boom"
        bad.mkdir()
        (bad / "SKILL.md").write_text(
            "---\nname: boom\ndescription: 会炸\nhandler: handler.py\n---\n", encoding="utf-8"
        )
        (bad / "handler.py").write_text("def run(ctx, args):\n    raise RuntimeError('炸了')\n", encoding="utf-8")
        result = self.app.skills.run("boom", {}, ctx=self.app.context())
        self.assertFalse(result.ok)
        self.assertIn("炸了", result.error)

    def test_usage_recorded(self):
        ctx = self.app.context()
        self.app.skills.run("weekly-review", {"week": "2020-W01"}, ctx=ctx)
        self.app.skills.run("weekly-review", {"week": "2020-W02"}, ctx=ctx)
        stats = self.app.skills.stats()
        self.assertEqual(stats["weekly-review"]["calls"], 2)
        self.assertEqual(stats["weekly-review"]["ok"], 2)

    def test_create_skill_scaffold(self):
        info = create_skill(self.app.config, "我的新技能", description="测试用")
        self.assertTrue(info["ok"])
        self.app.loader.load_all(force=True)
        self.assertIsNotNone(self.app.loader.get("我的新技能"))

    def test_create_skill_twice(self):
        create_skill(self.app.config, "重复技能")
        second = create_skill(self.app.config, "重复技能")
        self.assertFalse(second["ok"])


if __name__ == "__main__":
    unittest.main()
