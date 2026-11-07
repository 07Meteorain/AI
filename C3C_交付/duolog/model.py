"""duolog.model —— 日志数据模型与解析（契约层）。

本模块是全项目唯一的数据契约（interface contract）。协作者 A（算法向）
与协作者 B（工程向）都只依赖这里的类型与函数签名，不互相依赖内部实现，
因此两人可以并行开发，最后由主持人集成。

日志文件格式
------------
每位协作者一份 Markdown 日志，条目以二级标题开头：

    ## E-001 | 1 | 类型:分工,技能:SEL-1
    正文第一行
    正文第二行

字段含义：

- ``eid``   事件编号，**跨日志共享**。两人对同一件事使用同一编号，
  就构成一次"双重确认"（double entry），这是本工具的信息强度来源。
- ``clock`` 该作者自己的**逻辑时钟**（正整数），同一作者日志内单调递增。
  注意：它不是墙上时间，两人之间不可直接比较大小——正是这一点让合并
  规则必须显式设计，而不能简单按时间戳取最新。
- ``tags``  逗号分隔的标签，形如 ``类型:分工`` / ``技能:SEL-1``。

``#`` 一级标题、``<!-- -->`` 注释与所有非条目文本都会被忽略，
这样日志里可以自由夹带说明文字而不会破坏解析。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

__all__ = [
    "Entry",
    "ParseIssue",
    "normalize_text",
    "parse_log",
    "eid_key",
    "canonical_json",
    "fingerprint_of",
    "TAG_TYPE",
    "TAG_SKILL",
    "TYPE_DECISION",
]

#: 标签命名空间
TAG_TYPE = "类型"
TAG_SKILL = "技能"

#: 被视为"决策"的类型标签值，冲突裁决规则 R1 会用到它
TYPE_DECISION = "决策"

_HEADER_RE = re.compile(
    r"^##\s+(?P<eid>[A-Za-z0-9][A-Za-z0-9_.-]*)\s*"
    r"\|\s*(?P<clock>\d+)\s*"
    r"\|\s*(?P<tags>[^|]*?)\s*$"
)


@dataclass(frozen=True)
class Entry:
    """一条日志条目。不可变，便于做纯函数式的合并。"""

    eid: str
    author: str
    clock: int
    tags: tuple[str, ...]
    text: str
    line: int

    @property
    def norm_text(self) -> str:
        """用于比较的规范化正文（空白差异不算冲突）。"""
        return normalize_text(self.text)

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def tag_value(self, namespace: str) -> str | None:
        """取 ``namespace:value`` 形式标签的 value，没有则返回 None。"""
        prefix = namespace + ":"
        for tag in self.tags:
            if tag.startswith(prefix):
                return tag[len(prefix):]
        return None

    def to_dict(self) -> dict:
        return {
            "eid": self.eid,
            "author": self.author,
            "clock": self.clock,
            "tags": list(self.tags),
            "text": self.text,
            "line": self.line,
        }


@dataclass(frozen=True)
class ParseIssue:
    """解析告警。``level`` 为 ``error`` 时，CLI 应以退出码 2 结束。"""

    level: str          # "error" | "warn"
    line: int
    message: str

    def __str__(self) -> str:  # pragma: no cover - 仅用于人读输出
        return f"[{self.level}] 第 {self.line} 行：{self.message}"


def normalize_text(text: str) -> str:
    """规范化正文：行尾空白去掉、首尾空行去掉、连续空行压成一行空行。

    合并判等只看规范化结果，因此"同一个事件"在两个日志里写法略有差异
    （多一个空格、少一个空行）不会被误判成冲突。
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    blank = False
    for ln in lines:
        if not ln:
            blank = True
            continue
        if blank and out:
            out.append("")
        blank = False
        out.append(ln)
    return "\n".join(out)


