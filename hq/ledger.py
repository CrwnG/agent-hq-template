"""Optional money module: a ledger of REAL transactions only, in integer cents.

Nothing here estimates or projects. If the project doesn't handle money, ignore
this module and drop "ledger" from HQ_PLUGINS; the rest of HQ doesn't use it.

Sign convention (profit = everything except investment and payout):
  sale        + money earned
  refund      - money given back
  fee         - platform/processor fee (positive = a fee credit)
  cost        - production, hosting, supplies (positive = a supplier refund)
  investment  - one-off money the owner puts in (capital, not a P&L cost)
  payout      + money moved to the owner's bank (a transfer, not profit)

Dedupe: an entry whose (platform, ref) already exists is refused, so importing the
same order twice can't double-count it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from hq import config, db

KINDS = ("sale", "refund", "fee", "cost", "investment", "payout")
MANUAL_SIGN = {"sale": 1, "refund": -1, "fee": -1, "cost": -1, "investment": -1, "payout": 1}
PNL_KINDS = ("sale", "refund", "fee", "cost")
_PLATFORM_RE = re.compile(r"[a-z0-9_]{1,32}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    platform TEXT,
    kind TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    ref TEXT,
    note TEXT
);
"""


def ensure_table(conn) -> None:
    conn.executescript(SCHEMA)


# ---------------------------------------------------------------- parsing

def dollars_to_cents(raw: str | float | int) -> int:
    """Strict owner input: positive, at most 2 decimals, below $1,000,000."""
    s = str(raw).strip().replace("$", "").replace(",", "")
    if not re.fullmatch(r"\d{1,7}(\.\d{1,2})?|\.\d{1,2}", s):
        raise ValueError("amount must be a positive number like 12.50 (max 2 decimals)")
    cents = int((Decimal(s) * 100).quantize(Decimal("1")))
    if cents <= 0:
        raise ValueError("amount must be greater than zero")
    if cents >= 100_000_000:
        raise ValueError("amount too large")
    return cents


def fmt_cents(cents: int | None) -> str:
    c = int(cents or 0)
    return ("-" if c < 0 else "") + f"${abs(c) // 100:,}.{abs(c) % 100:02d}"


def normalize_platform(raw: str | None) -> str:
    p = re.sub(r"[\s\-]+", "_", (raw or "").strip().lower())
    if not _PLATFORM_RE.fullmatch(p):
        raise ValueError("platform must be 1-32 chars of a-z, 0-9, _ (e.g. stripe, cash, other)")
    return p


def valid_month(s: str | None) -> bool:
    return bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", s or ""))


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ---------------------------------------------------------------- writes

