"""HQ dashboard server.

  .venv\\Scripts\\python.exe -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8787

Local only. Reads hq/state.db through hq.db / dashboard.queries. The only core
writes are the owner's approve/reject decisions; plugins (HQ_PLUGINS) may add
their own routes, e.g. the ledger plugin's manual money entry.

Safety: the Host header must be local (DNS-rebinding guard), and every
non-GET request from another site is refused (a random web page can't approve
anything on your behalf). /api/file only serves images inside output/.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from hq import config, db
from dashboard import plugins as plugin_pkg
from dashboard import queries

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
STATIC_DIR = Path(__file__).resolve().parent / "static"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


# ---------------------------------------------------------------- files

def resolve_output_file(raw: str) -> Path:
    """Map a stored path to a real image file inside OUTPUT_DIR, or raise."""
    if not raw or "\x00" in raw:
        raise HTTPException(400, "bad path")
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    try:
        p = p.resolve()
        out = OUTPUT_DIR.resolve()
    except OSError:
        raise HTTPException(400, "bad path")
    if not p.is_relative_to(out):
        raise HTTPException(403, "path outside output/")
    if p.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(403, "not an image")
    if not p.is_file():
        raise HTTPException(404, "file not found")
    return p


def file_url(raw: str | None) -> str | None:
    if not raw or Path(raw).suffix.lower() not in IMAGE_SUFFIXES:
        return None
    return f"/api/file?path={quote(raw, safe='')}"


def safe_link(raw: str | None) -> str | None:
    """Only http(s) links become clickable; anything else is shown as text."""
    if raw and urlsplit(raw).scheme in ("http", "https"):
        return raw
    return None


# ---------------------------------------------------------------- core routes

core = APIRouter()


@core.get("/api/file")
def get_file(path: str = Query(...)):
    return FileResponse(resolve_output_file(path))


@core.get("/api/agents/{agent_id}")
def get_agent(agent_id: str):
    agent = queries.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "unknown agent")
    return {"agent": agent, "events": queries.recent_events(30, agent_id=agent_id)}


@core.get("/api/approvals")
def get_approvals(status: str = Query(default="pending")):
    if status not in db.APPROVAL_STATUSES:
        raise HTTPException(400, f"status must be one of {db.APPROVAL_STATUSES}")
    items = db.list_approvals(status)
    for it in items:
        it["image_url"] = file_url(it.get("file_path"))
        it["link_url"] = safe_link(it.get("link"))
    return {"items": items, "pass_score": config.pass_score()}


class ReviewBody(BaseModel):
    note: str = Field(default="", max_length=2000)


class ApproveBody(ReviewBody):
    title: str | None = Field(default=None, max_length=255)  # owner's edited title


def _decide(item_id: int, approve: bool, body: ApproveBody | ReviewBody | None) -> dict:
    note = body.note if body else ""
    title = getattr(body, "title", None) if (body and approve) else None
    item, changed = db.decide_approval(item_id, approve, note, title)
    if item is None:
        raise HTTPException(404, "unknown approval item")
    if not changed:
        raise HTTPException(409, f"item is '{item['status']}', not pending")
    return item


@core.post("/api/approvals/{item_id}/approve")
def approve_item(item_id: int, body: ApproveBody | None = None):
    return _decide(item_id, True, body)


@core.post("/api/approvals/{item_id}/reject")
def reject_item(item_id: int, body: ReviewBody | None = None):
    return _decide(item_id, False, body)


# ---------------------------------------------------------------- app factory

def create_app(plugin_names: list[str] | None = None) -> FastAPI:
    names = config.plugins() if plugin_names is None else plugin_names
    mods = plugin_pkg.load(names)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        db.init_db()  # idempotent: creates tables / registers the crew
        yield

    app = FastAPI(title=config.project_name(), lifespan=lifespan, docs_url=None, redoc_url=None)
    # Refuse requests whose Host isn't local (DNS-rebinding guard). "testserver" = TestClient.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*LOCAL_HOSTS, "testserver"])

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        """Block cross-site writes: an Origin that isn't local, or a browser saying cross-site."""
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
                return JSONResponse({"detail": "cross-origin write refused"}, status_code=403)
            if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
                return JSONResponse({"detail": "cross-site write refused"}, status_code=403)
        return await call_next(request)

    app.include_router(core)
    for m in mods:
        app.include_router(m.router)
    plugin_info = [{"name": m.NAME, "scripts": [f"/static/{s}" for s in m.SCRIPTS],
                    "styles": [f"/static/{s}" for s in m.STYLES]} for m in mods]

    @app.get("/api/state")
    def get_state():
        agents = queries.list_agents()
        return {
            "server_time": db.now(),
            "project": config.project_name(),
            "agents": agents,
            "working_count": sum(1 for a in agents if a["status"] == "working"),
            "counts": {"approvals": queries.approval_counts()},
            "events": queries.recent_events(50),
            "plugins": plugin_info,
        }

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
