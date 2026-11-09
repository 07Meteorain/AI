import os
import tempfile
import unittest
from pathlib import Path

from promptlint.config import Config
from promptlint.engine import lint_files, lint_text


class EngineTests(unittest.TestCase):
    def test_clean_prompt(self):
        self.assertEqual(lint_text("Return JSON.\n"), [])

    def test_severity_override(self):
        text = "{{user_message}}\n"
        found = lint_text(text, config=Config(rules={"PL009": "info"}))
        self.assertEqual([item.severity for item in found], ["info"])

    def test_rule_can_be_disabled(self):
        found = lint_text("{{user_message}}\n", config=Config(rules={"PL009": "off"}))
        self.assertEqual(found, [])

    def test_findings_are_sorted_by_position(self):
        text = "line one\nsk-" + "a" * 24 + "\n{{user_message}}\n"
        found = lint_text(text)
        positions = [(item.line, item.column) for item in found]
        self.assertEqual(positions, sorted(positions))


class FileDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_extensions_and_excluded_directories(self):
        self.write("prompts/a.prompt", "Return JSON.\n")
        self.write("prompts/notes.md", "Return JSON.\n")
        self.write("scripts/tool.py", "print('hi')\n")
        self.write(".git/hook.prompt", "{{user_message}}\n")
        results = lint_files([str(self.root)], Config())
        paths = [source.rel_path for source, _ in results]
        self.assertEqual(len(paths), 2)
        self.assertTrue(any(path.endswith("a.prompt") for path in paths))
        self.assertTrue(any(path.endswith("notes.md") for path in paths))

    def test_explicit_file_any_extension(self):
        path = self.write("tool.ps1", "{{user_message}}\n")
        results = lint_files([str(path)], Config())
        self.assertEqual(len(results), 1)
        self.assertTrue(any(item.rule_id == "PL009" for item in results[0][1]))

    def test_glob_exclude(self):
        self.write("vendor/skip.prompt", "{{user_message}}\n")
        self.write("keep.prompt", "Return JSON.\n")
        results = lint_files([str(self.root)], Config(exclude=["vendor/**"]))
        paths = [source.rel_path for source, _ in results]
        self.assertTrue(all("vendor" not in path for path in paths))


if __name__ == "__main__":
    unittest.main()
