import unittest

from promptlint.config import Config
from promptlint.engine import lint_text
from promptlint.tokens import estimate_tokens


def findings(text, config=None):
    return lint_text(text, config=config or Config())


LONG_INSTRUCTIONS = "Summarise the article carefully and completely. " * 12


class OutputContractTests(unittest.TestCase):
    def test_short_prompt_is_exempt(self):
        found = findings("Explain gravity briefly.\n")
        self.assertFalse(any(item.rule_id == "PL007" for item in found))

    def test_long_prompt_without_contract_is_flagged(self):
        found = findings(LONG_INSTRUCTIONS + "\n")
        self.assertTrue(any(item.rule_id == "PL007" for item in found))

    def test_long_prompt_with_json_contract_is_clean(self):
        found = findings(LONG_INSTRUCTIONS + "\nReturn JSON.\n")
        self.assertFalse(any(item.rule_id == "PL007" for item in found))

    def test_chinese_contract_keyword(self):
        found = findings(LONG_INSTRUCTIONS + "\n请用表格输出。\n")
        self.assertFalse(any(item.rule_id == "PL007" for item in found))


class DuplicateTests(unittest.TestCase):
    def test_duplicate_line_is_flagged_once(self):
        line = "Always answer in English and cite your sources."
        found = [item for item in findings(line + "\n" + line + "\n") if item.rule_id == "PL008"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].line, 2)

    def test_duplicate_inside_fence_is_ignored(self):
        line = "Always answer in English and cite your sources."
        found = findings("```\n%s\n%s\n```\n" % (line, line))
        self.assertFalse(any(item.rule_id == "PL008" for item in found))

    def test_short_repeated_lines_are_allowed(self):
        found = findings("- be nice\n- be nice\n")
        self.assertFalse(any(item.rule_id == "PL008" for item in found))


class TokenBudgetTests(unittest.TestCase):
    def test_too_long_uses_configured_budget(self):
        found = findings("word " * 100, Config(max_tokens=10))
        self.assertTrue(any(item.rule_id == "PL010" for item in found))

    def test_within_budget(self):
        found = findings("word " * 100, Config(max_tokens=1000))
        self.assertFalse(any(item.rule_id == "PL010" for item in found))

    def test_estimate_is_deterministic_and_wide_aware(self):
        self.assertEqual(estimate_tokens("hello world"), 3)
        self.assertEqual(estimate_tokens("你好"), 2)
        self.assertEqual(estimate_tokens(""), 1)


if __name__ == "__main__":
    unittest.main()
