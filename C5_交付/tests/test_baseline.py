import tempfile
import unittest
from pathlib import Path

from promptlint.baseline import (
    fingerprint,
    load_baseline,
    save_baseline,
)
from promptlint.engine import apply_baseline
from promptlint.model import Finding, SourceFile


def finding(line=1, message="untrusted input is not delimited", rule="PL009"):
    return Finding(
        rule_id=rule,
        severity="warning",
        message=message,
        line=line,
        column=1,
        end_line=line,
        end_column=2,
        snippet="{{user_message}}",
    )


class BaselineTests(unittest.TestCase):
    def test_fingerprint_ignores_line_numbers(self):
        first = finding(line=3)
        second = finding(line=90)
        self.assertEqual(
            fingerprint("prompts/a.prompt", first),
            fingerprint("prompts/a.prompt", second),
        )

    def test_fingerprint_changes_with_rule(self):
        self.assertNotEqual(
            fingerprint("a.prompt", finding(rule="PL009")),
            fingerprint("a.prompt", finding(rule="PL007")),
        )

    def test_fingerprint_distinguishes_occurrences(self):
        self.assertNotEqual(
            fingerprint("a.prompt", finding(), 0),
            fingerprint("a.prompt", finding(), 1),
        )

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.json"
            written = save_baseline(path, ["abc", "def", "abc"])
            self.assertEqual(written, 2)
            self.assertEqual(load_baseline(path), {"abc", "def"})

    def test_apply_baseline_suppresses_known_findings(self):
        source = SourceFile("a.prompt", "a.prompt", "x", ["x"])
        results = [(source, [finding()])]
        known = {fingerprint("a.prompt", finding())}
        filtered, suppressed = apply_baseline(results, known)
        self.assertEqual(suppressed, 1)
        self.assertEqual(filtered[0][1], [])

    def test_unknown_finding_survives(self):
        source = SourceFile("a.prompt", "a.prompt", "x", ["x"])
        results = [(source, [finding()])]
        filtered, suppressed = apply_baseline(results, {"deadbeef"})
        self.assertEqual(suppressed, 0)
        self.assertEqual(len(filtered[0][1]), 1)

    def test_only_the_accepted_occurrence_is_suppressed(self):
        source = SourceFile("a.prompt", "a.prompt", "x", ["x"])
        results = [(source, [finding(line=1), finding(line=2)])]
        known = {fingerprint("a.prompt", finding(), 0)}
        filtered, suppressed = apply_baseline(results, known)
        self.assertEqual(suppressed, 1)
        self.assertEqual(len(filtered[0][1]), 1)
        self.assertEqual(filtered[0][1][0].line, 2)


if __name__ == "__main__":
    unittest.main()
