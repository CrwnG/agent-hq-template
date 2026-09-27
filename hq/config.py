"""Non-secret HQ settings.

Read from the process environment first, then from `HQ_*` lines in the project's
`.env`. Only keys that start with `HQ_` are ever read from `.env`, so this module
never loads (or can leak) a secret.

  HQ_PROJECT_NAME   shown in the dashboard title bar        (default: "Agent HQ")
  HQ_PLUGINS        comma list of dashboard plugins          (default: "ledger"; "" = none)
  HQ_PASS_SCORE     CRITIC's bar; `hq.report submit` refuses lower scores (default: 9)
  HQ_GOAL_CENTS     monthly profit goal for the ledger plugin, 0 = no goal bar (default: 0)
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def _dotenv_hq() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line.startswith("HQ_") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.split(" #", 1)[0].strip().strip('"').strip("'")
    return out


def get(key: str, default: str) -> str:
    if not key.startswith("HQ_"):
        raise KeyError("hq.config only reads HQ_* settings")
    if key in os.environ:
        return os.environ[key]
    return _dotenv_hq().get(key, default)


def project_name() -> str:
    return get("HQ_PROJECT_NAME", "Agent HQ") or "Agent HQ"


def plugins() -> list[str]:
    raw = get("HQ_PLUGINS", "ledger")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def pass_score() -> float:
    try:
        return float(get("HQ_PASS_SCORE", "9"))
    except ValueError:
        return 9.0


def goal_cents() -> int:
    try:
        return max(0, int(get("HQ_GOAL_CENTS", "0")))
    except ValueError:
        return 0
