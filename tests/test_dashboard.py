from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from hq import db, ledger
from dashboard import app as dash
from dashboard import queries


@pytest.fixture()
def env(isolated_hq, monkeypatch):
    out = isolated_hq / "output"
    out.mkdir()
    monkeypatch.setattr(dash, "PROJECT_ROOT", isolated_hq)
    monkeypatch.setattr(dash, "OUTPUT_DIR", out)
    db.init_db()
    with TestClient(dash.create_app(["ledger"])) as client:
        yield client, isolated_hq, out


def _submit(title="Page v1", file_path=None, link=None):
    return db.submit_approval(title, kind="page", submitted_by="critic", score=9.2,
                              file_path=str(file_path) if file_path else None, link=link)


def test_state_shape(env):
    client, _, _ = env
    r = client.get("/api/state")
    assert r.status_code == 200
    s = r.json()
    assert set(s) >= {"agents", "counts", "events", "working_count", "server_time", "project", "plugins"}
    assert {a["id"] for a in s["agents"]} == {a["id"] for a in db.load_crew()}
    for a in s["agents"]:
        assert {"id", "name", "role", "room", "status", "current_task", "last_heartbeat"} <= set(a)
    assert s["counts"]["approvals"] == {"pending": 0, "approved": 0, "rejected": 0, "shipped": 0}
    assert s["project"] == "Agent HQ"
    assert [p["name"] for p in s["plugins"]] == ["ledger"]
    assert s["plugins"][0]["scripts"] == ["/static/plugins/ledger.js"]


def test_state_without_plugins(isolated_hq):
    db.init_db()
    with TestClient(dash.create_app([])) as client:
        s = client.get("/api/state").json()
        assert s["plugins"] == []
        assert client.get("/api/ledger/summary").status_code == 404


def test_unknown_plugin_refused():
    with pytest.raises(ValueError):
        dash.create_app(["nope"])


def test_state_reflects_events_and_approvals(env):
    client, _, _ = env
    db.log_event("researcher", "found 12 sources", "success")
    _submit()
    s = client.get("/api/state").json()
    assert s["counts"]["approvals"]["pending"] == 1
    assert s["events"][0]["message"].startswith("Approval #1 queued")
    assert any(e["message"] == "found 12 sources" for e in s["events"])


def test_stale_heartbeat_is_idle(env):
    client, _, _ = env
    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec="seconds")
    with db.connect() as c:
        c.execute("UPDATE agents SET status='working', last_heartbeat=? WHERE id='researcher'", (old,))
    db.heartbeat("builder", "working", "drafting")
    agents = {a["id"]: a for a in client.get("/api/state").json()["agents"]}
    assert agents["researcher"]["status"] == "idle" and agents["researcher"]["stale"] is True
    assert agents["researcher"]["stored_status"] == "working"
    assert agents["builder"]["status"] == "working"
    assert client.get("/api/state").json()["working_count"] == 1


def test_effective_status_rules():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    fresh = (now - timedelta(minutes=9)).isoformat()
    stale = (now - timedelta(minutes=10, seconds=1)).isoformat()
    assert queries.effective_status("working", fresh, now) == "working"
    assert queries.effective_status("working", stale, now) == "idle"
    assert queries.effective_status("working", None, now) == "idle"
    assert queries.effective_status("blocked", stale, now) == "blocked"
    assert queries.effective_status("offline", None, now) == "offline"


def test_agent_detail(env):
    client, _, _ = env
    db.heartbeat("builder", "blocked", "needs a login", "waiting on owner")
    r = client.get("/api/agents/builder").json()
    assert r["agent"]["status"] == "blocked"
    assert r["agent"]["current_task"] == "needs a login"
    assert r["events"][0]["message"] == "waiting on owner"
    assert client.get("/api/agents/nobody").status_code == 404


def test_unknown_room_agent_still_listed(env):
    client, _, _ = env
    db.heartbeat("pilot", "working", "flying")
    agents = {a["id"]: a for a in client.get("/api/state").json()["agents"]}
    assert agents["pilot"]["room"] == "pilot"


def test_approve_transition(env):
    client, _, out = env
    item = _submit(file_path=out / "a.png", link="https://example.com/preview")
    items = client.get("/api/approvals").json()["items"]
    assert [d["id"] for d in items] == [item]
    assert items[0]["image_url"] and items[0]["link_url"] == "https://example.com/preview"

    r = client.post(f"/api/approvals/{item}/approve", json={"note": "great"})
    assert r.status_code == 200
    d = db.get_approval(item)
    assert d["status"] == "approved" and d["reviewed_ts"] and d["owner_note"] == "great"
    assert client.get("/api/approvals").json()["items"] == []
    assert [x["id"] for x in client.get("/api/approvals?status=approved").json()["items"]] == [item]
    ev = queries.recent_events(1)[0]
    assert ev["agent_id"] == "owner" and "approved" in ev["message"]
    # a second decision on the same item is refused
    assert client.post(f"/api/approvals/{item}/reject", json={"note": "x"}).status_code == 409


def test_reject_transition_and_unknown(env):
    client, _, _ = env
    item = _submit()
    r = client.post(f"/api/approvals/{item}/reject", json={"note": "too generic"})
    assert r.status_code == 200
    d = db.get_approval(item)
    assert d["status"] == "rejected" and d["owner_note"] == "too generic"
    ev = queries.recent_events(1)[0]
    assert ev["agent_id"] == "owner" and ev["level"] == "warn"
    assert client.post("/api/approvals/9999/approve").status_code == 404
    assert client.get("/api/approvals?status=bogus").status_code == 400


