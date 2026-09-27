"""Money plugin (optional): P&L, goal ladder and owner money entries.

  GET  /api/ledger/summary           all-time totals + this month's profit and goal ladder
  GET  /api/ledger[?month=YYYY-MM]   the month's P&L per platform + last 20 rows
  POST /api/ledger                   the owner records a real transaction by hand

Writes are guarded by app.py's same-origin middleware. Amounts are typed as
positive dollars; the sign comes from the kind. Nothing is estimated.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr

from hq import db, ledger

NAME = "ledger"
SCRIPTS = ["plugins/ledger.js"]
STYLES = ["plugins/ledger.css"]

router = APIRouter()


class LedgerBody(BaseModel):
    kind: Literal["sale", "cost", "fee", "investment", "refund", "payout"]
    amount: StrictStr | StrictInt | StrictFloat = Field(...)  # strict: true/false are not money
    platform: str = Field(..., min_length=1, max_length=32)
    ref: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    date: str | None = Field(default=None, max_length=10)


def _month_or_400(month: str | None) -> str | None:
    if month and not ledger.valid_month(month):
        raise HTTPException(400, "month must be YYYY-MM")
    return month


def _entry_ts(raw: str | None) -> str:
    if not raw:
        return db.now()
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD")
    today = datetime.now(timezone.utc).date()
    if d > today + timedelta(days=1):
        raise HTTPException(422, "date is in the future")
    if d.year < 2000:
        raise HTTPException(422, "date too old")
    if d == today:
        return db.now()
    return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).isoformat(timespec="seconds")


@router.get("/api/ledger/summary")
def get_summary():
    return ledger.money_summary()


@router.get("/api/ledger")
def get_ledger(month: str | None = Query(default=None)):
    return {
        "pnl": ledger.month_pnl(_month_or_400(month)),
        "recent": ledger.recent(20),
        "kinds": list(ledger.MANUAL_SIGN),
    }


@router.post("/api/ledger")
def post_ledger(body: LedgerBody):
    try:
        cents = ledger.dollars_to_cents(body.amount)
        platform = ledger.normalize_platform(body.platform)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    ts = _entry_ts((body.date or "").strip() or None)
    try:
        row = ledger.add_manual(body.kind, cents, platform, ts=ts, ref=body.ref, note=body.note)
    except KeyError as ex:
        raise HTTPException(409, ex.args[0])
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    db.log_event("owner", f"Owner recorded {row['kind']} {ledger.fmt_cents(row['amount_cents'])} "
                          f"({row['platform']}){' ' + row['ref'] if row['ref'] else ''}", "success")
    return {"entry": row, "pnl": ledger.month_pnl(row["ts"][:7])}
