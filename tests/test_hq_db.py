import json

import pytest

from hq import config, db


def test_init_registers_crew_from_crew_json():
    db.init_db()
    with db.connect() as c:
        rows = {r["id"]: dict(r) for r in c.execute("SELECT * FROM agents")}
    crew = db.load_crew()
    assert set(rows) == {a["id"] for a in crew}
    assert {"architect", "critic"} <= set(rows)
    assert all(r["status"] == "offline" for r in rows.values())


def test_init_is_idempotent_and_keeps_live_status():
    db.init_db()
    db.heartbeat("critic", "working", "reviewing")
    db.init_db()
    with db.connect() as c:
        r = c.execute("SELECT status, current_task FROM agents WHERE id='critic'").fetchone()
    assert (r["status"], r["current_task"]) == ("working", "reviewing")


def test_heartbeat_sets_status_and_logs_message():
    db.init_db()
    db.heartbeat("builder", "working", "drafts", "started drafts")
    with db.connect() as c:
        a = c.execute("SELECT status, current_task, last_heartbeat FROM agents WHERE id='builder'").fetchone()
        ev = c.execute("SELECT agent_id, message FROM events ORDER BY id DESC").fetchone()
    assert a["status"] == "working" and a["current_task"] == "drafts" and a["last_heartbeat"]
    assert (ev["agent_id"], ev["message"]) == ("builder", "started drafts")
    with pytest.raises(ValueError):
        db.heartbeat("builder", "sleeping")


def test_unknown_agent_heartbeat_registers_it():
    db.init_db()
    db.heartbeat("Pilot", "working", "flying")
    with db.connect() as c:
        r = c.execute("SELECT name, room, status FROM agents WHERE id='pilot'").fetchone()
    assert (r["name"], r["room"], r["status"]) == ("PILOT", "pilot", "working")


def test_add_agent_writes_db_and_crew_json():
    db.init_db()
    db.add_agent("analyst", "ANALYST", "Numbers", "analytics")
    db.add_agent("analyst", "ANALYST", "Numbers and trends", "analytics")  # update, no duplicate
    crew = json.loads(db.CREW_FILE.read_text(encoding="utf-8"))
    assert [a["role"] for a in crew if a["id"] == "analyst"] == ["Numbers and trends"]
    with db.connect() as c:
        assert c.execute("SELECT room FROM agents WHERE id='analyst'").fetchone()["room"] == "analytics"
    with pytest.raises(ValueError):
        db.add_agent("bad id!")


def test_event_levels():
    db.init_db()
    db.log_event("critic", "3 passed", "success")
    with pytest.raises(ValueError):
        db.log_event("critic", "x", "loud")


def test_approval_lifecycle():
    db.init_db()
    item = db.submit_approval("Landing v2", kind="page", submitted_by="critic", score=9.2, pass_score=9)
    assert [a["id"] for a in db.list_approvals("pending")] == [item]
    got, changed = db.decide_approval(item, True, "ship it", title="Landing page v2")
    assert changed and got["status"] == "approved" and got["title"] == "Landing page v2"
    assert got["owner_note"] == "ship it" and got["reviewed_ts"]
    _, changed = db.decide_approval(item, False)
    assert not changed  # already decided
    db.mark_shipped(item, "architect", "deployed")
    assert db.get_approval(item)["status"] == "shipped"


def test_only_approved_items_ship():
    db.init_db()
    item = db.submit_approval("Draft", submitted_by="critic")
    with pytest.raises(ValueError):
        db.mark_shipped(item)
    db.decide_approval(item, False, "no")
    with pytest.raises(ValueError):
        db.mark_shipped(item)


def test_submit_below_the_bar_is_refused():
    db.init_db()
    with pytest.raises(ValueError, match="below the bar"):
        db.submit_approval("Weak", score=8.5, pass_score=9)
    with pytest.raises(ValueError):
        db.submit_approval("   ")
    assert db.list_approvals("pending") == []


def test_config_reads_only_hq_keys_from_dotenv(isolated_hq, monkeypatch):
    env = isolated_hq / ".env"
    env.write_text('SECRET_TOKEN=abc123\nHQ_PROJECT_NAME="Test Deck"\nHQ_PASS_SCORE=9.5\n'
                   'HQ_PLUGINS=\n', encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env)
    assert config.project_name() == "Test Deck"
    assert config.pass_score() == 9.5
    assert config.plugins() == []
    with pytest.raises(KeyError):
        config.get("SECRET_TOKEN", "")
    monkeypatch.setenv("HQ_PASS_SCORE", "8")
    assert config.pass_score() == 8.0