def test_approve_with_edited_title(env):
    client, _, _ = env
    item = _submit()
    r = client.post(f"/api/approvals/{item}/approve", json={"title": "  Page v1 (final)  "})
    assert r.status_code == 200
    assert db.get_approval(item)["title"] == "Page v1 (final)"
    assert "(title edited)" in queries.recent_events(1)[0]["message"]


def test_blank_title_keeps_original_and_long_title_refused(env):
    client, _, _ = env
    item = _submit()
    assert client.post(f"/api/approvals/{item}/approve", json={"title": "x" * 256}).status_code == 422
    assert db.get_approval(item)["status"] == "pending"
    assert client.post(f"/api/approvals/{item}/approve", json={"title": "   "}).status_code == 200
    assert db.get_approval(item)["title"] == "Page v1"


def test_reject_ignores_title(env):
    client, _, _ = env
    item = _submit()
    assert client.post(f"/api/approvals/{item}/reject", json={"title": "New"}).status_code == 200
    assert db.get_approval(item)["title"] == "Page v1"


def test_approve_without_body(env):
    client, _, _ = env
    item = _submit()
    assert client.post(f"/api/approvals/{item}/approve").status_code == 200
    assert db.get_approval(item)["owner_note"] is None


def test_non_http_links_are_not_clickable(env):
    client, _, _ = env
    _submit(link="javascript:alert(1)")
    item = client.get("/api/approvals").json()["items"][0]
    assert item["link_url"] is None and item["link"] == "javascript:alert(1)"


def test_cross_origin_write_refused(env):
    client, _, _ = env
    item = _submit()
    r = client.post(f"/api/approvals/{item}/approve", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post(f"/api/approvals/{item}/approve", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert db.get_approval(item)["status"] == "pending"


def test_foreign_host_refused(env):
    client, _, _ = env
    assert client.get("/api/state", headers={"Host": "attacker.example"}).status_code == 400


def test_file_endpoint_serves_output_images_only(env):
    client, root, out = env
    (out / "sub").mkdir()
    img = out / "sub" / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    secret = root / "secret.png"
    secret.write_bytes(b"nope")
    (out / "notes.txt").write_text("hi")

    ok = client.get("/api/file", params={"path": str(img)})
    assert ok.status_code == 200 and ok.content.startswith(b"\x89PNG")
    assert client.get("/api/file", params={"path": "output/sub/shot.png"}).status_code == 200

    for bad in (str(secret), "output/../secret.png", "../secret.png",
                str(root / "state.db"), "C:/Windows/win.ini", "/etc/passwd"):
        r = client.get("/api/file", params={"path": bad})
        assert r.status_code in (400, 403, 404), bad
    assert client.get("/api/file", params={"path": str(secret)}).status_code == 403
    assert client.get("/api/file", params={"path": str(out / "notes.txt")}).status_code == 403
    assert client.get("/api/file", params={"path": str(out / "missing.png")}).status_code == 404


def test_index_and_static_served(env):
    client, _, _ = env
    r = client.get("/")
    assert r.status_code == 200 and "<canvas" in r.text
    for path in ("app.js", "station.js", "sprites.js", "style.css", "plugins/ledger.js", "plugins/ledger.css"):
        assert client.get(f"/static/{path}").status_code == 200, path


# ---------------------------------------------------------------- ledger plugin

def test_ledger_summary_and_pnl(env):
    client, _, _ = env
    s = client.get("/api/ledger/summary").json()
    assert s["revenue_cents"] == 0 and s["profit_cents"] == 0 and s["goals_cents"] == []
    ledger.add_entry("sale", 2500, "stripe")
    ledger.add_entry("fee", -300, "stripe")
    s = client.get("/api/ledger/summary").json()
    assert s["revenue_cents"] == 2500 and s["profit_cents"] == 2200 and s["month_profit_cents"] == 2200
    body = client.get("/api/ledger").json()
    assert body["pnl"]["totals"]["net"] == 2200 and len(body["recent"]) == 2
    assert client.get("/api/ledger?month=2026-13").status_code == 400


def test_owner_money_entry(env):
    client, _, _ = env
    r = client.post("/api/ledger", json={"kind": "cost", "amount": "12.50", "platform": "Hosting",
                                         "ref": "inv-1", "note": "domain"})
    assert r.status_code == 200
    e = r.json()["entry"]
    assert e["amount_cents"] == -1250 and e["platform"] == "hosting"
    assert queries.recent_events(1)[0]["agent_id"] == "owner"
    dup = client.post("/api/ledger", json={"kind": "cost", "amount": "12.50", "platform": "hosting", "ref": "inv-1"})
    assert dup.status_code == 409
    for bad in ({"kind": "sale", "amount": True, "platform": "x"},
                {"kind": "sale", "amount": "-3", "platform": "x"},
                {"kind": "gift", "amount": "3", "platform": "x"},
                {"kind": "sale", "amount": "3", "platform": "x", "date": "2999-01-01"}):
        assert client.post("/api/ledger", json=bad).status_code == 422, bad
    r = client.post("/api/ledger", json={"kind": "sale", "amount": "5", "platform": "x"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
