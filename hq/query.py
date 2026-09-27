"""Read-only SQL view of hq/state.db, for crew agents whose shell only runs `python -m`.

    python -m hq.query "SELECT id, status, current_task FROM agents"
    python -m hq.query --tsv "SELECT * FROM approvals WHERE status='approved'"

Only SELECT/WITH/PRAGMA/EXPLAIN statements are accepted, and the connection is opened
read-only (mode=ro), so this can never change the roster, the approvals or the ledger.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from . import db

ALLOWED = ("select", "with", "pragma", "explain")


def run(sql: str, limit: int = 200, db_path=None) -> list[sqlite3.Row]:
    if not sql.strip().lower().startswith(ALLOWED):
        raise SystemExit("hq.query runs read-only statements only (SELECT / WITH / PRAGMA)")
    uri = f"file:{Path(db_path or db.DB_PATH).as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql).fetchmany(limit)
    finally:
        con.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="hq.query", description="read-only SQL against hq/state.db")
    p.add_argument("sql")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--tsv", action="store_true", help="tab-separated, one row per line")
    a = p.parse_args(argv)
    rows = run(a.sql, a.limit)
    if not rows:
        print("(no rows)")
        return
    cols = rows[0].keys()
    if a.tsv:
        print("\t".join(cols))
        for r in rows:
            print("\t".join("" if v is None else str(v).replace("\n", "\\n") for v in tuple(r)))
        return
    for r in rows:
        for c in cols:
            v = r[c]
            if v is not None and str(v) != "":
                print(f"{c}: {str(v)[:600]}")
        print("-" * 60)


if __name__ == "__main__":
    main()
