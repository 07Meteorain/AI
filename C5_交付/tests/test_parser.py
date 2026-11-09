import unittest

from promptlint.parser import line_offset, parse_prompt


class ParserTests(unittest.TestCase):
    def test_inline_vars(self):
        parsed = parse_prompt("---\nvars: [a, b]\n---\nHi {{a}} and {{b}}\n")
        self.assertTrue(parsed.vars_declared)
        self.assertEqual(set(parsed.vars), {"a", "b"})
        self.assertEqual(parsed.body_start, 3)
        self.assertEqual(parsed.body_line, 4)
        self.assertEqual([item.name for item in parsed.placeholders], ["a", "b"])

    def test_block_vars_keep_declaration_lines(self):
        parsed = parse_prompt("---\nvars:\n  - a\n  - b\n---\n{{a}} {{b}}\n")
        self.assertEqual(set(parsed.vars), {"a", "b"})
        self.assertEqual(parsed.vars["a"].line, 3)
        self.assertEqual(parsed.vars["b"].line, 4)
        self.assertIn("vars", parsed.front_matter)

    def test_placeholders_inside_fences_are_ignored(self):
        parsed = parse_prompt("```\n{{inside}}\n```\n{{outside}}\n")
        self.assertEqual([item.name for item in parsed.placeholders], ["outside"])
        self.assertTrue(parsed.fenced[0])
        self.assertFalse(parsed.fenced[3])

    def test_inline_code_is_ignored(self):
        parsed = parse_prompt("Use `{{literal}}` and {{real}}\n")
        self.assertEqual([item.name for item in parsed.placeholders], ["real"])

    def test_whitespace_inside_braces_is_normalised(self):
        parsed = parse_prompt("Hello {{ name }}\n")
        self.assertEqual(parsed.placeholders[0].name, "name")
        self.assertTrue(parsed.placeholders[0].valid)

    def test_unclosed_front_matter_is_reported(self):
        parsed = parse_prompt("---\nvars: [a]\nHello\n")
        self.assertEqual(parsed.body_start, 0)
        self.assertTrue(any(issue.rule_id == "PL012" for issue in parsed.issues))
        self.assertEqual(parsed.issues[0].line, 1)

    def test_unbalanced_delimiters_are_reported(self):
        parsed = parse_prompt("Hello {{name\n")
        messages = [issue.message for issue in parsed.issues]
        self.assertTrue(any("unbalanced" in message for message in messages))
        self.assertEqual(parsed.issues[0].column, 7)

    def test_orphan_closing_braces_are_reported(self):
        parsed = parse_prompt("{{ok}} }}\n")
        self.assertEqual(len(parsed.placeholders), 1)
        self.assertTrue(any("'}}'" in issue.message for issue in parsed.issues))

    def test_no_front_matter(self):
        parsed = parse_prompt("Just a prompt.\n")
        self.assertFalse(parsed.vars_declared)
        self.assertEqual(parsed.body_start, 0)
        self.assertEqual(parsed.front_matter, {})

    def test_line_offset(self):
        self.assertEqual(line_offset(["ab", "cd"], 2, 1), 3)
        self.assertEqual(line_offset(["ab", "cd"], 2, 3), 5)

    def test_crlf_is_normalised(self):
        parsed = parse_prompt("first\r\nsecond {{name}}\r\n")
        self.assertEqual(parsed.lines, ["first", "second {{name}}"])
        self.assertEqual(parsed.placeholders[0].line, 2)
        self.assertNotIn("\r", parsed.text)


if __name__ == "__main__":
    unittest.main()
