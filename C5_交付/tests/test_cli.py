import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from promptlint.cli import main


@contextlib.contextmanager
def chdir(path):
    old = os.getcwd()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(old)


def run(args, cwd=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if cwd is None:
            code = main(args)
        else:
            with chdir(cwd):
                code = main(args)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_version(self):
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--version"])
        self.assertEqual(raised.exception.code, 0)

    def test_no_command_returns_usage(self):
        code, out, _ = run([])
        self.assertEqual(code, 2)
        self.assertIn("usage", out.lower())

    def test_clean_file_exits_zero(self):
        path = self.write("ok.prompt", "Return JSON.\n")
        code, out, _ = run(["check", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("No problems found", out)

    def test_finding_exits_one(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        code, out, _ = run(["check", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("PL009", out)

    def test_fail_on_none(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        code, _, _ = run(["check", str(path), "--fail-on", "none"])
        self.assertEqual(code, 0)

    def test_fail_on_error_ignores_warning(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        code, _, _ = run(["check", str(path), "--fail-on", "error"])
        self.assertEqual(code, 0)

    def test_json_format(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        code, out, _ = run(["check", str(path), "--format", "json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["tool"], "promptlint")
        self.assertEqual(payload["summary"]["findings"], 1)
        self.assertEqual(payload["files"][0]["findings"][0]["rule"], "PL009")

    def test_sarif_output_file(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        output = self.root / "reports" / "out.sarif"
        code, out, err = run(
            ["check", str(path), "--format", "sarif", "--output", str(output)]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("wrote", err)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], "2.1.0")

    def test_rules_json(self):
        code, out, _ = run(["rules", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["rules"]), 12)
        self.assertEqual(payload["rules"][0]["id"], "PL001")

    def test_explain(self):
        code, out, _ = run(["explain", "pl005"])
        self.assertEqual(code, 0)
        self.assertIn("PL005", out)
        self.assertIn("Bad example", out)

    def test_explain_unknown(self):
        code, out, err = run(["explain", "PL999"])
        self.assertEqual(code, 1)
        self.assertIn("unknown rule", err)

    def test_init_and_overwrite_guard(self):
        code, _, _ = run(["init"], cwd=self.root)
        self.assertEqual(code, 0)
        config = self.root / "promptlint.json"
        self.assertTrue(config.is_file())
        self.assertIn("max_tokens", json.loads(config.read_text(encoding="utf-8")))

        code, _, err = run(["init"], cwd=self.root)
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

        code, _, _ = run(["init", "--force"], cwd=self.root)
        self.assertEqual(code, 0)

    def test_baseline_flow(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        baseline = self.root / "nested" / "baseline.json"
        code, out, _ = run(["baseline", str(path), "--output", str(baseline)])
        self.assertEqual(code, 0)
        self.assertTrue(baseline.is_file())
        self.assertIn("Wrote 1 fingerprint", out)

        code, out, _ = run(["check", str(path), "--baseline", str(baseline)])
        self.assertEqual(code, 0)
        self.assertIn("suppressed by baseline", out)

    def test_init_creates_parent_directory(self):
        target = self.root / "config" / "promptlint.json"
        code, _, _ = run(["init", "--output", str(target)])
        self.assertEqual(code, 0)
        self.assertTrue(target.is_file())

    def test_missing_path(self):
        code, _, err = run(["check", str(self.root / "does-not-exist")])
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)

    def test_config_disables_rule(self):
        path = self.write("bad.prompt", "{{user_message}}\n")
        config = self.write("promptlint.json", json.dumps({"rules": {"PL009": "off"}}))
        code, _, _ = run(["check", str(path), "--config", str(config)])
        self.assertEqual(code, 0)

    def test_config_is_discovered_upward(self):
        path = self.write("prompts/bad.prompt", "word " * 100)
        self.write("promptlint.json", json.dumps({"max_tokens": 5}))
        code, out, _ = run(
            ["check", str(self.root / "prompts")], cwd=self.root / "prompts"
        )
        self.assertEqual(code, 1)
        self.assertIn("PL010", out)

    def test_max_tokens_override(self):
        path = self.write("long.prompt", "word " * 50)
        code, out, _ = run(["check", str(path), "--max-tokens", "5"])
        self.assertEqual(code, 1)
        self.assertIn("PL010", out)


if __name__ == "__main__":
    unittest.main()
