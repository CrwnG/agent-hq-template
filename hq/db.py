"""Shared HQ state: every agent reports here, the dashboard reads from here.

One SQLite file (hq/state.db, gitignored) with three core tables:

  agents     the crew roster (seeded from hq/crew.json) + live status per agent
  events     an append-only feed of what happened
  approvals  items waiting for the owner, and the owner's decisions

The optional money module lives in hq/ledger.py and adds its own table.
Nothing here fabricates data: every row comes from an agent or the owner.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

HQ_DIR = Path(__file__).resolve().parent
DB_PATH = HQ_DIR / "state.db"
CREW_FILE = HQ_DIR / "crew.json"

AGENT_STATUSES = ("idle", "working", "blocked", "offline")
EVENT_LEVELS = ("info", "success", "warn", "error")
# pending -> approved | rejected (by the owner); approved -> shipped (by the crew, after it acts)
APPROVAL_STATUSES = ("pending", "approved", "rejected", "shipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    room TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'offline',
    current_task TEXT,
    last_heartbeat TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent_id TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'item',
    title TEXT NOT NULL,
    summary TEXT,
    file_path TEXT,
    link TEXT,
    submitted_by TEXT,
    score REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    owner_note TEXT,
    created_ts TEXT NOT NULL,
    reviewed_ts TEXT,
    shipped_ts TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path | str | None = None):
    conn = sqlite3.connect(db_path or DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- crew

def load_crew(crew_file: Path | str | None = None) -> list[dict]:
    """The roster in hq/crew.json: [{"id", "name", "role", "room"}, ...]."""
    path = Path(crew_file or CREW_FILE)
    if not path.exists():
        return []
    crew = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for a in crew:
        aid = str(a["id"]).strip().lower()
        out.append({"id": aid, "name": str(a.get("name") or aid.upper()),
                    "role": str(a.get("role") or ""), "room": str(a.get("room") or aid)})
    return out


def init_db(db_path: Path | str | None = None, crew_file: Path | str | None = None) -> None:
    """Create tables and register every crew.json agent (idempotent; never resets status)."""
    with connect(db_path) as c:
        c.executescript(SCHEMA)
        for a in load_crew(crew_file):
            c.execute(
                "INSERT INTO agents (id, name, role, room) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role, room=excluded.room",
                (a["id"], a["name"], a["role"], a["room"]),
            )


def add_agent(agent_id: str, name: str | None = None, role: str = "", room: str | None = None,
              db_path=None, crew_file: Path | str | None = None, save: bool = True) -> dict:
    """Register (or update) an agent in the DB and, with save=True, in hq/crew.json."""
    agent_id = agent_id.strip().lower()
    if not agent_id or not agent_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("agent id must be letters, digits, '-' or '_'")
    a = {"id": agent_id, "name": name or agent_id.upper(), "role": role, "room": room or agent_id}
    with connect(db_path) as c:
        c.executescript(SCHEMA)
        c.execute(
            "INSERT INTO agents (id, name, role, room) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role, room=excluded.room",
            (a["id"], a["name"], a["role"], a["room"]),
        )
    if save:
        path = Path(crew_file or CREW_FILE)
        crew = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        crew = [x for x in crew if str(x.get("id", "")).lower() != agent_id] + [a]
        path.write_text("[\n" + ",\n".join("  " + json.dumps(x) for x in crew) + "\n]\n", encoding="utf-8")
    return a


def heartbeat(agent_id: str, status: str, task: str | None = None,
              message: str | None = None, db_path=None) -> None:
    """Set an agent's live status. An unknown agent is registered on the fly
    (own room), so a new role shows up on the station without extra setup."""
    if status not in AGENT_STATUSES:
        raise ValueError(f"status must be one of {AGENT_STATUSES}")
    agent_id = agent_id.strip().lower()
    with connect(db_path) as c:
        c.execute(
            "INSERT INTO agents (id, name, role, room) VALUES (?, ?, '', ?) ON CONFLICT(id) DO NOTHING",
            (agent_id, agent_id.upper(), agent_id),
        )
        c.execute(
            "UPDATE agents SET status=?, current_task=?, last_heartbeat=? WHERE id=?",
            (status, task, now(), agent_id),
        )
        if message:
            c.execute(
                "INSERT INTO events (ts, agent_id, level, message) VALUES (?, ?, 'info', ?)",
                (now(), agent_id, message),
            )


def log_event(agent_id: str | None, message: str, level: str = "info", db_path=None) -> None:
    if level not in EVENT_LEVELS:
        raise ValueError(f"level must be one of {EVENT_LEVELS}")
    with connect(db_path) as c:
        c.execute(
            "INSERT INTO events (ts, agent_id, level, message) VALUES (?, ?, ?, ?)",
            (now(), agent_id, level, message),
        )


# ---------------------------------------------------------------- approvals

def submit_approval(title: str, *, kind: str = "item", summary: str | None = None,
                    file_path: str | None = None, link: str | None = None,
                    submitted_by: str | None = None, score: float | None = None,
                    pass_score: float | None = None, db_path=None) -> int:
    """Queue an item for the owner. With `pass_score`, a lower `score` is refused:
    work below the quality bar never reaches the owner."""
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if score is not None and pass_score is not None and score < pass_score:
        raise ValueError(f"score {score:g} is below the bar ({pass_score:g}); fix it, don't submit it")
    with connect(db_path) as c:
        cur = c.execute(
            "INSERT INTO approvals (kind, title, summary, file_path, link, submitted_by, score, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, title, summary, file_path, link, submitted_by, score, now()),
        )
        item_id = cur.lastrowid
        c.execute(
            "INSERT INTO events (ts, agent_id, level, message) VALUES (?, ?, 'info', ?)",
            (now(), submitted_by, f"Approval #{item_id} queued for the owner: {title}"),
        )
    return item_id


def get_approval(item_id: int, db_path=None) -> dict | None:
    with connect(db_path) as c:
        row = c.execute("SELECT * FROM approvals WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def list_approvals(status: str = "pending", db_path=None) -> list[dict]:
    if status not in APPROVAL_STATUSES:
        raise ValueError(f"status must be one of {APPROVAL_STATUSES}")
    with connect(db_path) as c:
        rows = c.execute("SELECT * FROM approvals WHERE status=? ORDER BY id", (status,)).fetchall()
    return [dict(r) for r in rows]


def decide_approval(item_id: int, approve: bool, note: str = "", title: str | None = None,
                    db_path=None) -> tuple[dict | None, bool]:
    """Owner decision on a pending item. Returns (item, changed); changed is False
    if the item wasn't pending (already decided)."""
    note = (note or "").strip()
    title = (title or "").strip() or None
    new_status = "approved" if approve else "rejected"
    if not approve:
        title = None  # a rejection never edits the item
    with connect(db_path) as c:
        before = c.execute("SELECT title FROM approvals WHERE id=?", (item_id,)).fetchone()
        cur = c.execute(
            "UPDATE approvals SET status=?, reviewed_ts=?, owner_note=?, title=COALESCE(?, title) "
            "WHERE id=? AND status='pending'",
            (new_status, now(), note or None, title, item_id),
        )
        changed = cur.rowcount > 0
        if changed:
            edited = title is not None and before is not None and before["title"] != title
            label = title or (before["title"] if before else f"#{item_id}")
            msg = (f"Owner {new_status} #{item_id}: {label}" + (" (title edited)" if edited else "")
                   + (f" - {note}" if note else ""))
            c.execute(
                "INSERT INTO events (ts, agent_id, level, message) VALUES (?, 'owner', ?, ?)",
                (now(), "success" if approve else "warn", msg),
            )
    return get_approval(item_id, db_path), changed


def mark_shipped(item_id: int, agent_id: str | None = None, note: str | None = None,
                 db_path=None) -> None:
    """The crew acted on an approved item (published, sent, deployed...)."""
    with connect(db_path) as c:
        cur = c.execute(
            "UPDATE approvals SET status='shipped', shipped_ts=? WHERE id=? AND status='approved'",
            (now(), item_id),
        )
        if not cur.rowcount:
            raise ValueError(f"approval #{item_id} is not 'approved'; only owner-approved items ship")
        c.execute(
            "INSERT INTO events (ts, agent_id, level, message) VALUES (?, ?, 'success', ?)",
            (now(), agent_id, f"Shipped approval #{item_id}" + (f": {note}" if note else "")),
        )
