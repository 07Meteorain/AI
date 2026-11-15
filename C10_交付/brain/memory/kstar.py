"""KSTAR 记忆门面：写入、检索、更新、命中计数、Markdown 镜像。

对外只暴露一个类 ``KSTARMemory``，因为记忆系统的复杂度应该被关在里面——
循环层不该知道"倒排索引什么时候重建"，技能层也不该知道"知识层还有一份 md 镜像"。

三个设计决定，写在这里而不是留给读者猜：

1. **JSONL 是唯一真相，Markdown 是单向镜像**。人可以读、可以 diff 的那份在
   ``memory/knowledge/*.md``；但程序只认 JSONL。反向同步会引入两套真相，
   这是所有"笔记 + 数据库"双写系统翻车的起点。
2. **检索是排序不是布尔**。BM25 × 层先验 × 新近度 × 重要度，四项相乘而不是
   相加——因为"完全没命中"必须得 0 分，加法会让一条高重要度的无关记录胜出。
3. **命中要记账**。``hits`` 与 ``last_hit`` 是沉淀与淘汰的依据：
   三个月没人找回来的 S 记录，就该被压缩成周报。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..config import Config
from ..util import (
    append_jsonl,
    atomic_write_text,
    days_between,
    iso,
    new_id,
    read_json,
    slugify,
    tokenize,
    write_json,
)
from .index import InvertedIndex
from .store import ID_PREFIX, LAYERS, LAYER_NAMES, JsonlStore, Record

# 层先验：同一段文字，作为"知识"比作为"某次会话"更值得被找回
LAYER_PRIOR = {"K": 1.25, "T": 1.15, "AR": 1.0, "S": 0.95}


@dataclass
class Hit:
    record: Record
    score: float
    matched: list[str]
    reason: str = ""

    @property
    def why(self) -> str:
        return self.reason or ("命中：" + "、".join(self.matched[:6]) if self.matched else "")

    def brief(self, limit: int = 88) -> str:
        return f"[{self.record.layer}] {self.record.title or self.record.summary(limit)}"


class KSTARMemory:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.config.ensure_dirs()
        self.stores: dict[str, JsonlStore] = {
            layer: JsonlStore(self.config.db_dir / f"{layer.lower()}.jsonl", layer).load()
            for layer in LAYERS
        }
        self._index = InvertedIndex()
        self._indexed: set[str] = set()
        self.aliases: dict[str, list[str]] = read_json(self.config.aliases_path, {"map": {}}) or {"map": {}}
        self._rebuild_index()

    # ------------------------------------------------------------------
    # 索引
    # ------------------------------------------------------------------
    def _rebuild_index(self) -> None:
        self._index.clear()
        self._indexed.clear()
        for store in self.stores.values():
            for rec in store.all():
                self._index.add(rec.id, tokenize(rec.keyword_haystack()))
                self._indexed.add(rec.id)

    def reindex(self) -> int:
        self._rebuild_index()
        return self._index.size

    def known_terms(self) -> set[str]:
        """索引里出现过的词元。进化层用它判断"这个词系统压根没见过"。"""
        return self._index.terms()

    def _ensure_indexed(self, rec: Record) -> None:
        if rec.id in self._indexed:
            self._index.remove(rec.id)
        self._index.add(rec.id, tokenize(rec.keyword_haystack()))
        self._indexed.add(rec.id)

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------
    def write(
        self,
        layer: str,
        text: str,
        *,
        title: str = "",
        tags: Iterable[str] | None = None,
        source: str = "human",
        importance: float = 0.5,
        status: str = "",
        meta: dict[str, Any] | None = None,
        dedupe: bool = False,
    ) -> Record:
        layer = layer.upper()
        if layer not in LAYERS:
            raise ValueError(f"未知记忆层：{layer}")

        text = (text or "").strip()
        title = (title or "").strip() or self._derive_title(text)

        if dedupe:
            existing = self.find_duplicate(layer, text)
            if existing is not None:
                existing.hits += 0  # 不算一次"被找回"
                existing.updated = iso()
                self.stores[layer].put(existing)
                self.stores[layer].flush()
                return existing

        ts = iso()
        rec = Record(
            id=new_id(ID_PREFIX[layer], seed=text[:32]),
            layer=layer,
            title=title,
            text=text,
            created=ts,
            updated=ts,
            tags=[str(t) for t in (tags or [])],
            source=source,
            importance=importance,
            status=status,
            meta=meta or {},
        )
        self.stores[layer].put(rec)
        self.stores[layer].flush()
        self._ensure_indexed(rec)
        if layer == "K":
            self._mirror_knowledge(rec)
        return rec

    @staticmethod
    def _derive_title(text: str) -> str:
        first = " ".join((text or "").split())
        for sep in ("。", "！", "？", ". ", "\n"):
            if sep in first:
                first = first.split(sep)[0]
                break
        return (first[:28] + "…") if len(first) > 28 else (first or "（无标题）")

    def find_duplicate(self, layer: str, text: str) -> Record | None:
        """极简去重：前 60 字完全相同即视为同一条。

        不做语义去重——那需要向量，而向量需要依赖。宁可保守（漏判重复）
        也不要激进（把两条不同的经验合并成一条错的）。
        """
        key = " ".join((text or "").split())[:60]
        if not key:
            return None
        for rec in self.stores[layer.upper()].all():
            if " ".join(rec.text.split())[:60] == key:
                return rec
        return None

    def _mirror_knowledge(self, rec: Record) -> None:
        path = self.config.knowledge_dir / f"{rec.id}.md"
        front = [
            "---",
            f"id: {rec.id}",
            f"title: {rec.title}",
            f"created: {rec.created}",
            f"tags: {', '.join(rec.tags) if rec.tags else '-'}",
            f"importance: {rec.importance}",
            f"source: {rec.source}",
            "---",
            "",
            f"# {rec.title}",
            "",
            rec.text,
            "",
        ]
        atomic_write_text(path, "\n".join(front))
        self._write_knowledge_index()

    def _write_knowledge_index(self) -> None:
        recs = sorted(self.stores["K"].all(), key=lambda r: r.created, reverse=True)
        lines = [
            "# 知识层索引（自动生成，请勿手改）",
            "",
            "> 由 `brain.memory.kstar` 在每次写入 K 记录时重写。",
            "> 逐条正文在同目录 `<id>.md`；本文件只是给人看的目录。",
            "",
            f"共 {len(recs)} 条。",
            "",
            "| ID | 标题 | 标签 | 重要度 | 创建 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for rec in recs:
            tags = "、".join(rec.tags) if rec.tags else "-"
            lines.append(f"| `{rec.id}` | {rec.title} | {tags} | {rec.importance:.1f} | {rec.created[:10]} |")
        atomic_write_text(self.config.knowledge_dir / "INDEX.md", "\n".join(lines) + "\n")

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def get(self, record_id: str) -> Record | None:
        for store in self.stores.values():
            rec = store.get(record_id)
            if rec is not None:
                return rec
        return None

    def all(self, layer: str | None = None) -> list[Record]:
        if layer:
            return self.stores[layer.upper()].all()
        out: list[Record] = []
        for name in LAYERS:
            out.extend(self.stores[name].all())
        return out

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        layers: Iterable[str] | None = None,
        min_score: float = 0.0,
        touch: bool = True,
        include_echo: bool = False,
    ) -> list[Hit]:
        """BM25 检索 + 同义词扩展 + 四因子重排。返回带"为什么"的 Hit 列表。

        ``include_echo=False`` 时跳过"问句回声"记录（``meta.echo``）。
        理由见 ``docs/KSTAR记忆规范.md``：一句问话在库里躺两天，不会变成答案，
        但它会让同一句话第二次提问时"命中"自己，制造虚假的成功率。
        """

        query = (query or "").strip()
        if not query:
            return []

        tokens = tokenize(query)
        if not tokens:
            return []

        want = {l.upper() for l in layers} if layers else set(LAYERS)
        raw: dict[str, tuple[float, list[str]]] = {}

        def _eligible(rec: Record) -> bool:
            if rec.layer not in want:
                return False
            return include_echo or not rec.meta.get("echo")

        for doc_id, score, matched in self._index.search(tokens, limit=max(50, top_k * 8)):
            rec = self.get(doc_id)
            if rec is None or not _eligible(rec):
                continue
            raw[doc_id] = (score, matched)

        # 同义词扩展：权重 0.5，不覆盖原查询的分数，只做加法
        for alias_query in self._alias_queries(query):
            alias_tokens = tokenize(alias_query)
            for doc_id, score, matched in self._index.search(alias_tokens, limit=50):
                rec = self.get(doc_id)
                if rec is None or not _eligible(rec):
                    continue
                prev = raw.get(doc_id)
                if prev is None:
                    raw[doc_id] = (score * 0.5, matched)
                else:
                    merged = list(dict.fromkeys(prev[1] + matched))
                    raw[doc_id] = (prev[0] + score * 0.5, merged)

        hits: list[Hit] = []
        for doc_id, (base, matched) in raw.items():
            rec = self.get(doc_id)
            if rec is None:
                continue
            score = self._rerank(rec, base)
            if score < min_score:
                continue
            hits.append(Hit(record=rec, score=round(score, 4), matched=matched))

        hits.sort(key=lambda h: (h.score, h.record.importance), reverse=True)
        hits = hits[:top_k]

        if touch and hits:
            self.record_hit([h.record.id for h in hits])
        return hits

    def _rerank(self, rec: Record, base: float) -> float:
        prior = LAYER_PRIOR.get(rec.layer, 1.0)
        important = 0.85 + 0.3 * rec.importance
        if rec.layer == "K":
            fresh = 1.0  # 知识不衰减：牛顿力学不会因为放了三年就不对
        else:
            age = days_between(rec.created)
            fresh = max(0.55, math.exp(-math.log(2) * age / max(1.0, self.config.half_life_days)))
        # 被反复找回过的记录略微加权：它是"活的"
        used = 1.0 + min(0.25, 0.03 * rec.hits)
        return base * prior * important * fresh * used

    def _alias_queries(self, query: str) -> list[str]:
        """查同义词表：把命中别名键的那部分换成它的目标词，产生一条附加查询。"""

        mapping = (self.aliases or {}).get("map", {}) or {}
        out: list[str] = []
        for key, targets in mapping.items():
            if key and key in query:
                joined = " ".join(str(t) for t in targets)
                out.append(joined)
        return out

    def add_alias(self, key: str, targets: Iterable[str], *, source: str = "evolve") -> bool:
        key = (key or "").strip()
        targets = [str(t).strip() for t in targets if str(t).strip()]
        if not key or not targets:
            return False
        mapping = self.aliases.setdefault("map", {})
        current = [t for t in mapping.get(key, []) if t not in targets]
        merged = current + targets
        if mapping.get(key) == merged:
            return False
        mapping[key] = merged
        write_json(self.config.aliases_path, self.aliases)
        append_jsonl(
            self.config.evolution_log,
            {"ts": iso(), "kind": "alias", "key": key, "targets": targets, "source": source},
        )
        return True

    # ------------------------------------------------------------------
    # 更新 / 命中
    # ------------------------------------------------------------------
    def update(self, record_id: str, **fields: Any) -> Record | None:
        rec = self.get(record_id)
        if rec is None:
            return None
        for key, value in fields.items():
            if hasattr(rec, key):
                setattr(rec, key, value)
        rec.updated = iso()
        rec.__post_init__()  # 重新规整 layer/tags/importance
        self.stores[rec.layer].put(rec)
        self.stores[rec.layer].flush()
        self._ensure_indexed(rec)
        if rec.layer == "K":
            self._mirror_knowledge(rec)
        return rec

    def record_hit(self, ids: Iterable[str]) -> None:
        touched: set[str] = set()
        ts = iso()
        for rid in ids:
            rec = self.get(rid)
            if rec is None or rid in touched:
                continue
            rec.hits += 1
            rec.last_hit = ts
            touched.add(rid)
            self.stores[rec.layer].put(rec)
        for store in self.stores.values():
            store.flush()

    # ------------------------------------------------------------------
    # 观测
    # ------------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        per = {layer: self.stores[layer].stats() for layer in LAYERS}
        per["total"] = {
            "count": sum(per[l]["count"] for l in LAYERS),
            "bytes": sum(per[l]["bytes"] for l in LAYERS),
            "total_hits": sum(per[l]["total_hits"] for l in LAYERS),
        }
        return {
            "layers": per,
            "names": LAYER_NAMES,
            "index_size": self._index.size,
            "vocabulary": len(self._index.terms()),
            "aliases": len((self.aliases or {}).get("map", {}) or {}),
            "home": str(self.config.home),
        }

    def describe(self) -> str:
        s = self.stats()["layers"]
        return "记忆：" + "  ".join(f"{l}={s[l]['count']}" for l in LAYERS) + f"  索引={self._index.size} 条"
