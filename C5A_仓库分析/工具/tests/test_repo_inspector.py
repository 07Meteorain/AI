#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repo_inspector 的单元测试（仅用标准库 unittest，零第三方依赖）。

运行::

    cd 工具
    python -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_inspector as ri  # noqa: E402


def run(cmd, cwd, env=None):
    subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env or dict(os.environ, GIT_TERMINAL_PROMPT="0"),
    )


def make_repo(root):
    run(["git", "init", "-q", "-b", "main"], root)
    run(["git", "config", "user.name", "Test User"], root)
    run(["git", "config", "user.email", "test@example.com"], root)
    run(["git", "config", "commit.gpgsign", "false"], root)

    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text(
        "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    run(["git", "add", "-A"], root)
    run(["git", "commit", "-q", "-m", "feat: initial commit"], root)

    (root / "app.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    run(["git", "add", "-A"], root)
    run(["git", "commit", "-q", "-m", "feat(core): add subtraction"], root)
    run(["git", "tag", "v1.0.0"], root)


def full_metrics():
    """构造一份所有检查都通过的指标，用于验证满分边界。"""
    return {
        "repo": {
            "last_commit_age_days": 1,
            "age_days": 100,
            "total_commits": 10,
        },
        "files": {"source_loc": 100, "test_loc": 50, "test_file_count": 10},
        "commits": {
            "total": 10,
            "merges": 3,
            "conventional_ratio": 0.8,
            "subject_avg_len": 40.0,
            "subject_gt_72_ratio": 0.0,
        },
        "branches": {"stale_ratio": 0.0, "stale_count": 0, "remote_count": 2},
        "tags": {"count": 3, "latest": "v1.0.0"},
        "governance": {
            "checks": {
                "readme": True,
                "license": True,
                "contributing": True,
                "changelog": True,
                "code_of_conduct": True,
                "security": True,
                "ci": True,
                "issue_templates": True,
                "dependabot": True,
                "release_workflow": True,
                "tests": True,
                "test_files": True,
            }
        },
    }


class HelperTests(unittest.TestCase):
    def test_count_lines(self):
        self.assertEqual(ri.count_lines(b""), 0)
        self.assertEqual(ri.count_lines(b"a\nb\n"), 2)
        self.assertEqual(ri.count_lines(b"a\nb"), 2)

    def test_is_binary(self):
        self.assertFalse(ri.is_binary(b"hello\n"))
        self.assertTrue(ri.is_binary(b"abc\x00def"))

    def test_classify_commit(self):
        parsed = ri.classify_commit("feat(parser): support nested JSON")
        self.assertEqual(parsed, ("feat", "parser", False))
        self.assertEqual(ri.classify_commit("fix!: breaking change")[2], True)
        self.assertIsNone(ri.classify_commit("Fix a bug"))
        self.assertIsNone(ri.classify_commit("feat:no space"))

    def test_extension_and_directory(self):
        self.assertEqual(ri.extension_of("a/b/c.PY"), ".py")
        self.assertEqual(ri.extension_of("Makefile"), "(无扩展名)")
        self.assertEqual(ri.directory_of("a/b/c.py"), "a")
        self.assertEqual(ri.directory_of("README.md"), "(根目录)")

    def test_test_path_matching(self):
        self.assertTrue(ri.is_test_path("tests/test_app.py"))
        self.assertTrue(ri.is_test_path("tests/tests.py"))
        self.assertTrue(ri.is_test_path("pkg/foo_test.go"))
        self.assertTrue(ri.is_test_path("web/App.test.tsx"))
        self.assertFalse(ri.is_test_path("tests/fixtures/data.xml"))
        self.assertFalse(ri.is_test_path("httpie/cli.py"))

    def test_is_source(self):
        self.assertTrue(ri.is_source("a.py"))
        self.assertFalse(ri.is_source("README.md"))

    def test_human_bytes(self):
        self.assertEqual(ri.human_bytes(512), "512 B")
        self.assertEqual(ri.human_bytes(2048), "2.0 KB")
        self.assertEqual(ri.human_bytes(3 * 1024 * 1024), "3.0 MB")

    def test_pct(self):
        self.assertEqual(ri.pct(1, 4), "25.0%")
        self.assertEqual(ri.pct(1, 0), "—")


class HealthTests(unittest.TestCase):
    def test_full_score_is_100(self):
        health = ri.compute_health(full_metrics())
        self.assertEqual(health["score"], 100)
        self.assertEqual(health["findings"], ["未发现显著风险信号。"])

    def test_missing_readme_and_ci_reduces_score(self):
        metrics = full_metrics()
        metrics["governance"]["checks"]["readme"] = False
        metrics["governance"]["checks"]["ci"] = False
        health = ri.compute_health(metrics)
        self.assertEqual(health["score"], 100 - 6 - 8)
        self.assertTrue(any("README" in item for item in health["findings"]))

    def test_inactive_and_stale_branches(self):
        metrics = full_metrics()
        metrics["repo"]["last_commit_age_days"] = 500
        metrics["branches"]["stale_ratio"] = 0.9
        metrics["branches"]["stale_count"] = 9
        metrics["branches"]["remote_count"] = 10
        health = ri.compute_health(metrics)
        self.assertEqual(health["score"], 100 - 8 - 7)
        self.assertTrue(any("低活跃" in item for item in health["findings"]))


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_inspect_smoke(self):
        metrics = ri.inspect_repo(self.root)
        self.assertEqual(metrics["repo"]["total_commits"], 2)
        self.assertEqual(metrics["files"]["tracked"], 3)
        self.assertEqual(metrics["files"]["test_file_count"], 1)
        self.assertEqual(metrics["commits"]["conventional_count"], 2)
        self.assertEqual(metrics["tags"]["count"], 1)
        self.assertEqual(metrics["branches"]["default"], "main")
        self.assertIn("health", metrics)
        self.assertGreaterEqual(metrics["health"]["score"], 0)

    def test_markdown_sections(self):
        markdown = ri.render_markdown(ri.inspect_repo(self.root))
        for section in [
            "## 1. 概览",
            "## 2. 文件与语言构成",
            "## 3. 提交与协作习惯",
            "## 4. 工程治理清单",
            "## 5. 变更热点与测试联动",
            "## 6. 健康度评分",
        ]:
            self.assertIn(section, markdown)
        self.assertIn("Test User", markdown)

    def test_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(ri.GitError):
                ri.inspect_repo(other)

    def test_stale_branch_detection(self):
        old_env = dict(
            os.environ,
            GIT_TERMINAL_PROMPT="0",
            GIT_AUTHOR_DATE="2020-01-01T00:00:00+00:00",
            GIT_COMMITTER_DATE="2020-01-01T00:00:00+00:00",
        )
        run(["git", "checkout", "-q", "-b", "old/topic"], self.root)
        (self.root / "old.txt").write_text("old\n", encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-q", "-m", "docs: old topic"], self.root, env=old_env)
        run(["git", "update-ref", "refs/remotes/origin/old/topic", "HEAD"], self.root)
        run(["git", "checkout", "-q", "main"], self.root)
        metrics = ri.inspect_repo(self.root, stale_days=180)
        names = [item["name"] for item in metrics["branches"]["stale"]]
        self.assertIn("origin/old/topic", names)


if __name__ == "__main__":
    unittest.main()
