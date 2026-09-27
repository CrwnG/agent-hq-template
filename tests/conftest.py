"""Every test runs against a temp HQ: its own state.db, crew.json copy and no .env."""
import shutil

import pytest

from hq import config, db


@pytest.fixture(autouse=True)
def isolated_hq(tmp_path, monkeypatch):
    crew = tmp_path / "crew.json"
    shutil.copy(db.CREW_FILE, crew)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "state.db")
    monkeypatch.setattr(db, "CREW_FILE", crew)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")
    for key in ("HQ_PROJECT_NAME", "HQ_PLUGINS", "HQ_PASS_SCORE", "HQ_GOAL_CENTS"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path
