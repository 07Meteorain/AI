"""SQLite 存储：卡组、复习状态、复习日志。

为什么用 SQLite 而不是 JSON：复习记录是只增不改的流水，天然适合表格；
重建卡组时又要保留每张卡的复习状态。JSON 需要「读入—改—整体写回」，
一旦中断就丢整份进度，SQLite 一条语句就能原子更新。
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .model import Card
from .scheduler import State, is_due, parse_date, today_iso

SCHEMA_VERSION = 1
DEFAULT_DB = "recall.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    source TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    line INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'approved',
    created TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS states (
    card_id TEXT PRIMARY KEY,
    ef REAL NOT NULL DEFAULT 2.5,
    reps INTEGER NOT NULL DEFAULT 0,
    interval INTEGER NOT NULL DEFAULT 0,
    due TEXT NOT NULL DEFAULT '',
    lapses INTEGER NOT NULL DEFAULT 0,
    suspended INTEGER NOT NULL DEFAULT 0,
    last_review TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    grade INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL,
    interval INTEGER NOT NULL,
    ef REAL NOT NULL,
    reps INTEGER NOT NULL,
    due TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
CREATE INDEX IF NOT EXISTS idx_reviews_card ON reviews(card_id);
CREATE INDEX IF NOT EXISTS idx_states_due ON states(due);
"""


def connect(path: str = DEFAULT_DB) -> sqlite3.Connection:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()
    elif int(row["value"]) != SCHEMA_VERSION:
        raise RuntimeError(
            "数据库 schema 版本是 {}，本程序需要 {}；请换一个 --db 路径或先备份迁移".format(
                row["value"], SCHEMA_VERSION
            )
        )
    return conn


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def _card_from_row(row: sqlite3.Row) -> Card:
    try:
        tags = tuple(json.loads(row["tags"]) or ())
    except (ValueError, TypeError):
        tags = ()
    return Card(
        id=row["id"],
        kind=row["kind"],
        prompt=row["prompt"],
        answer=row["answer"],
        source=row["source"],
        heading=row["heading"],
        line=int(row["line"]),
        confidence=float(row["confidence"]),
        tags=tags,
        status=row["status"],
        created=row["created"],
    )


def upsert_cards(conn: sqlite3.Connection, cards: Iterable[Card]) -> Tuple[int, int]:
    """写入卡组。已存在的卡保留 status / created / 复习状态，只更新内容字段。

    返回 (新增, 更新) 的粗略计数（SQLite 不区分 upsert 的插入与更新，
    这里按执行前是否存在 id 统计）。
    """
    existing = {
        row[0] for row in conn.execute("SELECT id FROM cards").fetchall()
    }
    inserted = 0
    updated = 0
    for card in cards:
        if card.id in existing:
            updated += 1
        else:
            inserted += 1
    conn.executemany(
        """
        INSERT INTO cards(id, kind, prompt, answer, source, heading, line, confidence, tags, status, created)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            kind=excluded.kind,
            prompt=excluded.prompt,
            answer=excluded.answer,
            source=excluded.source,
            heading=excluded.heading,
            line=excluded.line,
            confidence=excluded.confidence,
            tags=excluded.tags
        """,
        [
            (
                c.id,
                c.kind,
                c.prompt,
                c.answer,
                c.source,
                c.heading,
                c.line,
                c.confidence,
                json.dumps(list(c.tags), ensure_ascii=False),
                c.status,
                c.created,
            )
            for c in cards
        ],
    )
    conn.commit()
    return inserted, updated


def list_cards(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    kinds: Optional[Sequence[str]] = None,
) -> List[Card]:
    sql = "SELECT * FROM cards"
    clauses = []
    params: List[object] = []
    if status:
        clauses.append("status=?")
        params.append(status)
    if kinds:
        clauses.append("kind IN ({})".format(",".join("?" for _ in kinds)))
        params.extend(kinds)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY source, line, prompt"
    return [_card_from_row(row) for row in conn.execute(sql, params).fetchall()]


def get_card(conn: sqlite3.Connection, card_id: str) -> Optional[Card]:
    row = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    return _card_from_row(row) if row else None


def states_for(conn: sqlite3.Connection, card_ids: Optional[Iterable[str]] = None) -> Dict[str, State]:
    if card_ids is None:
        rows = conn.execute("SELECT * FROM states").fetchall()
    else:
        ids = list(card_ids)
        if not ids:
            return {}
        rows = conn.execute(
            "SELECT * FROM states WHERE card_id IN ({})".format(",".join("?" for _ in ids)), ids
        ).fetchall()
    out: Dict[str, State] = {}
    for row in rows:
        out[row["card_id"]] = State(
            ef=float(row["ef"]),
            reps=int(row["reps"]),
            interval=int(row["interval"]),
            due=row["due"],
            lapses=int(row["lapses"]),
            suspended=bool(row["suspended"]),
            last_review=row["last_review"],
        )
    return out


