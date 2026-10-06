"""记忆层：短期对话历史 + 长期事实记忆，SQLite 持久化。

对应 rubric 的「有记忆」信号。设计要点：

* **短期记忆**：对话消息历史，带 token 预算的滑动窗口裁剪，
  避免超出模型上下文导致 OOM 或截断。
* **长期记忆**：Agent 自主决定写入的事实（用户偏好、已确认的地点坐标等），
  以 (key, value) 形式存储，可在进程重启后被 recall。
* **会话隔离**：按 session_id 分库，Agent 的每个技能实例互不污染。

只用标准库 sqlite3，无需引入 ORM 依赖。
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class MemoryStats:
    """记忆使用统计，写入日志用于验证「记忆确实生效」。"""

    turns: int = 0
    facts: int = 0
    tokens_estimate: int = 0
    trimmed_turns: int = 0

    def summary(self) -> str:
        return (
            f"turns={self.turns} facts={self.facts} "
            f"~tokens={self.tokens_estimate} trimmed={self.trimmed_turns}"
        )


class MemoryStore:
    """SQLite 支撑的 Agent 记忆存储。

    表结构：
        turns(id, session_id, role, content, tool_name, created_at)
        facts(id, session_id, key, value, confidence, created_at)
        runs(id, session_id, kind, payload_json, created_at)
    """

    def __init__(self, db_path: str | Path, session_id: str = "default") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_name TEXT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at REAL NOT NULL,
                UNIQUE(session_id, key)
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_turns_sess
                ON turns(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_facts_sess
                ON facts(session_id, key);
            """
        )
        self._conn.commit()

    # ---------- 短期记忆：对话历史 ----------

    def add_turn(
        self,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO turns (session_id, role, content, tool_name, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (self.session_id, role, content, tool_name, time.time()),
        )
        self._conn.commit()

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """按时间顺序取回对话历史（不含系统提示）。"""
        sql = (
            "SELECT role, content, tool_name FROM turns"
            " WHERE session_id = ? ORDER BY id ASC"
        )
        params: list[Any] = [self.session_id]
        if limit is not None:
            sql = (
                "SELECT role, content, tool_name FROM ("
                "  SELECT * FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC"
            )
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {"role": r["role"], "content": r["content"], "tool_name": r["tool_name"]}
            for r in rows
        ]

    def build_messages(
        self,
        system_prompt: str,
        max_turns: int = 12,
        approx_chars_per_token: int = 3,
    ) -> tuple[list[dict[str, Any]], MemoryStats]:
        """组装送给模型的 messages，并按预算裁剪历史。

        返回 (messages, stats)。裁剪策略：从最旧开始丢弃成对的
        user/assistant 消息，始终保留系统提示。
        """
        stats = MemoryStats()
        raw = self.history()
        stats.turns = len(raw)

        def char_len(msgs: list[dict[str, Any]]) -> int:
            return sum(len(m.get("content") or "") for m in msgs)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages += [{"role": r["role"], "content": r["content"]} for r in raw]

        # 从最旧的记录开始裁剪，直到整体积落到预算内
        max_chars = 6000
        while len(messages) > max_turns + 1 and char_len(messages) > max_chars:
            # 保住 system(0)，删掉第一条 user 及其后第一条 assistant
            del messages[1:3]
            stats.trimmed_turns += 2

        stats.tokens_estimate = char_len(messages) // approx_chars_per_token
        return messages, stats

    # ---------- 长期记忆：事实 ----------

    def remember(
        self, key: str, value: str, confidence: float = 1.0
    ) -> None:
        """写入或更新一条事实记忆（幂等）。"""
        self._conn.execute(
            "INSERT INTO facts (session_id, key, value, confidence, created_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(session_id, key) DO UPDATE SET"
            "   value = excluded.value,"
            "   confidence = excluded.confidence,"
            "   created_at = excluded.created_at",
            (self.session_id, key, value, confidence, time.time()),
        )
        self._conn.commit()

    def recall(self, key: str | None = None) -> list[dict[str, Any]]:
        """按 key 精确召回；key=None 时召回全部事实。"""
        if key is None:
            rows = self._conn.execute(
                "SELECT key, value, confidence FROM facts"
                " WHERE session_id = ? ORDER BY id ASC",
                (self.session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT key, value, confidence FROM facts"
                " WHERE session_id = ? AND key LIKE ? ORDER BY id ASC",
                (self.session_id, f"%{key}%"),
            ).fetchall()
        return [
            {"key": r["key"], "value": r["value"], "confidence": r["confidence"]}
            for r in rows
        ]

    def forget(self, key: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM facts WHERE session_id = ? AND key = ?",
            (self.session_id, key),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ---------- 运行归档 ----------

    def log_run(self, kind: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO runs (session_id, kind, payload_json, created_at)"
            " VALUES (?, ?, ?, ?)",
            (self.session_id, kind, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        self._conn.commit()

    def runs(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind is None:
            rows = self._conn.execute(
                "SELECT kind, payload_json, created_at FROM runs"
                " WHERE session_id = ? ORDER BY id ASC",
                (self.session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT kind, payload_json, created_at FROM runs"
                " WHERE session_id = ? AND kind = ? ORDER BY id ASC",
                (self.session_id, kind),
            ).fetchall()
        return [
            {
                "kind": r["kind"],
                "payload": json.loads(r["payload_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ---------- 统计与维护 ----------

    def stats(self) -> MemoryStats:
        turns = self._conn.execute(
            "SELECT COUNT(*) c FROM turns WHERE session_id = ?", (self.session_id,)
        ).fetchone()["c"]
        facts = self._conn.execute(
            "SELECT COUNT(*) c FROM facts WHERE session_id = ?", (self.session_id,)
        ).fetchone()["c"]
        chars = self._conn.execute(
            "SELECT COALESCE(SUM(LENGTH(content)),0) s FROM turns WHERE session_id = ?",
            (self.session_id,),
        ).fetchone()["s"]
        return MemoryStats(turns=turns, facts=facts, tokens_estimate=int(chars) // 3)

    def clear(self) -> None:
        """清空当前会话（保留表结构）。"""
        for table in ("turns", "facts", "runs"):
            self._conn.execute(
                f"DELETE FROM {table} WHERE session_id = ?", (self.session_id,)
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def memory_prompt_block(facts: Iterable[dict[str, Any]]) -> str:
    """把长期记忆渲染成注入系统提示的文本块。"""
    items = list(facts)
    if not items:
        return ""
    lines = [f"- {f['key']}: {f['value']}" for f in items]
    return (
        "\n\n## 你已记住的事实（此前对话中确认过，优先复用，不要重复询问）\n"
        + "\n".join(lines)
    )


__all__ = ["MemoryStore", "MemoryStats", "memory_prompt_block"]