"""Read-only views over hq/state.db for the dashboard.

Everything here only SELECTs. Writes go through hq.db (the owner's approve/reject
in dashboard/app.py, and plugin routes). Nothing is estimated or invented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hq import db

# A 'working' agent that hasn't heartbeated for this long is shown as idle
# (a subagent that crashed or finished without its final heartbeat).
STALE_AFTER = timedelta(minutes=10)


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def effective_status(status: str, last_heartbeat: str | None,
                     now: datetime | None = None) -> str:
    """A 'working' agent whose heartbeat is older than STALE_AFTER is shown as idle."""
    if status != "working":
        return status
    now = now or datetime.now(timezone.utc)
    hb = _parse_ts(last_heartbeat)
    if hb is None or now - hb > STALE_AFTER:
        return "idle"
    return "working"


def _agent_dict(row, now: datetime) -> dict:
    d = dict(row)
    d["stored_status"] = d["status"]
    d["status"] = effective_status(d["status"], d["last_heartbeat"], now)
    d["stale"] = d["stored_status"] == "working" and d["status"] != "working"
    return d


_AGENT_COLS = "id, name, role, room, status, current_task, last_heartbeat"


def list_agents(db_path=None, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    with db.connect(db_path) as c:
        rows = c.execute(f"SELECT {_AGENT_COLS} FROM agents ORDER BY rowid").fetchall()
    return [_agent_dict(r, now) for r in rows]


def get_agent(agent_id: str, db_path=None, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    with db.connect(db_path) as c:
        row = c.execute(f"SELECT {_AGENT_COLS} FROM agents WHERE id=?", (agent_id,)).fetchone()
    return _agent_dict(row, now) if row else None


def recent_events(limit: int = 50, agent_id: str | None = None, db_path=None) -> list[dict]:
    sql = "SELECT id, ts, agent_id, level, message FROM events"
    args: tuple = ()
    if agent_id:
        sql += " WHERE agent_id=?"
        args = (agent_id,)
    sql += " ORDER BY id DESC LIMIT ?"
    with db.connect(db_path) as c:
        return [dict(r) for r in c.execute(sql, args + (limit,)).fetchall()]


def approval_counts(db_path=None) -> dict:
    with db.connect(db_path) as c:
        rows = c.execute("SELECT status, COUNT(*) AS n FROM approvals GROUP BY status").fetchall()
    counts = {s: 0 for s in db.APPROVAL_STATUSES}
    counts.update({r["status"]: r["n"] for r in rows})
    return counts
