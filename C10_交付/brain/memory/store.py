"""记录模型与 JSONL 存储。

存储层只做三件事：**读得回来、写得进去、改得安全**。
检索是 ``index.py`` 的事，沉淀是 ``promote.py`` 的事——不混在一起，
因为三者出故障的方式完全不同（存储坏了丢数据，检索坏了找不到，沉淀坏了会污染知识库）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..util import append_jsonl, atomic_write_text, iso, new_id, parse_iso, read_jsonl

LAYERS = ("K", "S", "T", "AR")

LAYER_NAMES = {
    "K": "Knowledge 知识",
    "S": "Situation 情境",
    "T": "Task 任务",
    "AR": "Action-Reflection 行动与反思",
}

ID_PREFIX = {"K": "k", "S": "s", "T": "t", "AR": "ar"}


@dataclass
class Record:
    """一条记忆。字段不多，但每个都有明确用途。

    * ``title`` / ``text`` 进索引；``tags`` 既进索引也用于过滤。
    * ``importance`` 参与排序（0~1）；``hits`` 是"被找回过的次数"，
      用来在沉淀时区分"写在库里"和"真的被用上"。
    * ``source`` 是溯源字段：谁写的（run id / skill / human）。没有它就谈不上可追溯。
    """

    id: str
    layer: str
    title: str
    text: str
    created: str
    updated: str
    tags: list[str] = field(default_factory=list)
    source: str = "human"
    importance: float = 0.5
    status: str = ""
    hits: int = 0
    last_hit: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.layer = self.layer.upper()
        if self.layer not in LAYERS:
            raise ValueError(f"未知记忆层：{self.layer}")
        self.tags = [str(t) for t in (self.tags or [])]
        self.importance = float(min(1.0, max(0.0, self.importance)))

    # -- 序列化 --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload.setdefault("id", new_id(ID_PREFIX.get(str(data.get("layer", "K")).upper(), "k")))
        payload.setdefault("layer", "K")
        payload.setdefault("title", "")
        payload.setdefault("text", "")
        payload.setdefault("created", payload.get("updated") or iso())
        payload.setdefault("updated", payload["created"])
        return cls(**payload)  # type: ignore[arg-type]

    # -- 便捷 ----------------------------------------------------------
    @property
    def age_days(self) -> float:
        return max(0.0, (parse_iso(iso()) - parse_iso(self.created)).total_seconds() / 86400.0)

    @property
    def layer_name(self) -> str:
        return LAYER_NAMES.get(self.layer, self.layer)

    def summary(self, limit: int = 90) -> str:
        text = " ".join((self.text or "").split())
        return text[:limit] + ("…" if len(text) > limit else "")

    def keyword_haystack(self) -> str:
        return " ".join([self.title, self.text, " ".join(self.tags)])


class JsonlStore:
    """一层一个 append-only 文件；更新时整体重写（记忆量级远小于重写成本）。"""

    def __init__(self, path: Path, layer: str):
        self.path = Path(path)
        self.layer = layer
        self._records: dict[str, Record] = {}
        self._dirty = False
        self._loaded = False

    # -- 生命周期 ------------------------------------------------------
    def load(self) -> "JsonlStore":
        if self._loaded:
            return self
        self._records = {}
        for raw in read_jsonl(self.path):
            try:
                rec = Record.from_dict(raw)
            except (ValueError, TypeError):
                continue
            self._records[rec.id] = rec
        self._loaded = True
        return self

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    # -- 读 ------------------------------------------------------------
    def all(self) -> list[Record]:
        self._ensure()
        return list(self._records.values())

    def get(self, record_id: str) -> Record | None:
        self._ensure()
        return self._records.get(record_id)

    def __len__(self) -> int:
        self._ensure()
        return len(self._records)

    def __iter__(self) -> Iterator[Record]:
        return iter(self.all())

    # -- 写 ------------------------------------------------------------
    def put(self, rec: Record) -> Record:
        self._ensure()
        if rec.id in self._records:
            rec.updated = iso()
            self._records[rec.id] = rec
            self._dirty = True
        else:
            self._records[rec.id] = rec
            append_jsonl(self.path, rec.to_dict())
        return rec

    def flush(self) -> None:
        """只在有更新（非追加）时重写整个文件。"""
        self._ensure()
        if not self._dirty:
            return
        lines = [json.dumps(r.to_dict(), ensure_ascii=False) for r in self._records.values()]
        atomic_write_text(self.path, "\n".join(lines) + ("\n" if lines else ""))
        self._dirty = False

    def remove(self, record_id: str) -> bool:
        self._ensure()
        if record_id not in self._records:
            return False
        del self._records[record_id]
        self._dirty = True
        self.flush()
        return True

    # -- 观测 ----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        recs = self.all()
        return {
            "layer": self.layer,
            "count": len(recs),
            "bytes": self.path.stat().st_size if self.path.exists() else 0,
            "avg_importance": round(sum(r.importance for r in recs) / len(recs), 3) if recs else 0.0,
            "total_hits": sum(r.hits for r in recs),
        }
