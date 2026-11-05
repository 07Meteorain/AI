# -*- coding: utf-8 -*-
"""question_lint 的回归测试。运行：python -m unittest discover -s tests -v"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import question_lint as ql  # noqa: E402

FENCE = chr(96) * 3
CASES = ROOT / "cases"


def read_case(name):
    return (CASES / name).read_text(encoding="utf-8")


DRAFT_EMPTY = "我想问个问题。"

DRAFT_CONTEXT = DRAFT_EMPTY + "\n环境：Windows 11 / Python 3.14.2。目标：批量读取 300 个 csv 并合并。"

DRAFT_ATTEMPTS = DRAFT_CONTEXT + "\n已尝试：\n1. 用 os.listdir 列目录 → 仍然漏掉子目录\n2. 换成 pathlib.rglob → 还是慢"

DRAFT_BLOCKER = DRAFT_ATTEMPTS + "\n卡点：报错 PermissionError: [WinError 5]，出现在 merge.py 第 42 行。"

DRAFT_EVIDENCE = DRAFT_BLOCKER + "\n复现：1) 运行 merge.py 2) 指向 D:\\数据 3) 报错。\n" + FENCE + "text\nPermissionError: [WinError 5]\n" + FENCE

DRAFT_EXPECT = DRAFT_EVIDENCE + "\n期望：合并出 result.csv。实际：直接抛异常退出。"

DRAFT_ASK = DRAFT_EXPECT + "\n想问下：是遍历方式的问题，还是权限本身被系统拦了？有没有办法在不改代码的情况下验证？"


class TestScoreLadder(unittest.TestCase):
    def test_case_ordering(self):
        bad = ql.lint(read_case("bad_01.md"))["score"]
        mid = ql.lint(read_case("mid_01.md"))["score"]
        good = ql.lint(read_case("good_01.md"))["score"]
        self.assertLess(bad, 40, "坏样例应低于 40 分，实际 %.1f" % bad)
        self.assertLess(mid, 60, "中样例应低于 60 分，实际 %.1f" % mid)
        self.assertGreaterEqual(good, 85, "好样例应不低于 85 分，实际 %.1f" % good)
        self.assertLess(bad, mid)
        self.assertLess(mid, good)

    def test_rating_bands(self):
        self.assertEqual(ql.lint("")["rating"], "E")
        self.assertEqual(ql.lint(read_case("good_01.md"))["rating"], "A")


class TestElementMonotonicity(unittest.TestCase):
    def test_each_element_adds_points(self):
        chain = [DRAFT_EMPTY, DRAFT_CONTEXT, DRAFT_ATTEMPTS, DRAFT_BLOCKER,
                 DRAFT_EVIDENCE, DRAFT_EXPECT, DRAFT_ASK]
        scores = [ql.lint(t)["score"] for t in chain]
        for a, b in zip(scores, scores[1:]):
            self.assertLessEqual(a, b, "补要素后分数不应下降：%s" % scores)
        self.assertGreaterEqual(scores[-1], 85, "六要素齐全应 >= 85，实际 %s" % scores)

    def test_attempts_from_list_items(self):
        res = ql.lint(DRAFT_ATTEMPTS)
        attempts = [e for e in res["elements"] if e["key"] == "attempts"][0]
        self.assertGreater(attempts["ratio"], 0.9, "编号列表写的尝试应被识别")


class TestNegativeSignals(unittest.TestCase):
    def test_emotion_penalized(self):
        base = ql.lint(read_case("mid_01.md"))["score"]
        noisy = ql.lint(read_case("mid_01.md").replace("怎么回事？", "救命！！！怎么回事？？？"))["score"]
        self.assertLess(noisy, base)

    def test_empty_text_penalized(self):
        self.assertLessEqual(ql.lint("报错了")["score"], 0.0 + 15.0)

    def test_short_text_flag(self):
        res = ql.lint("短")
        names = [n["name"] for n in res["negatives"]]
        self.assertIn("empty", names)


class TestCli(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "question_lint.py")] + list(args),
            input=stdin, capture_output=True, text=True, encoding="utf-8", env=env,
        )

    def test_json_output(self):
        r = self.run_cli("--json", str(CASES / "good_01.md"))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(len(data), 1)
        self.assertIn("score", data[0])
        self.assertEqual(len(data[0]["elements"]), 6)

    def test_min_threshold_exit_code(self):
        r = self.run_cli("--min", "90", str(CASES / "bad_01.md"))
        self.assertEqual(r.returncode, 2)

    def test_batch(self):
        r = self.run_cli("--batch", str(CASES), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertGreaterEqual(len(data), 3)

    def test_stdin(self):
        r = self.run_cli(stdin=read_case("good_01.md"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("得分", r.stdout)

    def test_selftest(self):
        r = self.run_cli("--selftest")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
