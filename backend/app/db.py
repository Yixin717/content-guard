"""SQLite 数据层：建表、seed 规则、最小读写。

设计取舍：
- 不用 ORM：6 张表、字段固定，sqlite3 直写更透明，也便于面试时逐行解释；
- 规则以 CSV 为唯一来源，DB 里是**副本**（init_db 时重建），避免两处手工同步；
- 确认表用 UNIQUE(draft_id) 实现幂等，而不是应用层先查后写（并发下会重复）。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .config import settings
from .rules import load_rules

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id            TEXT PRIMARY KEY,
    brief         TEXT NOT NULL,
    tone          TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id            TEXT PRIMARY KEY,
    product_id    TEXT NOT NULL,
    angle         TEXT NOT NULL,
    angle_name    TEXT,
    title         TEXT NOT NULL,
    hook          TEXT,
    script        TEXT NOT NULL,
    selling_points TEXT,
    disclosure    TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft / checked / confirmed
    owner_id      TEXT,                            -- 匿名设备号；老数据为 NULL
    created_at    TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS checks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id      TEXT NOT NULL,
    rule_id       TEXT,
    quote         TEXT,
    severity      TEXT,
    suggestion    TEXT,
    confidence    REAL,
    verdict       TEXT NOT NULL,                   -- violation / uncertain / suspected
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confirmations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id      TEXT NOT NULL UNIQUE,            -- 幂等的关键
    final_content TEXT NOT NULL,
    reviewer      TEXT,
    created_at    TEXT NOT NULL
);

-- 事件流：每次"查过"就是一条记录（方案 C）。payload 里存当次分析快照，供点开恢复。
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id        TEXT NOT NULL,
    kind            TEXT NOT NULL,                   -- check / confirm
    draft_id        TEXT,
    title           TEXT,
    violation_count INTEGER NOT NULL DEFAULT 0,
    remaining_count INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'checked', -- checked / confirmed
    payload         TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id            TEXT PRIMARY KEY,
    category      TEXT NOT NULL,
    title         TEXT NOT NULL,
    quote         TEXT,
    source        TEXT,
    source_url    TEXT,
    fetched_at    TEXT,
    severity      TEXT,
    status        TEXT,
    examples      TEXT,
    counter_examples TEXT,
    note          TEXT,
    version       TEXT
);

CREATE INDEX IF NOT EXISTS idx_drafts_product ON drafts(product_id);
CREATE INDEX IF NOT EXISTS idx_checks_draft ON checks(draft_id);
CREATE INDEX IF NOT EXISTS idx_rules_category ON rules(category);
CREATE INDEX IF NOT EXISTS idx_events_owner ON events(owner_id, id DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """老库补列：SQLite 没有 IF NOT EXISTS 的 ALTER，只能先查 PRAGMA。"""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db(db_path: Optional[Path] = None, seed: bool = True) -> int:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "drafts", "owner_id", "TEXT")
        if not seed:
            return 0
        rules = load_rules()
        conn.executemany(
            """INSERT INTO rules (id, category, title, quote, source, source_url, fetched_at,
                                  severity, status, examples, counter_examples, note, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 category=excluded.category, title=excluded.title, quote=excluded.quote,
                 source=excluded.source, source_url=excluded.source_url,
                 severity=excluded.severity, status=excluded.status,
                 examples=excluded.examples, counter_examples=excluded.counter_examples,
                 note=excluded.note, version=excluded.version""",
            [
                (
                    r.id, r.category, r.title, r.quote, r.source, r.source_url, r.fetched_at,
                    r.severity, r.status, r.examples, r.counter_examples, r.note, r.version,
                )
                for r in rules
            ],
        )
        return len(rules)


# ---------- 写入 ----------

def insert_product(conn: sqlite3.Connection, product_id: str, brief: str, tone: str) -> None:
    conn.execute(
        "INSERT INTO products (id, brief, tone, created_at) VALUES (?,?,?,?)",
        (product_id, brief, tone, now()),
    )


def insert_draft(conn: sqlite3.Connection, d: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO drafts (id, product_id, angle, angle_name, title, hook, script,
                               selling_points, disclosure, status, owner_id, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            d["id"], d["product_id"], d["angle"], d.get("angle_name", ""), d["title"],
            d.get("hook", ""), d["script"], json.dumps(d.get("selling_points", []), ensure_ascii=False),
            d.get("disclosure", ""), d.get("status", "draft"), d.get("owner_id"), now(),
        ),
    )


def save_check(conn: sqlite3.Connection, draft_id: str, verdict: str, item: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO checks (draft_id, rule_id, quote, severity, suggestion, confidence, verdict, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            draft_id, item.get("rule_id"), item.get("quote", ""), item.get("severity", ""),
            item.get("suggestion", ""), item.get("confidence", 0.0), verdict, now(),
        ),
    )


def upsert_confirmation(conn: sqlite3.Connection, draft_id: str, final_content: str, reviewer: str) -> Dict[str, Any]:
    """返回 {audit_id, idempotent}；重复确认不新增行（靠 UNIQUE 约束）。"""
    existing = conn.execute(
        "SELECT id, created_at FROM confirmations WHERE draft_id = ?", (draft_id,)
    ).fetchone()
    if existing:
        return {"audit_id": existing["id"], "idempotent": True, "confirmed_at": existing["created_at"]}

    cur = conn.execute(
        "INSERT INTO confirmations (draft_id, final_content, reviewer, created_at) VALUES (?,?,?,?)",
        (draft_id, final_content, reviewer, now()),
    )
    conn.execute("UPDATE drafts SET status='confirmed' WHERE id=?", (draft_id,))
    return {"audit_id": cur.lastrowid, "idempotent": False, "confirmed_at": now()}


# ---------- 读取 ----------

def get_draft(conn: sqlite3.Connection, draft_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()


def list_rules(conn: sqlite3.Connection, category: Optional[str] = None) -> List[sqlite3.Row]:
    if category:
        return conn.execute("SELECT * FROM rules WHERE category=? ORDER BY id", (category,)).fetchall()
    return conn.execute("SELECT * FROM rules ORDER BY id").fetchall()


def add_event(
    conn: sqlite3.Connection,
    owner_id: str,
    kind: str,
    draft_id: Optional[str],
    title: Optional[str],
    violation_count: int = 0,
    remaining_count: int = 0,
    status: str = "checked",
    payload: Optional[Dict[str, Any]] = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO events (owner_id, kind, draft_id, title, violation_count, remaining_count,
                               status, payload, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            owner_id, kind, draft_id, title, int(violation_count), int(remaining_count),
            status, json.dumps(payload, ensure_ascii=False) if payload is not None else None, now(),
        ),
    )
    return int(cur.lastrowid)


def list_events(conn: sqlite3.Connection, owner_id: str, limit: int = 20) -> List[sqlite3.Row]:
    """只返回某个设备的记录：没有账号，也不能互相看到。"""
    return conn.execute(
        """SELECT id, draft_id, title, violation_count, remaining_count, status, created_at
           FROM events WHERE owner_id = ? AND kind = 'check'
           ORDER BY id DESC LIMIT ?""",
        (owner_id, limit),
    ).fetchall()


def get_event(conn: sqlite3.Connection, event_id: int, owner_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM events WHERE id = ? AND owner_id = ?",
        (event_id, owner_id),
    ).fetchone()


def mark_confirmed(conn: sqlite3.Connection, owner_id: str, draft_id: str) -> None:
    """确认后把这次草稿最近的一条检查记录标为已确认。"""
    conn.execute(
        """UPDATE events SET status='confirmed'
           WHERE id = (SELECT id FROM events
                       WHERE owner_id=? AND draft_id=? AND kind='check'
                       ORDER BY id DESC LIMIT 1)""",
        (owner_id, draft_id),
    )


def draft_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["selling_points"] = json.loads(d.get("selling_points") or "[]")
    except json.JSONDecodeError:
        d["selling_points"] = []
    return d


def _main(argv: Sequence[str]) -> int:

    action = argv[1] if len(argv) > 1 else "init"
    if action == "init":
        n = init_db()
        print(f"建库完成：{settings.db_path.name}，seed {n} 条规则")
    elif action == "reset":
        if settings.db_path.exists():
            settings.db_path.unlink()
        n = init_db()
        print(f"已重建：{settings.db_path.name}，seed {n} 条规则")
    else:
        print("用法：python -m app.db [init|reset]")
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv))
