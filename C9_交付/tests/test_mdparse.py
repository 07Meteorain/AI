"""Markdown 解析测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recall.mdparse import (  # noqa: E402
    clean_inline,
    count_words,
    iter_markdown_files,
    join_lines,
    parse_note,
)


class TempNote:
    def __init__(self, text: str, name: str = "note.md"):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, name)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def __enter__(self) -> str:
        return self.path

    def __exit__(self, *exc) -> None:
        self.dir.cleanup()


def parse(text: str):
    with TempNote(text) as path:
        return parse_note(path)


class TestFrontMatter(unittest.TestCase):
    def test_meta_and_title(self):
        note = parse("---\ntitle: 测试标题\ncategory: 示例\n---\n\n# 正文标题\n\n正文。\n")
        self.assertEqual(note.meta["title"], "测试标题")
        self.assertEqual(note.meta["category"], "示例")
        self.assertEqual(note.title, "测试标题")

    def test_body_line_numbers_after_front_matter(self):
        note = parse("---\ntitle: T\n---\n\n# 第一节\n\n段落。\n")
        self.assertEqual(note.sections[0].line, 5)
        self.assertEqual(note.sections[0].blocks[0].line, 7)

    def test_unclosed_front_matter_is_body(self):
        note = parse("---\ntitle: T\n\n# 标题\n\n正文。\n")
        self.assertEqual(note.meta, {})
        self.assertEqual(note.sections[0].title, "标题")

    def test_title_falls_back_to_h1(self):
        note = parse("# 一级标题\n\n正文。\n")
        self.assertEqual(note.title, "一级标题")

    def test_title_falls_back_to_filename(self):
        with TempNote("正文没有标题。\n", name="我的笔记.md") as path:
            note = parse_note(path)
        self.assertEqual(note.title, "我的笔记")


class TestSections(unittest.TestCase):
    def test_levels_and_path(self):
        note = parse("# A\n\n## B\n\n文字\n\n### C\n\n文字\n\n## D\n\n文字\n")
        paths = [section.path for section in note.sections]
        self.assertIn(("A", "B"), paths)
        self.assertIn(("A", "B", "C"), paths)
        self.assertIn(("A", "D"), paths)

    def test_block_kinds(self):
        note = parse(
            "# T\n\n段落一行\n段落二行\n\n- 项目一\n- 项目二\n\n> 引用\n\n```py\nprint(1)\n```\n\n| a | b |\n| - | - |\n"
        )
        kinds = [block.kind for block in note.sections[0].blocks]
        self.assertEqual(kinds, ["para", "list", "quote", "code", "table"])

    def test_list_item_lines(self):
        note = parse("# T\n\n- **甲**：第一\n- **乙**：第二\n")
        block = note.sections[0].blocks[0]
        self.assertEqual(block.items, ["**甲**：第一", "**乙**：第二"])
        self.assertEqual(block.item_lines, [3, 4])

    def test_paragraph_joins_chinese_without_space(self):
        note = parse("# T\n\n这是第一行\n这是第二行。\n")
        self.assertEqual(note.sections[0].paragraphs[0], "这是第一行这是第二行。")

    def test_page_numbers_dropped(self):
        note = parse("# T\n\n正文第一句。\n\n12\n\n正文第二句。\n")
        joined = "".join(note.sections[0].paragraphs)
        self.assertNotIn("12", joined)

    def test_empty_sections_dropped(self):
        note = parse("# A\n\n## B\n\n## C\n\n文字\n")
        self.assertEqual([s.title for s in note.sections], ["C"])

    def test_no_heading_uses_document_title(self):
        note = parse("---\ntitle: 无标题结构\n---\n\n只有一段正文。\n")
        self.assertEqual(note.sections[0].title, "无标题结构")


class TestCleanInline(unittest.TestCase):
    def test_links_images_html(self):
        text = "看 [文档](https://x.com) 和 ![图](a.png) 以及 <b>粗体</b>"
        self.assertEqual(clean_inline(text), "看 文档 和 以及 粗体")

    def test_bold_and_code(self):
        self.assertEqual(clean_inline("**加粗** 与 `code`"), "加粗 与 code")
        self.assertEqual(clean_inline("*斜体* 与 **粗**"), "斜体 与 粗")

    def test_underscore_dunder(self):
        self.assertEqual(clean_inline("__init__ 方法"), "__init__ 方法")

    def test_escapes_and_whitespace(self):
        self.assertEqual(clean_inline("a\\*b\u3000\u3000c"), "a*b c")

    def test_empty(self):
        self.assertEqual(clean_inline(""), "")


class TestHelpers(unittest.TestCase):
    def test_join_lines(self):
        self.assertEqual(join_lines(["中文", "继续"]), "中文继续")
        self.assertEqual(join_lines(["hello", "world"]), "hello world")
        self.assertEqual(join_lines(["中文", "english"]), "中文english")

    def test_count_words(self):
        self.assertEqual(count_words("中文两个字"), 5)
        self.assertEqual(count_words("hello world"), 2)

    def test_iter_markdown_files_skips_nav(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a.md", "README.md", "index.md"):
                Path(tmp, name).write_text("# x\n", encoding="utf-8")
            hidden = Path(tmp, ".git")
            hidden.mkdir()
            (hidden / "b.md").write_text("# y\n", encoding="utf-8")
            found = [path.name for path in iter_markdown_files(tmp)]
        self.assertEqual(found, ["a.md"])

    def test_bom_is_stripped(self):
        with TempNote("\ufeff# 标题\n\n正文。\n") as path:
            note = parse_note(path)
        self.assertEqual(note.title, "标题")


if __name__ == "__main__":
    unittest.main()
