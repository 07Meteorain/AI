import unittest

from promptlint.engine import CheckResult
from promptlint.model import Finding, SourceFile
from promptlint.rules import RULES
from promptlint.sarif import build_sarif


def make_result(severity="warning", rule="PL009"):
    source = SourceFile("a.prompt", "prompts/a.prompt", "x", ["x"])
    finding = Finding(
        rule_id=rule,
        severity=severity,
        message="untrusted input '{{user_message}}' is not delimited",
        line=3,
        column=2,
        end_line=3,
        end_column=9,
        snippet="{{user_message}}",
    )
    return CheckResult([(source, [finding])], 0)


class SarifTests(unittest.TestCase):
    def test_envelope(self):
        payload = build_sarif(make_result())
        self.assertEqual(payload["version"], "2.1.0")
        self.assertIn("sarif", payload["$schema"])
        self.assertEqual(len(payload["runs"]), 1)
        driver = payload["runs"][0]["tool"]["driver"]
        self.assertEqual(driver["name"], "promptlint")
        self.assertEqual(len(driver["rules"]), len(RULES))

    def test_result_mapping(self):
        payload = build_sarif(make_result())
        result = payload["runs"][0]["results"][0]
        self.assertEqual(result["ruleId"], "PL009")
        expected_index = [rule.id for rule in RULES].index("PL009")
        self.assertEqual(result["ruleIndex"], expected_index)
        self.assertEqual(result["level"], "warning")
        region = result["locations"][0]["physicalLocation"]["region"]
        self.assertEqual(region["startLine"], 3)
        self.assertEqual(region["startColumn"], 2)
        self.assertGreater(region["endColumn"], region["startColumn"])
        self.assertEqual(
            result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
            "prompts/a.prompt",
        )

    def test_levels(self):
        self.assertEqual(build_sarif(make_result("error"))["runs"][0]["results"][0]["level"], "error")
        self.assertEqual(build_sarif(make_result("info"))["runs"][0]["results"][0]["level"], "note")

    def test_fingerprints_present(self):
        result = build_sarif(make_result())["runs"][0]["results"][0]
        self.assertIn("promptlint/v1", result["partialFingerprints"])
        self.assertEqual(len(result["partialFingerprints"]["promptlint/v1"]), 40)

    def test_empty_results(self):
        payload = build_sarif(CheckResult([], 0))
        self.assertEqual(payload["runs"][0]["results"], [])


if __name__ == "__main__":
    unittest.main()
