import unittest

from promptlint.config import Config
from promptlint.engine import lint_text


def rules(text, config=None):
    return [finding.rule_id for finding in lint_text(text, config=config or Config())]


class StructureRuleTests(unittest.TestCase):
    def test_empty_prompt(self):
        self.assertIn("PL001", rules("   \n\n"))

    def test_front_matter_only_is_empty(self):
        found = rules("---\nvars: [a]\n---\n")
        self.assertIn("PL001", found)

    def test_undeclared_placeholder(self):
        found = rules("---\nvars: [topic]\n---\nWrite about {{topik}}.\n")
        self.assertIn("PL002", found)

    def test_undeclared_check_is_skipped_without_vars(self):
        found = rules("Write about {{anything}}.\n")
        self.assertNotIn("PL002", found)

    def test_unused_variable(self):
        found = rules("---\nvars: [a, b]\n---\nUse {{a}}.\n")
        self.assertIn("PL003", found)

    def test_unused_variable_points_at_declaration(self):
        findings = lint_text("---\nvars: [a, b]\n---\nUse {{a}}.\n")
        unused = [item for item in findings if item.rule_id == "PL003"]
        self.assertEqual(len(unused), 1)
        self.assertEqual(unused[0].line, 2)
        self.assertIn("'b'", unused[0].message)

    def test_malformed_placeholders(self):
        found = rules("Hello {{name\nEmpty {{ }} and {{1st}}\n")
        self.assertEqual(found.count("PL004"), 3)

    def test_invalid_front_matter(self):
        found = rules("---\nvars: topic\n---\nHello {{x}}\n")
        self.assertIn("PL012", found)
        self.assertIn("PL002", found)

    def test_clean_template_has_no_structure_findings(self):
        found = rules("---\nvars: [topic]\n---\nReturn JSON about {{topic}}.\n")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
