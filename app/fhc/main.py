import asyncio
import contextlib
import hmac
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import VERSION
from .catalog import SUPPORTED, Catalog
from .config import load_options
from .engine import Engine
from .ha import HA
from .provider import Provider
from .store import Store


class Command(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    request_id: uuid.UUID


class Policy(BaseModel):
    light: bool
    switch: bool


@asynccontextmanager
async def lifespan(app):
    options = load_options()
    store = Store(
        Path(os.environ.get("FHC_DATA_DIR", "/data")), options.history_days, options.history_limit
    )
    ha, provider = HA(options.rescan_hours), Provider(options)
    app.state.ha, app.state.provider, app.state.store = ha, provider, store
    app.state.engine = Engine(ha, provider, store)
    app.state.tasks = set()
    task = asyncio.create_task(ha.run())
    try:
        yield
    finally:
        task.cancel()
        jobs = list(app.state.tasks)
        for job in jobs:
            job.cancel()
        for job in [task, *jobs]:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await job
        await ha.close()
        await provider.close()
        store.close()


app = FastAPI(
    title="Fast Home Control", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
)
STATIC = Path(__file__).parent / "static"


@app.middleware("http")
async def access_control(request: Request, call_next):
    if request.url.path == "/healthz":
        return JSONResponse({"running": True})
    standalone = os.environ.get("FHC_STANDALONE_TOKEN", "")
    if standalone:
        allowed = hmac.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {standalone}"
        )
        # Browser uses a session cookie set by an authenticated bootstrap POST.
        allowed = allowed or hmac.compare_digest(request.cookies.get("fhc_session", ""), standalone)
    else:
        allowed = request.client is not None and request.client.host == "172.30.32.2"
    if not allowed:
        return JSONResponse({"error": "access_denied"}, status_code=403)
    if request.method not in {"GET", "HEAD"}:
        if (
            request.headers.get("x-fhc-request") != "1"
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            return JSONResponse({"error": "request_origin_rejected"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.post("/api/dev-session")
async def dev_session():
    token = os.environ.get("FHC_STANDALONE_TOKEN")
    if not token:
        raise HTTPException(404)
    response = JSONResponse({"ok": True})
    response.set_cookie("fhc_session", token, httponly=True, samesite="strict", max_age=3600)
    return response


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
async def status():
    ha, provider = app.state.ha, app.state.provider
    return {
        "version": VERSION,
        "ha_ready": ha.ready,
        "ha_error": ha.error,
        "last_sync": ha.last_sync,
        "catalog_version": ha.version,
        "entities": len(ha.states),
        "providers": provider.status,
        "configured_providers": provider.options.configured(),
        "supported_domains": list(SUPPORTED),
        "execution_ready": ha.ready and bool(provider.options.configured()),
    }


@app.get("/api/domains")
async def domains():
    ha, store = app.state.ha, app.state.store
    policy = store.policy()
    catalog = Catalog(ha, {domain: True for domain in SUPPORTED})
    discovered = {entity_id.split(".", 1)[0] for entity_id in ha.states}
    return [
        {
            "domain": domain,
            "label": SUPPORTED.get(domain, domain),
            "supported": domain in SUPPORTED,
            "enabled": policy.get(domain, False),
            "count": sum(e.domain == domain for e in catalog.entities.values()),
        }
        for domain in sorted(discovered | set(SUPPORTED))
    ]


@app.put("/api/policy")
async def policy(body: Policy):
    if any(
        app.state.store.get(job.get_name())[1]["status"] == "executing"
        for job in app.state.tasks
        if not job.done()
    ):
        raise HTTPException(409, "execution_in_progress")
    app.state.store.set_policy(body.model_dump())
    return {"ok": True}


@app.post("/api/rescan")
async def rescan():
    if app.state.ha.ws is None:
        raise HTTPException(503, "ha_not_connected")
    if app.state.ha.sync_lock.locked():
        raise HTTPException(409, "sync_in_progress")
    try:
        await app.state.ha.rescan()
    except Exception as exc:
        raise HTTPException(503, "sync_failed") from exc
    return {"ok": app.state.ha.ready}


@app.post("/api/commands", status_code=202)
async def command(body: Command):
    request_id, text = str(body.request_id), body.text.strip()
    if not text:
        raise HTTPException(422, "empty_command")
    existing = app.state.store.get(request_id)
    if existing:
        if existing[0] != text:
            raise HTTPException(409, "request_id_conflict")
        return existing[1]
    if any(not task.done() for task in app.state.tasks):
        raise HTTPException(409, "executor_busy")
    if not app.state.ha.ready:
        raise HTTPException(503, "ha_not_ready")
    if not app.state.provider.options.configured():
        raise HTTPException(503, "provider_not_configured")
    record = app.state.store.insert(request_id, text)
    task = asyncio.create_task(app.state.engine.run(request_id, text), name=request_id)
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return record


@app.get("/api/commands/{request_id}")
async def get_command(request_id: uuid.UUID):
    found = app.state.store.get(str(request_id))
    if not found:
        raise HTTPException(404, "request_not_found")
    return found[1]


@app.get("/api/history")
async def history():
    return [r for r in app.state.store.recent() if not r.get("hidden")]


@app.delete("/api/history")
async def clear_history():
    if any(not task.done() for task in app.state.tasks):
        raise HTTPException(409, "executor_busy")
    app.state.store.clear_history()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
