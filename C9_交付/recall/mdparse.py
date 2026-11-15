"""Markdown 解析：把一篇笔记拆成「章节 → 区块 → 句子」三层。

只解析抽取卡片真正需要的东西：标题、段落、列表、引用、代码块、表格。
代码块与表格会被识别但**不用于出题**——从代码里自动出题很容易产出一堆
「这行代码是干嘛的」的伪问题，Recall 宁可少出，也不出噪音。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .model import Block, Note, Section

_BOM = "\ufeff"
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LIST_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,3}[.)])\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_RE = re.compile(r"^\s*\|")
_HR_RE = re.compile(r"^\s*(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_PAGE_NO_RE = re.compile(r"^\s*(?:[-–—]?\s*\d{1,3}\s*[-–—]?|第\s*\d+\s*页)\s*$")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_RE = re.compile(r"<[^>]{1,200}>")
_EMPH_RE = re.compile(r"(?<!\w)\*([^*\n]+?)\*(?!\w)")
_MULTI_WS_RE = re.compile(r"[ \t\u00a0\u3000]+")

_CJK_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0x3040, 0x30FF),
    (0xAC00, 0xD7AF),
)


def is_cjk(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def clean_inline(text: str) -> str:
    """去掉行内 Markdown / HTML，得到适合展示与判定的纯文本。"""
    if not text:
        return ""
    text = text.replace(_BOM, "").replace("\u200b", "").replace("\ufeff", "")
    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _HTML_RE.sub("", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = _EMPH_RE.sub(r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = text.replace("~~", "")
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>])", r"\1", text)
    text = _MULTI_WS_RE.sub(" ", text)
    return text.strip()


def join_lines(parts: Iterable[str]) -> str:
    """按中英文习惯拼接换行：中文与中文之间不加空格。"""
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
        elif is_cjk(out[-1]) or is_cjk(part[0]):
            out += part
        else:
            out += " " + part
    return out


def count_words(text: str) -> int:
    """字数：CJK 字符逐个计，拉丁词按词计。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    latin = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text))
    return cjk + latin


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def _parse_front_matter(lines: List[str]) -> Tuple[Dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = -1
    for i in range(1, min(len(lines), 120)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end < 0:
        return {}, 0
    meta: Dict[str, str] = {}
    for raw in lines[1:end]:
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lower()
        if key:
            meta[key] = value.strip().strip("\"'")
    return meta, end + 1


def _is_block_start(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    return bool(
        _HEADING_RE.match(line)
        or _FENCE_RE.match(line)
        or _LIST_RE.match(line)
        or _QUOTE_RE.match(line)
        or _TABLE_RE.match(line)
        or _HR_RE.match(line)
    )


def _parse_blocks(lines: List[str], first_line: int) -> List[Block]:
    blocks: List[Block] = []
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line_no = first_line + i
        if not raw.strip():
            i += 1
            continue

        fence = _FENCE_RE.match(raw)
        if fence:
            marker = fence.group(1)
            j = i + 1
            chunk: List[str] = []
            while j < n and not lines[j].strip().startswith(marker):
                chunk.append(lines[j])
                j += 1
            blocks.append(Block("code", "\n".join(chunk), line_no))
            i = j + 1
            continue

        heading = _HEADING_RE.match(raw)
        if heading:
            title = clean_inline(heading.group(2))
            if title:
                blocks.append(Block("heading", title, line_no, level=len(heading.group(1))))
            i += 1
            continue

        if _HR_RE.match(raw):
            blocks.append(Block("hr", "", line_no))
            i += 1
            continue

        if _LIST_RE.match(raw):
            items: List[str] = []
            item_lines: List[int] = []
            j = i
            while j < n:
                lm = _LIST_RE.match(lines[j])
                if lm:
                    items.append(lm.group(1).strip())
                    item_lines.append(first_line + j)
                    j += 1
                    continue
                if (
                    items
                    and lines[j].strip()
                    and (lines[j].startswith("  ") or lines[j].startswith("\t"))
                    and not _is_block_start(lines[j])
                ):
                    items[-1] = join_lines([items[-1], lines[j]])
                    j += 1
                    continue
                break
            blocks.append(Block("list", "\n".join(items), line_no, items=items, item_lines=item_lines))
            i = j
            continue

        if _QUOTE_RE.match(raw):
            chunk = []
            j = i
            while j < n:
                qm = _QUOTE_RE.match(lines[j])
                if not qm:
                    break
                chunk.append(qm.group(1))
                j += 1
            text = join_lines(chunk)
            if text:
                blocks.append(Block("quote", text, line_no))
            i = j
            continue

        if _TABLE_RE.match(raw):
            chunk = []
            j = i
            while j < n and _TABLE_RE.match(lines[j]):
                chunk.append(lines[j].strip())
                j += 1
            blocks.append(Block("table", "\n".join(chunk), line_no))
            i = j
            continue

        # 普通段落：吃到空行或下一个区块起点
        chunk = []
        j = i
        while j < n and lines[j].strip() and not (j > i and _is_block_start(lines[j])):
            if _PAGE_NO_RE.match(lines[j]):
                j += 1
                continue
            chunk.append(lines[j])
            j += 1
        text = join_lines(chunk)
        if text:
            blocks.append(Block("para", text, line_no))
        i = j

    return blocks


def _assemble_sections(blocks: List[Block], fallback_title: str) -> List[Section]:
    sections: List[Section] = []
    stack: List[Tuple[int, str]] = []
    current: Optional[Section] = None
    saw_heading = False

    def flush() -> None:
        nonlocal current
        if current is not None and current.blocks:
            sections.append(current)
        current = None

    for block in blocks:
        if block.kind == "heading":
            saw_heading = True
            flush()
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            stack.append((block.level, block.text))
            current = Section(
                title=block.text,
                level=block.level,
                line=block.line,
                path=tuple(title for _, title in stack),
            )
        else:
            if current is None:
                if saw_heading or block.kind != "para":
                    continue
                current = Section(
                    title=fallback_title or "正文",
                    level=1,
                    line=block.line,
                    path=(fallback_title or "正文",),
                )
            current.blocks.append(block)

    flush()
    return sections


def parse_note(path: str, source: Optional[str] = None, root: Optional[str] = None) -> Note:
    """解析一个文件。source 为展示用相对路径（POSIX 风格）。"""
    text = read_text(path)
    lines = text.splitlines()
    meta, offset = _parse_front_matter(lines)
    body = lines[offset:]
    blocks = _parse_blocks(body, offset + 1)

    if source is None:
        if root:
            source = os.path.relpath(path, root)
        else:
            source = os.path.basename(path)
    source = source.replace("\\", "/")

    title = meta.get("title", "").strip()
    if not title:
        for block in blocks:
            if block.kind == "heading" and block.level == 1:
                title = block.text
                break
    if not title:
        title = Path(path).stem

    sections = _assemble_sections(blocks, title)
    return Note(
        path=path,
        source=source,
        title=clean_inline(title),
        meta=meta,
        sections=sections,
        line_count=len(lines),
    )


def iter_markdown_files(root: str) -> List[Path]:
    """按路径排序返回 Markdown 文件；跳过隐藏目录、README 与导航 index。"""
    root_path = Path(root)
    if root_path.is_file():
        return [root_path]
    files: List[Path] = []
    for path in sorted(root_path.rglob("*.md")):
        parts = path.relative_to(root_path).parts
        if any(part.startswith(".") for part in parts):
            continue
        if path.name.lower() in ("readme.md", "index.md"):
            continue
        files.append(path)
    return files
