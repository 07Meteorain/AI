"""倒排索引 + BM25。用标准库实现，为什么不用 SQLite FTS5：

* FTS5 依赖编译期开关，``python.org`` 的 Windows 包通常带，但某些发行版和
  某些精简容器不带——一个"在别人机器上跑不起来"的记忆系统不算交付物。
* 记忆库的量级是几千条，纯 Python 的 BM25 在 1ms 量级，FTS5 省下来的时间
  还不够解释"为什么你这里要建虚表"的口水。

代价也写清楚：全量加载进内存，倒排不落盘。**十万条以上要换实现**，
这不是现在的问题，但写在 README 的边界里。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Doc:
    doc_id: str
    length: int = 0
    terms: dict[str, int] = field(default_factory=dict)


class InvertedIndex:
    """经典 BM25（k1=1.5, b=0.75），带增量增删。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: dict[str, Doc] = {}
        self._postings: dict[str, dict[str, int]] = {}
        self._df: dict[str, int] = {}
        self._total_len = 0

    # -- 增删 ----------------------------------------------------------
    def add(self, doc_id: str, tokens: Iterable[str]) -> None:
        self.remove(doc_id)
        tf: dict[str, int] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        doc = Doc(doc_id=doc_id, length=sum(tf.values()), terms=tf)
        self._docs[doc_id] = doc
        self._total_len += doc.length
        for term, count in tf.items():
            self._postings.setdefault(term, {})[doc_id] = count
            self._df[term] = self._df.get(term, 0) + 1

    def remove(self, doc_id: str) -> None:
        doc = self._docs.pop(doc_id, None)
        if doc is None:
            return
        self._total_len -= doc.length
        for term in doc.terms:
            bucket = self._postings.get(term)
            if bucket is not None:
                bucket.pop(doc_id, None)
                if not bucket:
                    del self._postings[term]
                    self._df.pop(term, None)
                else:
                    self._df[term] = len(bucket)

    def clear(self) -> None:
        self._docs.clear()
        self._postings.clear()
        self._df.clear()
        self._total_len = 0

    # -- 统计 ----------------------------------------------------------
    @property
    def size(self) -> int:
        return len(self._docs)

    @property
    def avgdl(self) -> float:
        return (self._total_len / len(self._docs)) if self._docs else 0.0

    def idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        n = max(1, len(self._docs))
        # BM25 的 +0.5 平滑；df=0 时给 0，避免给没出现过的词加分
        if df == 0:
            return 0.0
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    # -- 检索 ----------------------------------------------------------
    def search(self, query_tokens: Iterable[str], limit: int = 20) -> list[tuple[str, float, list[str]]]:
        """返回 ``[(doc_id, bm25, 命中的词), ...]``，按分数降序。"""

        q = [t for t in dict.fromkeys(query_tokens)]
        if not q or not self._docs:
            return []
        avgdl = self.avgdl or 1.0
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}

        for term in q:
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for doc_id, tf in postings.items():
                doc = self._docs[doc_id]
                denom = tf + self.k1 * (1 - self.b + self.b * (doc.length / avgdl))
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * (tf * (self.k1 + 1)) / (denom or 1.0)
                matched.setdefault(doc_id, []).append(term)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [(doc_id, round(score, 4), matched.get(doc_id, [])) for doc_id, score in ranked]

    def terms(self) -> set[str]:
        return set(self._postings)