def _split_tags(raw: str, line_no: int, issues: list[ParseIssue]) -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for chunk in raw.split(","):
        tag = chunk.strip()
        if not tag:
            continue
        if ":" not in tag:
            issues.append(
                ParseIssue("warn", line_no, f"标签 {tag!r} 不是 命名空间:值 形式，已保留但不会被统计")
            )
        if tag in seen:
            issues.append(ParseIssue("warn", line_no, f"标签 {tag!r} 重复出现，已去重"))
            continue
        seen.add(tag)
        tags.append(tag)
    return tuple(tags)


def parse_log(text: str, author: str) -> tuple[list[Entry], list[ParseIssue]]:
    """把一份 Markdown 日志解析成条目列表。

    返回 ``(entries, issues)``。``entries`` 保持文件中出现的顺序；
    ``issues`` 中的 ``error`` 级问题表示该条目未被收录。
    """
    if not author or not author.strip():
        raise ValueError("author 不能为空")

    entries: list[Entry] = []
    issues: list[ParseIssue] = []

    current: dict | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal current, buf
        if current is None:
            buf = []
            return
        text_body = normalize_text("\n".join(buf))
        if not text_body:
            issues.append(
                ParseIssue("warn", current["line"], f"条目 {current['eid']} 正文为空")
            )
        entries.append(
            Entry(
                eid=current["eid"],
                author=author,
                clock=current["clock"],
                tags=current["tags"],
                text=text_body,
                line=current["line"],
            )
        )
        current = None
        buf = []

    for line_no, raw in enumerate(text.splitlines(), start=1):
        m = _HEADER_RE.match(raw)
        if m:
            flush()
            current = {
                "eid": m.group("eid"),
                "clock": int(m.group("clock")),
                "tags": _split_tags(m.group("tags"), line_no, issues),
                "line": line_no,
            }
            if current["clock"] < 1:
                issues.append(ParseIssue("error", line_no, "logic clock 必须 >= 1"))
            continue
        if raw.startswith("## "):
            # 形如二级标题但不合格式：几乎肯定是写错了的表头，必须报出来
            issues.append(
                ParseIssue("error", line_no, f"条目标题格式不合法：{raw.strip()!r}")
            )
            current = None
            buf = []
            continue
        if current is not None:
            buf.append(raw)
    flush()

    # 同一作者内 eid 重复：报 error，但两条都保留，交给合并阶段显式处理
    seen: dict[str, int] = {}
    for e in entries:
        if e.eid in seen:
            issues.append(
                ParseIssue("error", e.line, f"同一份日志中 eid {e.eid} 重复（首次出现在第 {seen[e.eid]} 行）")
            )
        else:
            seen[e.eid] = e.line

    # 逻辑时钟应当在同一作者内单调递增
    last_clock = -1
    for e in entries:
        if e.clock < last_clock:
            issues.append(
                ParseIssue("warn", e.line, f"条目 {e.eid} 的 clock={e.clock} 小于前一条的 {last_clock}，逻辑时钟应单调递增")
            )
        last_clock = max(last_clock, e.clock)

    return entries, issues


def eid_key(eid: str) -> tuple[str, int, int, str]:
    """事件编号的排序键：``E-2`` 排在 ``E-10`` 之前（数值感知）。

    返回定长 4 元组，保证不同类型可比较，排序结果与输入顺序无关。
    """
    m = re.fullmatch(r"([A-Za-z_.-]*)(\d+)", eid)
    if m:
        return (m.group(1), 0, int(m.group(2)), eid)
    return (eid, 1, 0, eid)


def canonical_json(obj: object) -> str:
    """规范化 JSON 序列化：键排序、不转义非 ASCII、无多余空白。

    这是"可复现指纹"的基础——同样的语义必须得到同样的字节。
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint_of(obj: object) -> str:
    """对任意可 JSON 化的对象取 sha256 指纹（前 16 位十六进制足够人读）。"""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def merge_sort_key(item: "MergedItemLike") -> tuple:
    """合并结果的稳定排序键，MergeResult 与渲染层共用。"""
    return (eid_key(item.eid), item.authors)


class MergedItemLike:
    """仅用于类型提示的最小协议（避免循环导入）。"""

    eid: str
    authors: tuple[str, ...]
