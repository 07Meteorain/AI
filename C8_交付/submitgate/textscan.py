"""Markdown 文本的轻量特征提取。

这些函数只回答「有没有」和「有多少」，不判断写得好不好 ——
判断好坏需要人，工具负责把需要人看的地方指出来。
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_READ_BYTES = 400_000

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
_TEMPLATE_RE = re.compile(r"(待填|待补|待更新|待真实|待确认|待定|TODO|TBD|xxx|占位)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

_NUM = r"[0-9]+|[一二三四五六七八九十两]+"
_ROUND_RES = (
    re.compile(rf"第\s*({_NUM})\s*[轮次步]"),
    re.compile(rf"轮次\s*[（(：:\s]*({_NUM})"),
    re.compile(r"round\s*([0-9]+)", re.IGNORECASE),
    re.compile(r"^\s*#{2,6}\s*R([0-9]+)\b", re.MULTILINE),
    re.compile(rf"({_NUM})\s*次\s*(?:prompt\s*)?迭代", re.IGNORECASE),
    re.compile(rf"迭代\s*({_NUM})\s*次", re.IGNORECASE),
)


def read_text(path: Path, max_bytes: int = MAX_READ_BYTES) -> str:
    """按 UTF-8 读文本；二进制文件返回空串而不是抛异常。"""

    try:
        raw = Path(path).read_bytes()[:max_bytes]
    except OSError:
        return ""
    if b"\x00" in raw:
        return ""
    return raw.decode("utf-8", errors="replace")


def strip_code_fences(text: str) -> str:
    """去掉代码块内容，避免把代码里的数字/标题算成正文特征。"""

    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


def headings(text: str) -> list[tuple[int, str]]:
    return [(len(m.group(1)), m.group(2).strip()) for m in _HEADING_RE.finditer(text)]


def find_heading(text: str, keywords: tuple[str, ...] | list[str]) -> str | None:
    lowered = [kw.casefold() for kw in keywords]
    for _, title in headings(text):
        title_fold = title.casefold()
        if any(kw in title_fold for kw in lowered):
            return title
    return None


def count_fences(text: str) -> int:
    """代码块数量（围栏行数的一半）。"""

    return len(_FENCE_RE.findall(text)) // 2


def count_distinct_numbers(text: str) -> int:
    return len(set(_NUMBER_RE.findall(strip_code_fences(text))))


def count_keyword_hits(text: str, keywords: tuple[str, ...] | list[str]) -> int:
    folded = text.casefold()
    return sum(1 for kw in keywords if kw.casefold() in folded)


def cn_to_int(token: str) -> int | None:
    """``三``/``十二``/``二十三``/``12`` → int；无法识别返回 None。"""

    token = token.strip()
    if token.isdigit():
        return int(token)
    if not token:
        return None
    if "十" not in token:
        if all(ch in _CN_DIGITS for ch in token):
            return _CN_DIGITS[token] if len(token) == 1 else None
        return None
    head, _, tail = token.partition("十")
    tens = _CN_DIGITS.get(head, 1) if head else 1
    ones = _CN_DIGITS.get(tail, 0) if tail else 0
    return tens * 10 + ones


def round_metrics(text: str) -> tuple[int, int]:
    """AI 日志的迭代证据：返回 ``(最大轮次, 不同轮次标记数)``。

    真实日志的写法比预想的散：``第 3 轮``、``第一轮``、``轮次（12 轮）``、
    ``## R3``、``三次 prompt 迭代`` 都有。只认阿拉伯数字会把「第一轮/第二轮/第三轮」
    判成 0 轮 —— 这是第一版最典型的误报。
    """

    numbers: set[int] = set()
    for pattern in _ROUND_RES:
        for token in pattern.findall(text):
            value = cn_to_int(token)
            if value is not None:
                numbers.add(value)
    if not numbers:
        return (0, 0)
    return (max(numbers), len(numbers))


def template_marks(text: str) -> int:
    """模板痕迹：``待填``/``TODO``/``占位`` 之类的出现次数。"""

    return len(_TEMPLATE_RE.findall(text))


def table_rows(text: str) -> int:
    return len(_TABLE_ROW_RE.findall(text))


def count_quote_blocks(text: str) -> int:
    """连续的 ``>`` 引用段数量。

    Prompt 原文不一定要放进代码块：真实日志里常见写法是
    ``1. > 帮我完成 C6 这个挑战……``。只数代码块会把这类日志判成「没有 prompt 原文」。
    """

    blocks = 0
    inside = False
    for line in text.splitlines():
        is_quote = line.lstrip().startswith(">")
        if is_quote and not inside:
            blocks += 1
        inside = is_quote
    return blocks


def char_count(text: str) -> int:
    return len(text)


def has_command_block(text: str) -> bool:
    """README 里是否有可复制执行的命令块。"""

    if count_fences(text) == 0:
        return False
    command_words = ("python", "python3", "node ", "npm ", "pnpm ", "pip ", "git ", "unittest", "pytest")
    for block in _iter_blocks(text):
        folded = block.casefold()
        if any(word in folded for word in command_words):
            return True
    return False


def _iter_blocks(text: str):
    lines = text.splitlines()
    block: list[str] = []
    inside = False
    for line in lines:
        if _FENCE_RE.match(line):
            if inside:
                yield "\n".join(block)
                block = []
            inside = not inside
            continue
        if inside:
            block.append(line)
    if inside and block:
        yield "\n".join(block)
