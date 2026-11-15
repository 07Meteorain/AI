"""数据模型：卡片、构建结果。

卡片 id 由「来源路径 + 类型 + 归一化问题」派生，因此**重建不会丢复习记录**；
反过来，问题文本一改，id 就变，旧记录会留在库里成为孤儿——这是有意的取舍：
一张问题被改写过的卡，本来就不应该继承旧卡的记忆强度。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s，。！？、；：,.!?;:\"'“”‘’（）()\[\]【】《》<>—\-…·]+")


def normalize(text: str) -> str:
    """归一化：小写、去标点、压空白。用于去重与 id。"""
    text = (text or "").strip().lower()
    text = _PUNCT_RE.sub("", text)
    return _WS_RE.sub("", text)


def make_id(source: str, kind: str, prompt: str) -> str:
    raw = "{}\x1f{}\x1f{}".format(source.replace("\\", "/"), kind, normalize(prompt))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Card:
    id: str
    kind: str
    prompt: str
    answer: str
    source: str
    heading: str
    line: int
    confidence: float
    tags: Tuple[str, ...] = ()
    status: str = "approved"
    created: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "prompt": self.prompt,
            "answer": self.answer,
            "source": self.source,
            "heading": self.heading,
            "line": self.line,
            "confidence": round(self.confidence, 3),
            "tags": list(self.tags),
            "status": self.status,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Card":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            prompt=str(data["prompt"]),
            answer=str(data["answer"]),
            source=str(data.get("source", "")),
            heading=str(data.get("heading", "")),
            line=int(data.get("line", 0) or 0),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            tags=tuple(data.get("tags") or ()),
            status=str(data.get("status", "approved")),
            created=str(data.get("created", "")),
        )


@dataclass
class Section:
    """一个标题下的内容。"""

    title: str
    level: int
    line: int
    path: Tuple[str, ...] = ()
    blocks: List["Block"] = field(default_factory=list)

    @property
    def paragraphs(self) -> List[str]:
        return [b.text for b in self.blocks if b.kind == "para"]

    @property
    def list_items(self) -> List[str]:
        items: List[str] = []
        for block in self.blocks:
            if block.kind == "list":
                items.extend(block.items)
        return items


@dataclass
class Block:
    kind: str  # heading | para | list | quote | table | code | hr
    text: str
    line: int
    level: int = 0
    items: List[str] = field(default_factory=list)
    item_lines: List[int] = field(default_factory=list)


@dataclass
class Note:
    path: str
    source: str
    title: str
    meta: Dict[str, str]
    sections: List[Section]
    line_count: int = 0

    @property
    def paragraphs(self) -> List[str]:
        out: List[str] = []
        for section in self.sections:
            out.extend(section.paragraphs)
        return out


@dataclass
class BuildStats:
    files: int = 0
    sections: int = 0
    paragraphs: int = 0
    candidates: int = 0
    accepted: int = 0
    rejected: Dict[str, int] = field(default_factory=dict)
    by_kind: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)
    words: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files": self.files,
            "sections": self.sections,
            "paragraphs": self.paragraphs,
            "candidates": self.candidates,
            "accepted": self.accepted,
            "rejected": dict(sorted(self.rejected.items())),
            "by_kind": dict(sorted(self.by_kind.items())),
            "by_source": dict(sorted(self.by_source.items())),
            "words": self.words,
        }


@dataclass
class BuildResult:
    cards: List[Card]
    stats: BuildStats
    notes: List[Note] = field(default_factory=list)
    generated: str = ""
