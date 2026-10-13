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
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import VERSION
from .catalog import SUPPORTED, Catalog
from .config import load_options, read_public_options, save_options
from .engine import Engine
from .ha import HA
from .provider import Provider
from .store import Store


class Command(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    request_id: uuid.UUID


class EntityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


class Policy(BaseModel):
    light: bool | None = None
    switch: bool | None = None
    climate: bool | None = None
    domains: dict[str, bool] | None = None
    entities: dict[str, EntityOverride] | None = None
    entity_id: str | None = None
    entity_enabled: StrictBool | None = None


class ConfigUpdate(BaseModel):
    openrouter_api_key: str | None = None
    delete_openrouter_api_key: bool = False
    openrouter_model: str | None = None
    azure_api_key: str | None = None
    delete_azure_api_key: bool = False
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    provider: str | None = None
    rescan_hours: int | None = None
    history_days: int | None = None
    history_limit: int | None = None


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
    app.state.mutation_lock = asyncio.Lock()
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
    management = request.url.path in {
        "/api/config",
        "/api/policy",
        "/api/domains",
        "/api/rescan",
        "/api/history",
    }
    if management and not standalone:
        user_id = request.headers.get("x-remote-user-id", "")
        if not await app.state.ha.is_admin(user_id):
            return JSONResponse({"error": "admin_required"}, status_code=403)
    if request.method not in {"GET", "HEAD"} and request.url.path.startswith("/api/"):
        async with app.state.mutation_lock:
            response = await call_next(request)
    else:
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


@app.get("/api/config")
async def get_config():
    try:
        return (await read_public_options(app.state.provider.options)).public_dict()
    except ValueError:
        raise HTTPException(503, "options_read_failed") from None


@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    if any(not job.done() for job in app.state.tasks):
        raise HTTPException(409, "execution_in_progress")
    try:
        new_options = await save_options(
            body.model_dump(exclude_unset=True), app.state.provider.options
        )
    except Exception as exc:
        raise HTTPException(400, "options_save_failed") from exc
    app.state.ha.rescan_hours = new_options.rescan_hours
    app.state.ha.periodic_wakeup.set()
    app.state.store.days = new_options.history_days
    app.state.store.limit = new_options.history_limit
    app.state.provider.options = new_options
    app.state.provider.status = {name: "configured_unverified" for name in new_options.configured()}
    if new_options.azure_error():
        app.state.provider.status["azure"] = new_options.azure_error()
    return new_options.public_dict()


@app.get("/api/shortcuts")
async def shortcuts():
    return app.state.store.recent_shortcuts(limit=6)


@app.get("/api/domains")
async def domains():
    ha, store = app.state.ha, app.state.store
    store.reconcile_registry(ha)
    policy_dict = store.policy()
    catalog = Catalog(ha, {domain: True for domain in SUPPORTED})
    discovered = {entity_id.split(".", 1)[0] for entity_id in ha.states}
    res = []
    for domain in sorted(discovered | set(SUPPORTED)):
        domain_entities = [
            {
                "entity_id": e.entity_id,
                "name": e.name,
                "area": e.area,
                "enabled": policy_dict.is_allowed(
                    domain,
                    e.entity_id,
                    next((r.get("id") for r in ha.registry if r["entity_id"] == e.entity_id), None),
                ),
            }
            for e in catalog.entities.values()
            if e.domain == domain
        ]
        res.append(
            {
                "domain": domain,
                "label": SUPPORTED.get(domain, domain),
                "supported": domain in SUPPORTED,
                "enabled": policy_dict.is_domain_allowed(domain),
                "count": len(domain_entities),
                "entities": domain_entities,
            }
        )
    return res


@app.get("/api/policy")
async def get_policy():
    return app.state.store.policy()


@app.put("/api/policy")
async def update_policy(body: Policy):
    if any(not job.done() for job in app.state.tasks):
        raise HTTPException(409, "execution_in_progress")

    curr = app.state.store.policy()
    domains = dict(curr.domains)
    entities = dict(curr.entities)

    if body.domains:
        domains.update(body.domains)
    for dom in ["light", "switch", "climate"]:
        val = getattr(body, dom, None)
        if val is not None:
            domains[dom] = val
    if body.entities:
        for eid, override in body.entities.items():
            identity = next(
                (r.get("id") for r in app.state.ha.registry if r["entity_id"] == eid), None
            )
            entities[eid] = {**override.model_dump(), "identity": identity}
    if body.entity_id is not None and body.entity_enabled is not None:
        identity = next(
            (r.get("id") for r in app.state.ha.registry if r["entity_id"] == body.entity_id), None
        )
        entities[body.entity_id] = {"enabled": body.entity_enabled, "identity": identity}

    new_pol = {"domains": domains, "entities": entities}
    app.state.store.set_policy(new_pol)
    return {"ok": True, "policy": new_pol}


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
