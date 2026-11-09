import unittest

from promptlint.engine import lint_text
from promptlint.rules.safety import mask_email, mask_secret


def findings(text):
    return lint_text(text)


class SecretTests(unittest.TestCase):
    SAMPLES = [
        "sk-" + "a" * 24,
        "ghp_" + "b" * 30,
        "AKIA" + "C" * 16,
        "xoxb-" + "1" * 12,
        "-----BEGIN RSA PRIVATE KEY-----",
    ]

    def test_known_secret_shapes(self):
        for sample in self.SAMPLES:
            with self.subTest(sample=sample[:12]):
                found = [item for item in findings("key: %s\n" % sample) if item.rule_id == "PL005"]
                self.assertEqual(len(found), 1)

    def test_generic_credential(self):
        found = [item for item in findings("password: 0123456789abcdef\n") if item.rule_id == "PL005"]
        self.assertEqual(len(found), 1)

    def test_secret_is_masked_in_report(self):
        secret = "sk-" + "a" * 24
        found = [item for item in findings(secret + "\n") if item.rule_id == "PL005"][0]
        self.assertNotIn(secret, found.message)
        self.assertIn("...", found.message)

    def test_secret_inside_fence_is_still_found(self):
        found = findings("```\nsk-" + "a" * 24 + "\n```\n")
        self.assertTrue(any(item.rule_id == "PL005" for item in found))


class PiiTests(unittest.TestCase):
    def test_email_mobile_and_national_id(self):
        text = "Mail alice@example.com, call 13800138000, id 110101199003071234.\n"
        found = [item for item in findings(text) if item.rule_id == "PL006"]
        self.assertGreaterEqual(len(found), 3)
        rendered = " ".join(item.message for item in found)
        self.assertNotIn("alice@example.com", rendered)
        self.assertNotIn("13800138000", rendered)

    def test_masks(self):
        self.assertEqual(mask_email("alice@example.com"), "a***@example.com")
        self.assertEqual(mask_secret("short"), "<redacted:5 chars>")
        self.assertEqual(mask_secret("0123456789a"), "<redacted:11 chars>")
        self.assertEqual(mask_secret("abcdefghijkl"), "abcd...ijkl")


class BoundaryTests(unittest.TestCase):
    def test_unwrapped_input_is_flagged(self):
        found = findings("Summarise this: {{user_message}}\n")
        self.assertTrue(any(item.rule_id == "PL009" for item in found))

    def test_wrapped_input_is_clean(self):
        found = findings("<user_message>\n{{user_message}}\n</user_message>\n")
        self.assertFalse(any(item.rule_id == "PL009" for item in found))

    def test_wrapped_input_with_attributes_is_clean(self):
        found = findings('<context source="retrieval">\n{{document}}\n</context>\n')
        self.assertFalse(any(item.rule_id == "PL009" for item in found))

    def test_non_input_placeholder_is_not_checked(self):
        found = findings("Write about {{topic}}\n")
        self.assertFalse(any(item.rule_id == "PL009" for item in found))

    def test_placeholder_inside_fence_is_not_checked(self):
        found = findings("```\n{{user_message}}\n```\n")
        self.assertFalse(any(item.rule_id == "PL009" for item in found))

    def test_crlf_offsets_are_normalised(self):
        text = "".join("line %d\r\n" % index for index in range(10))
        text += "{{user_message}}\r\n"
        found = findings(text)
        self.assertTrue(any(item.rule_id == "PL009" for item in found))


class InvisibleTests(unittest.TestCase):
    def test_zero_width_space(self):
        found = [item for item in findings("hello\u200b\n") if item.rule_id == "PL011"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].column, 6)

    def test_bom(self):
        found = [item for item in findings("\ufeffHello\n") if item.rule_id == "PL011"]
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
