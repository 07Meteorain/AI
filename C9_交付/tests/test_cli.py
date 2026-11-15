"""CLI 端到端测试。"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall import cli  # noqa: E402
from recall.store import connect, list_cards, stats  # noqa: E402

EXAMPLES = str(ROOT / "examples" / "notes")


def run(args):
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(args)
    return code, out.getvalue(), err.getvalue()


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.out = os.path.join(self.tmp.name, "out")

    def build(self):
        code, output, err = run(["build", EXAMPLES, "--db", self.db])
        self.assertEqual(code, 0, err)
        return output

    def conn(self):
        return connect(self.db)


class TestBuild(CliCase):
    def test_build_examples(self):
        output = self.build()
        self.assertIn("扫描 3 篇笔记", output)
        self.assertIn("通过", output)
        self.assertTrue(os.path.isfile(self.db))
        conn = self.conn()
        self.addCleanup(conn.close)
        self.assertGreaterEqual(len(list_cards(conn)), 15)

    def test_build_json(self):
        code, output, _ = run(["build", EXAMPLES, "--db", self.db, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["files"], 3)
        self.assertGreater(data["accepted"], 10)
        self.assertIn("by_kind", data)

    def test_build_missing_path(self):
        code, _, err = run(["build", os.path.join(self.tmp.name, "nope"), "--db", self.db])
        self.assertEqual(code, 1)
        self.assertIn("找不到", err)

    def test_build_no_cards(self):
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        with open(os.path.join(empty, "a.md"), "w", encoding="utf-8") as fh:
            fh.write("# 标题\n\n没有可出卡的结构。\n")
        code, _, err = run(["build", empty, "--db", self.db])
        self.assertEqual(code, 1)
        self.assertIn("没有抽到", err)

    def test_build_out_json(self):
        path = os.path.join(self.tmp.name, "deck.json")
        code, _, _ = run(["build", EXAMPLES, "--db", self.db, "--out", path])
        self.assertEqual(code, 0)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertGreater(len(payload["cards"]), 10)

    def test_build_kinds_filter(self):
        code, _, _ = run(["build", EXAMPLES, "--db", self.db, "--kinds", "term-list"])
        self.assertEqual(code, 0)
        conn = self.conn()
        self.addCleanup(conn.close)
        cards = list_cards(conn)
        self.assertTrue(cards)
        self.assertTrue(all(card.kind == "term-list" for card in cards))


class TestStatsAndReview(CliCase):
    def test_stats_json(self):
        self.build()
        code, output, _ = run(["stats", "--db", self.db, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["total"], data["approved"])
        self.assertIn("forecast", data)

    def test_scripted_review(self):
        self.build()
        code, output, _ = run(
            ["review", "--db", self.db, "--limit", "3", "--script", "3,2,4", "--today", "2026-11-15"]
        )
        self.assertEqual(code, 0, output)
        self.assertIn("本轮复习 3 张", output)
        conn = self.conn()
        self.addCleanup(conn.close)
        self.assertEqual(stats(conn, "2026-11-16")["due"], 3)

    def test_review_json(self):
        self.build()
        code, output, _ = run(
            ["review", "--db", self.db, "--limit", "2", "--script", "3,3", "--today", "2026-11-15", "--json"]
        )
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["reviewed"], 2)
        self.assertEqual(data["tally"]["3"], 2)

    def test_review_without_tty(self):
        self.build()
        with mock.patch("sys.stdin", io.StringIO("")):
            code, _, err = run(["review", "--db", self.db, "--limit", "1"])
        self.assertEqual(code, 1)
        self.assertIn("--script", err)

    def test_review_script_too_short(self):
        self.build()
        code, _, err = run(["review", "--db", self.db, "--limit", "3", "--script", "3"])
        self.assertEqual(code, 1)
        self.assertIn("--script", err)

    def test_review_empty_db(self):
        code, _, err = run(["review", "--db", self.db])
        self.assertEqual(code, 1)
        self.assertIn("没有卡片", err)

    def test_review_bad_today(self):
        self.build()
        code, _, err = run(["review", "--db", self.db, "--script", "3", "--today", "15/11/2026"])
        self.assertEqual(code, 1)
        self.assertIn("YYYY-MM-DD", err)

    def test_review_nothing_due(self):
        self.build()
        run(["review", "--db", self.db, "--limit", "1", "--script", "3", "--today", "2026-11-15"])
        code, output, _ = run(
            ["review", "--db", self.db, "--limit", "1", "--new-limit", "0", "--script", "3", "--today", "2026-11-15"]
        )
        self.assertEqual(code, 0)
        self.assertIn("没有到期", output)


class TestSampleApplyExport(CliCase):
    def test_sample_to_file(self):
        self.build()
        path = os.path.join(self.tmp.name, "audit.md")
        code, output, _ = run(["sample", "--db", self.db, "--n", "5", "--out", path])
        self.assertEqual(code, 0)
        self.assertIn("抽样 5 张", output)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("# Recall 抽样审核", text)
        self.assertIn("| 1 |", text)

    def test_apply_decisions(self):
        self.build()
        conn = self.conn()
        ids = [card.id for card in list_cards(conn)]
        conn.close()
        path = os.path.join(self.tmp.name, "decisions.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"approved": ids[1:], "rejected": [ids[0]], "missing": []}, fh)
        code, output, _ = run(["apply", path, "--db", self.db])
        self.assertEqual(code, 0)
        self.assertIn("剔除 1 张", output)
        conn = self.conn()
        self.addCleanup(conn.close)
        self.assertEqual(stats(conn)["rejected"], 1)

    def test_apply_bad_file(self):
        code, _, err = run(["apply", os.path.join(self.tmp.name, "nope.json"), "--db", self.db])
        self.assertEqual(code, 1)
        self.assertIn("找不到", err)

    def test_export_json(self):
        self.build()
        path = os.path.join(self.tmp.name, "deck.json")
        code, _, _ = run(["export", "--db", self.db, "--out", path])
        self.assertEqual(code, 0)
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertGreater(len(payload["cards"]), 10)

    def test_export_csv(self):
        self.build()
        path = os.path.join(self.tmp.name, "deck.csv")
        code, _, _ = run(["export", "--db", self.db, "--format", "csv", "--out", path])
        self.assertEqual(code, 0)
        text = Path(path).read_text(encoding="utf-8-sig")
        self.assertIn("id,kind,status,prompt", text)
        self.assertGreater(len(text.splitlines()), 5)


class TestOtherCommands(CliCase):
    def test_web(self):
        self.build()
        site = os.path.join(self.tmp.name, "site")
        code, output, _ = run(["web", "--db", self.db, "--out", site])
        self.assertEqual(code, 0)
        self.assertIn("张卡", output)
        self.assertTrue(os.path.isfile(os.path.join(site, "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(site, "deck.js")))

    def test_doctor(self):
        code, output, _ = run(["doctor", EXAMPLES])
        self.assertEqual(code, 0)
        self.assertIn("诊断 3 篇笔记", output)
        self.assertIn("平均可出卡性", output)

    def test_doctor_json(self):
        code, output, _ = run(["doctor", EXAMPLES, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(len(data), 3)
        self.assertIn("score", data[0])

    def test_doctor_missing(self):
        code, _, err = run(["doctor", os.path.join(self.tmp.name, "nope")])
        self.assertEqual(code, 1)
        self.assertIn("找不到", err)

    def test_selfcheck(self):
        code, output, _ = run(["selfcheck"])
        self.assertEqual(code, 0)
        self.assertIn("SELF-CHECK OK", output)

    def test_version(self):
        code, output, _ = run(["version"])
        self.assertEqual(code, 0)
        self.assertIn("1.0.0", output)

    def test_unknown_command(self):
        with self.assertRaises(SystemExit):
            run(["nope"])


if __name__ == "__main__":
    unittest.main()
