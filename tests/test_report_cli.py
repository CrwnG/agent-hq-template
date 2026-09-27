import pytest

from hq import db, query, report


def test_init_heartbeat_event(capsys):
    report.main(["init"])
    assert "HQ ready" in capsys.readouterr().out
    report.main(["heartbeat", "researcher", "working", "reading"])
    report.main(["event", "researcher", "found 3 sources", "--level", "success"])
    rows = query.run("SELECT status, current_task FROM agents WHERE id='researcher'")
    assert (rows[0]["status"], rows[0]["current_task"]) == ("working", "reading")
    ev = query.run("SELECT level, message FROM events ORDER BY id DESC LIMIT 1")[0]
    assert (ev["level"], ev["message"]) == ("success", "found 3 sources")


def test_submit_approvals_shipped(capsys):
    report.main(["submit", "Page v1", "--kind", "page", "--score", "9.1", "--by", "critic"])
    assert "approval #1 queued" in capsys.readouterr().out
    report.main(["approvals"])
    assert "#1 [page] Page v1 score 9.1" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        report.main(["shipped", "1"])  # not approved yet
    db.decide_approval(1, True, "go")
    report.main(["shipped", "1", "--note", "live"])
    assert db.get_approval(1)["status"] == "shipped"


def test_submit_under_pass_score_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as ex:
        report.main(["submit", "Meh", "--score", "7"])
    assert ex.value.code == 2
    assert "below the bar" in capsys.readouterr().err


def test_agent_add_and_list(capsys):
    report.main(["agent", "add", "writer", "WRITER", "Copy", "--room", "comms"])
    report.main(["agent", "list"])
    out = capsys.readouterr().out
    assert "registered writer" in out and "comms" in out


def test_ledger_cli_and_duplicate_ref():
    report.main(["ledger", "sale", "2500", "--platform", "stripe", "--ref", "inv-1"])
    with pytest.raises(SystemExit):
        report.main(["ledger", "sale", "2500", "--platform", "stripe", "--ref", "inv-1"])
    assert query.run("SELECT COUNT(*) AS n FROM ledger")[0]["n"] == 1


def test_query_is_read_only():
    db.init_db()
    with pytest.raises(SystemExit):
        query.run("DELETE FROM agents")
    with pytest.raises(Exception):
        query.run("SELECT 1; DELETE FROM agents")
    assert query.run("SELECT COUNT(*) AS n FROM agents")[0]["n"] >= 2
