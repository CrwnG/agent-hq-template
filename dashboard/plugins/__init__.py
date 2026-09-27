"""Optional dashboard plugins.

A plugin is a module in this package that exposes:

  router    a fastapi.APIRouter with its /api/<name>/... routes
  SCRIPTS   static JS files (under dashboard/static/) the page should load
  STYLES    static CSS files (under dashboard/static/) the page should load

Enable plugins with HQ_PLUGINS in .env (comma-separated; default "ledger";
empty = none). The page learns which ones are on from /api/state and loads
their assets; the core dashboard never depends on a plugin.

To add one: copy ledger.py's shape, put its JS/CSS in dashboard/static/plugins/,
and add its name to HQ_PLUGINS. Frontend hooks: see HQ in dashboard/static/app.js.
"""
from __future__ import annotations

import importlib
from types import ModuleType

AVAILABLE = ("ledger",)


def load(names: list[str]) -> list[ModuleType]:
    mods = []
    for name in names:
        if name not in AVAILABLE:
            raise ValueError(f"unknown dashboard plugin {name!r}; available: {AVAILABLE}")
        mods.append(importlib.import_module(f"{__name__}.{name}"))
    return mods
