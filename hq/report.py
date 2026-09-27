"""CLI so any agent (Claude subagent or script) can report to HQ.

  python -m hq.report init
  python -m hq.report heartbeat researcher working "Reading competitor pages"
  python -m hq.report heartbeat researcher idle
  python -m hq.report event builder "Built 3 drafts" --level success
  python -m hq.report agent add analyst ANALYST "Numbers and trends" --room analytics
  python -m hq.report submit "Landing page v2" --by critic --score 9.2 --file output/landing_v2.png
  python -m hq.report approvals --status approved
  python -m hq.report shipped 7 --by architect --note "deployed"
  python -m hq.report ledger sale 2499 --platform stripe --ref order-123     (optional money module)

Every command prints one short line (or nothing) and never prints secrets.
"""
from __future__ import annotations

import argparse
import sys

from hq import config, db


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="hq.report", description="report to HQ (hq/state.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create tables and register the crew from hq/crew.json")

    hb = sub.add_parser("heartbeat", help="set an agent's live status")
    hb.add_argument("agent")
    hb.add_argument("status", choices=db.AGENT_STATUSES)
    hb.add_argument("task", nargs="?")

    ev = sub.add_parser("event", help="add a line to the events feed")
    ev.add_argument("agent")
    ev.add_argument("message")
    ev.add_argument("--level", default="info", choices=db.EVENT_LEVELS)

    ag = sub.add_parser("agent", help="manage the roster")
    agsub = ag.add_subparsers(dest="agent_cmd", required=True)
    aga = agsub.add_parser("add", help="register an agent (DB + hq/crew.json)")
    aga.add_argument("id")
    aga.add_argument("name", nargs="?")
    aga.add_argument("role", nargs="?", default="")
    aga.add_argument("--room", help="station room (bridge, qa_lab, observatory, workshop, security, "
                                    "comms, broadcast, vault, analytics, or any new name)")
    agsub.add_parser("list", help="print the roster")

    sb = sub.add_parser("submit", help="queue an item for the owner's approval")
    sb.add_argument("title")
    sb.add_argument("--kind", default="item")
    sb.add_argument("--summary")
    sb.add_argument("--file", help="image under output/ to show as the thumbnail")
    sb.add_argument("--link", help="URL or path the owner should open")
    sb.add_argument("--by", default="critic", help="submitting agent")
    sb.add_argument("--score", type=float, help="CRITIC score; refused if below HQ_PASS_SCORE")

    ap = sub.add_parser("approvals", help="list approval items")
    ap.add_argument("--status", default="pending", choices=db.APPROVAL_STATUSES)

    sh = sub.add_parser("shipped", help="mark an owner-approved item as done/shipped")
    sh.add_argument("id", type=int)
    sh.add_argument("--by", default="architect")
    sh.add_argument("--note")

    lg = sub.add_parser("ledger", help="record a REAL transaction (signed cents)")
    lg.add_argument("kind", choices=("sale", "refund", "fee", "cost", "investment", "payout"))
    lg.add_argument("amount_cents", type=int)
    lg.add_argument("--platform")
    lg.add_argument("--ref")
    lg.add_argument("--note")

    a = p.parse_args(argv)
    db.init_db()
    try:
        if a.cmd == "init":
            print(f"HQ ready: {db.DB_PATH} ({len(db.load_crew())} agents in hq/crew.json)")
        elif a.cmd == "heartbeat":
            db.heartbeat(a.agent, a.status, a.task, a.task)
        elif a.cmd == "event":
            db.log_event(a.agent, a.message, a.level)
        elif a.cmd == "agent" and a.agent_cmd == "add":
            ag = db.add_agent(a.id, a.name, a.role, a.room)
            print(f"registered {ag['id']} ({ag['name']}) in room {ag['room']}")
        elif a.cmd == "agent" and a.agent_cmd == "list":
            with db.connect() as c:
                for r in c.execute("SELECT id, name, room, status, current_task FROM agents ORDER BY rowid"):
                    print(f"{r['id']:<14}{r['name']:<14}{r['room']:<14}{r['status']:<9}{r['current_task'] or ''}")
        elif a.cmd == "submit":
            item = db.submit_approval(a.title, kind=a.kind, summary=a.summary, file_path=a.file,
                                      link=a.link, submitted_by=a.by, score=a.score,
                                      pass_score=config.pass_score())
            print(f"approval #{item} queued")
        elif a.cmd == "approvals":
            for it in db.list_approvals(a.status):
                score = f" score {it['score']:g}" if it["score"] is not None else ""
                note = f" | owner: {it['owner_note']}" if it["owner_note"] else ""
                print(f"#{it['id']} [{it['kind']}] {it['title']}{score}{note}")
        elif a.cmd == "shipped":
            db.mark_shipped(a.id, a.by, a.note)
        elif a.cmd == "ledger":
            from hq import ledger
            ledger.add_entry(a.kind, a.amount_cents, a.platform, a.ref, a.note)
    except (ValueError, KeyError) as ex:
        print(f"hq.report: {ex.args[0] if ex.args else ex}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