def add_entry(kind: str, amount_cents: int, platform: str | None = None, ref: str | None = None,
              note: str | None = None, ts: str | None = None, db_path=None) -> dict:
    """Record a signed entry. Raises ValueError on bad input, KeyError on a duplicate ref."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
        raise ValueError("amount_cents must be an integer")
    platform = normalize_platform(platform or "other")
    ref = (ref or "").strip() or None
    note = (note or "").strip() or None
    with db.connect(db_path) as c:
        ensure_table(c)
        if ref and c.execute("SELECT 1 FROM ledger WHERE platform=? AND ref=?", (platform, ref)).fetchone():
            raise KeyError(f"an entry with platform={platform} ref={ref} already exists")
        cur = c.execute(
            "INSERT INTO ledger (ts, platform, kind, amount_cents, ref, note) VALUES (?, ?, ?, ?, ?, ?)",
            (ts or db.now(), platform, kind, amount_cents, ref, note),
        )
        row = c.execute("SELECT * FROM ledger WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def add_manual(kind: str, amount_cents_positive: int, platform: str, *, ts: str | None = None,
               ref: str | None = None, note: str | None = None, db_path=None) -> dict:
    """Owner-typed entry: the amount is positive and the sign comes from the kind."""
    if kind not in MANUAL_SIGN:
        raise ValueError(f"kind must be one of {tuple(MANUAL_SIGN)}")
    if not isinstance(amount_cents_positive, int) or amount_cents_positive <= 0:
        raise ValueError("amount must be greater than zero")
    return add_entry(kind, MANUAL_SIGN[kind] * amount_cents_positive, platform, ref,
                     note or "manual entry", ts, db_path)


# ---------------------------------------------------------------- reads

def goal_ladder(month_profit_cents: int, goal_cents: int | None = None, rungs: int = 3) -> list[int]:
    """Monthly targets with no ceiling: the goal is the floor, and once passed the
    ladder slides up in goal-sized steps (goal 200: 0 -> 200/400/600, 450 -> 400/600/800).
    A goal of 0 means no goal bar: []."""
    goal = config.goal_cents() if goal_cents is None else goal_cents
    if goal <= 0:
        return []
    reached = max(0, month_profit_cents) // goal * goal
    start = max(goal, reached)
    return [start + i * goal for i in range(rungs)]


def money_summary(db_path=None) -> dict:
    """All-time totals plus this month's profit."""
    month = current_month()
    with db.connect(db_path) as c:
        ensure_table(c)
        rows = c.execute(
            "SELECT kind, COALESCE(SUM(amount_cents), 0) AS total FROM ledger GROUP BY kind"
        ).fetchall()
        mp = c.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM ledger "
            "WHERE kind NOT IN ('investment', 'payout') AND substr(ts, 1, 7)=?", (month,)
        ).fetchone()["total"]
    totals = {r["kind"]: r["total"] for r in rows}
    return {
        "revenue_cents": totals.get("sale", 0),
        "profit_cents": sum(v for k, v in totals.items() if k not in ("investment", "payout")),
        "invested_cents": -totals.get("investment", 0),
        "month": month,
        "month_profit_cents": mp,
        "goal_cents": config.goal_cents(),
        "goals_cents": goal_ladder(mp),
    }


def _blank() -> dict:
    return {"revenue": 0, "refunds": 0, "fees": 0, "costs": 0, "net": 0,
            "investment": 0, "payout": 0, "entries": 0}


_BUCKET = {"sale": "revenue", "refund": "refunds", "fee": "fees", "cost": "costs",
           "investment": "investment", "payout": "payout"}


def month_pnl(month: str | None = None, db_path=None) -> dict:
    """P&L for a calendar month (UTC, by ledger ts), per platform. net = sales +
    refunds + fees + costs (investment and payouts excluded)."""
    month = month or current_month()
    with db.connect(db_path) as c:
        ensure_table(c)
        rows = c.execute(
            "SELECT COALESCE(platform, 'other') AS platform, kind, SUM(amount_cents) AS total, "
            "COUNT(*) AS n FROM ledger WHERE substr(ts, 1, 7)=? GROUP BY 1, 2", (month,)
        ).fetchall()
    plats: dict[str, dict] = {}
    for r in rows:
        if r["kind"] not in _BUCKET:
            continue
        p = plats.setdefault(r["platform"], _blank())
        p[_BUCKET[r["kind"]]] += r["total"]
        p["entries"] += r["n"]
        if r["kind"] in PNL_KINDS:
            p["net"] += r["total"]
    totals = _blank()
    for p in plats.values():
        for k, v in p.items():
            totals[k] += v
    goal = config.goal_cents()
    return {
        "month": month,
        "platforms": [{"platform": k, **v} for k, v in sorted(plats.items())],
        "totals": totals,
        "goal_cents": goal,
        "goals_cents": goal_ladder(totals["net"]),
        "goal_met": goal > 0 and totals["net"] >= goal,
        "to_goal_cents": max(0, goal - totals["net"]) if goal else 0,
    }


def recent(limit: int = 20, db_path=None) -> list[dict]:
    with db.connect(db_path) as c:
        ensure_table(c)
        rows = c.execute(
            "SELECT id, ts, platform, kind, amount_cents, ref, note FROM ledger ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