def save_state(conn: sqlite3.Connection, card_id: str, state: State) -> None:
    conn.execute(
        """
        INSERT INTO states(card_id, ef, reps, interval, due, lapses, suspended, last_review)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(card_id) DO UPDATE SET
            ef=excluded.ef, reps=excluded.reps, interval=excluded.interval,
            due=excluded.due, lapses=excluded.lapses, suspended=excluded.suspended,
            last_review=excluded.last_review
        """,
        (
            card_id,
            state.ef,
            state.reps,
            state.interval,
            state.due,
            state.lapses,
            1 if state.suspended else 0,
            state.last_review,
        ),
    )


def record_review(
    conn: sqlite3.Connection, card_id: str, grade: int, state: State, today: str
) -> None:
    save_state(conn, card_id, state)
    conn.execute(
        "INSERT INTO reviews(card_id, grade, reviewed_at, interval, ef, reps, due) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (card_id, grade, today, state.interval, state.ef, state.reps, state.due),
    )
    conn.commit()


def apply_decisions(
    conn: sqlite3.Connection,
    approved: Sequence[str] = (),
    rejected: Sequence[str] = (),
) -> Dict[str, int]:
    result = {"approved": 0, "rejected": 0, "missing": 0}
    known = {row[0] for row in conn.execute("SELECT id FROM cards").fetchall()}
    for card_id in approved:
        if card_id not in known:
            result["missing"] += 1
            continue
        conn.execute("UPDATE cards SET status='approved' WHERE id=?", (card_id,))
        result["approved"] += 1
    for card_id in rejected:
        if card_id not in known:
            result["missing"] += 1
            continue
        conn.execute("UPDATE cards SET status='rejected' WHERE id=?", (card_id,))
        result["rejected"] += 1
    conn.commit()
    return result


def stats(conn: sqlite3.Connection, today: Optional[str] = None) -> Dict[str, object]:
    today = today or today_iso()
    total = conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
    by_status = {
        row["status"]: row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM cards GROUP BY status").fetchall()
    }
    by_kind = {
        row["kind"]: row["n"]
        for row in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM cards WHERE status='approved' GROUP BY kind ORDER BY n DESC"
        ).fetchall()
    }
    new_count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM cards c
        LEFT JOIN states s ON s.card_id = c.id
        WHERE c.status='approved' AND s.card_id IS NULL
        """
    ).fetchone()["n"]
    due_count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM cards c
        JOIN states s ON s.card_id = c.id
        WHERE c.status='approved' AND s.suspended=0 AND s.due<>'' AND s.due<=?
        """,
        (today,),
    ).fetchone()["n"]
    reviewed_today = conn.execute(
        "SELECT COUNT(*) AS n FROM reviews WHERE reviewed_at=?", (today,)
    ).fetchone()["n"]
    suspended = conn.execute(
        "SELECT COUNT(*) AS n FROM states WHERE suspended=1"
    ).fetchone()["n"]
    return {
        "total": total,
        "by_status": by_status,
        "approved": by_status.get("approved", 0),
        "rejected": by_status.get("rejected", 0),
        "candidate": by_status.get("candidate", 0),
        "by_kind": by_kind,
        "new": new_count,
        "due": due_count,
        "reviewed_today": reviewed_today,
        "suspended": suspended,
        "today": today,
    }


def export_payload(conn: sqlite3.Connection, status: Optional[str] = "approved") -> Dict[str, object]:
    cards = list_cards(conn, status=status)
    states = states_for(conn, [c.id for c in cards])
    items = []
    for card in cards:
        data = card.to_dict()
        state = states.get(card.id)
        if state is not None:
            data["state"] = state.to_dict()
        items.append(data)
    return {
        "version": 1,
        "generated": get_meta(conn, "built_at", ""),
        "source_root": get_meta(conn, "source_root", ""),
        "stats": stats(conn),
        "cards": items,
    }


def next_due_preview(conn: sqlite3.Connection, today: Optional[str] = None, days: int = 7) -> List[Tuple[str, int]]:
    """未来 N 天每天到期的卡片数，用于 stats 的负载预览。"""
    from datetime import datetime, timedelta

    today_date = parse_date(today or today_iso())
    out: List[Tuple[str, int]] = []
    for offset in range(days):
        day = (today_date + timedelta(days=offset)).isoformat()
        count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM cards c JOIN states s ON s.card_id=c.id
            WHERE c.status='approved' AND s.suspended=0 AND s.due=?
            """,
            (day,),
        ).fetchone()["n"]
        out.append((day, count))
    return out
