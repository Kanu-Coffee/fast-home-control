import asyncio
import contextlib
import hmac
import io
import json
import os
import re
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import VERSION
from .actions import CONTROL_DOMAINS
from .catalog import DEFERRED, SUPPORTED, Catalog
from .config import load_options, read_public_options, save_options
from .engine import Engine
from .ha import HA
from .provider import Provider
from .store import Store

# Model choices are option ids. Official action/enum ids are safe for anonymized
# exports; user-authored option strings, names and message spans are not.
SAFE_CHOICES = frozenset(
    {
        "none",
        "turn_on",
        "turn_off",
        "query_state",
        "press",
        "start",
        "pause",
        "stop",
        "return_to_base",
        "trigger",
        "increment",
        "decrement",
        "reset",
        "set_value",
        "select_option",
        "open_cover",
        "close_cover",
        "stop_cover",
        "media_play",
        "media_pause",
        "media_stop",
        "media_next_track",
        "media_previous_track",
        "volume_set",
        "volume_mute",
        "oscillate_on",
        "oscillate_off",
        "forward",
        "reverse",
        "mute",
        "unmute",
        "next",
        "previous",
        "first",
        "last",
        "apply",
        "dim_down",
        "dim_up",
        "get_events",
        "create_event",
        "get_items",
        "add_item",
        "update_item",
        "remove_item",
        "get_forecasts",
        "set_datetime",
        "send_message",
        "speak",
        "enable_motion_detection",
        "disable_motion_detection",
        "today",
        "tomorrow",
        "day_after",
        "seven_days",
        "completed",
        "needs_action",
        "hourly",
        "daily",
        "twice_daily",
        "gt",
        "gte",
        "lt",
        "lte",
        "°C",
        "°F",
        "%",
        "off",
        "on",
        "heat",
        "cool",
        "heat_cool",
        "dry",
        "fan_only",
        "auto",
        "red",
        "green",
        "blue",
        "yellow",
        "orange",
        "purple",
        "white",
        "pink",
        "cyan",
        "magenta",
        "lime",
        "navy",
    }
)
LITERAL_ID = re.compile(r"^[vtd]\d+$")


def safe_choice(value):
    if isinstance(value, str) and (value in SAFE_CHOICES or LITERAL_ID.match(value)):
        return value
    return None


class Command(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    request_id: uuid.UUID


class EntityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool | None = None
    read_enabled: StrictBool | None = None


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    light: bool | None = None
    switch: bool | None = None
    climate: bool | None = None
    domains: dict[str, StrictBool] | None = None
    read_domains: dict[str, StrictBool] | None = None
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
        "/api/history/export",
    } or request.url.path.startswith("/api/history/")
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

    registry_eids = {r["entity_id"] for r in ha.registry if "entity_id" in r}
    state_eids = set(ha.states.keys())
    all_known_eids = registry_eids | state_eids

    discovered_domains = {eid.split(".", 1)[0] for eid in all_known_eids}
    res = []
    for domain in sorted(discovered_domains | set(SUPPORTED) | set(DEFERRED)):
        domain_eids = {eid for eid in all_known_eids if eid.startswith(f"{domain}.")}
        discovered_count = len(domain_eids)

        domain_entities = [e for e in catalog.entities.values() if e.domain == domain]

        is_supported = domain in SUPPORTED
        is_deferred = domain in DEFERRED
        is_control_domain = domain in CONTROL_DOMAINS

        controllable_entities = [
            e
            for e in domain_entities
            if is_control_domain
            and any(
                s in e.features.get("services", [])
                for s in (
                    "turn_on",
                    "turn_off",
                    "set_temperature",
                    "set_hvac_mode",
                    "start",
                    "press",
                    "set_percentage",
                    "open_cover",
                    "close_cover",
                    "set_cover_position",
                    "set_humidity",
                    "media_play",
                    "volume_set",
                    "set_value",
                    "select_option",
                    "trigger",
                    "send_message",
                    "speak",
                    "create_event",
                    "add_item",
                    "set_datetime",
                )
            )
        ]
        controllable_count = len(controllable_entities)
        # Read capability is independent: controllable entities can also be queried.
        queryable_count = len(domain_entities) if is_supported else 0

        if is_deferred:
            status = "deferred"
            note = DEFERRED[domain]
        elif not is_supported:
            status = "unsupported"
            note = "현재 미지원 도메인입니다."
        elif controllable_count == 0 and queryable_count > 0:
            status = "query_only"
            note = "상태 및 정보 조회만 지원"
        else:
            status = "supported"
            note = "제어 및 자동화 지원"

        is_domain_enabled = policy_dict.is_domain_allowed(domain)
        is_domain_read_enabled = policy_dict.is_domain_allowed(domain, access="read")
        allowed_entities = []
        for e in domain_entities:
            reg_id = next(
                (r.get("id") for r in ha.registry if r.get("entity_id") == e.entity_id), None
            )
            write_ok = policy_dict.is_allowed(domain, e.entity_id, reg_id, access="write")
            read_ok = policy_dict.is_allowed(domain, e.entity_id, reg_id, access="read")
            allowed_entities.append(
                {
                    "entity_id": e.entity_id,
                    "name": e.name,
                    "area": e.area,
                    "enabled": write_ok,
                    "read_enabled": read_ok,
                    "controllable": e in controllable_entities,
                    "queryable": is_supported and read_ok,
                }
            )

        # read/write possible and allowed counts are aggregated independently (FIX_05 R2).
        allowed_control_count = sum(1 for item in allowed_entities if item["enabled"])
        allowed_query_count = sum(1 for item in allowed_entities if item["queryable"])

        res.append(
            {
                "domain": domain,
                "label": SUPPORTED.get(domain) or DEFERRED.get(domain, domain),
                "supported": is_supported,
                "enabled": is_domain_enabled,
                "read_enabled": is_domain_read_enabled,
                "status": status,
                "query_only": status == "query_only",
                "note": note,
                "discovered_count": discovered_count,
                "controllable_count": controllable_count,
                "queryable_count": queryable_count,
                "allowed_control_count": allowed_control_count,
                "allowed_query_count": allowed_query_count,
                "count": len(domain_entities),
                "entities": allowed_entities,
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
    read_domains = dict(curr.read_domains)
    entities = dict(curr.entities)

    if body.domains:
        domains.update(body.domains)
    if body.read_domains:
        read_domains.update(body.read_domains)
    for dom in ["light", "switch", "climate"]:
        val = getattr(body, dom, None)
        if val is not None:
            domains[dom] = val
    known_ids = {r["entity_id"]: r.get("id") for r in app.state.ha.registry if "entity_id" in r}
    if body.entities:
        for eid, override in body.entities.items():
            updates = override.model_dump(exclude_unset=True, exclude_none=True)
            if not updates:
                raise HTTPException(422, "empty_entity_override")
            entry = dict(entities.get(eid, {}))
            entry.setdefault("enabled", True)
            entry.update(updates)
            entry["identity"] = known_ids.get(eid, entry.get("identity"))
            entities[eid] = entry
    if body.entity_id is not None and body.entity_enabled is not None:
        entry = dict(entities.get(body.entity_id, {}))
        entry["enabled"] = body.entity_enabled
        entry["identity"] = known_ids.get(body.entity_id, entry.get("identity"))
        entities[body.entity_id] = entry

    # Atomic full-document write: unrelated sections (read policy) are preserved.
    new_pol = {"domains": domains, "read_domains": read_domains, "entities": entities}
    app.state.store.set_policy(new_pol)
    return {"ok": True, "policy": app.state.store.policy()}


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


def command_summary(record):
    # Full phase/model diagnostics are available only through admin /api/history.
    public = {
        key: value
        for key, value in record.items()
        if key
        in {"id", "text", "status", "reason", "actions", "timings_ms", "created", "model_calls"}
    }
    public["actions"] = [
        {k: v for k, v in action.items() if k not in {"selected", "ref"}}
        for action in record.get("actions", [])
    ]
    return public


@app.post("/api/commands", status_code=202)
async def command(body: Command):
    request_id, text = str(body.request_id), body.text.strip()
    if not text:
        raise HTTPException(422, "empty_command")
    existing = app.state.store.get(request_id)
    if existing:
        if existing[0] != text:
            raise HTTPException(409, "request_id_conflict")
        return command_summary(existing[1])
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
    return command_summary(record)


@app.get("/api/commands/{request_id}")
async def get_command(request_id: uuid.UUID):
    found = app.state.store.get(str(request_id))
    if not found:
        raise HTTPException(404, "request_not_found")
    return command_summary(found[1])


@app.get("/api/history")
async def history():
    return [r for r in app.state.store.recent() if not r.get("hidden")]


@app.delete("/api/history")
async def clear_history():
    if any(not task.done() for task in app.state.tasks):
        raise HTTPException(409, "executor_busy")
    app.state.store.clear_history()
    return {"ok": True}


@app.get("/api/history/export")
async def export_history(
    include_text: bool = False,
    days: int = Query(default=1, ge=1, le=30),
    status: str | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
    request_id: str | None = None,
):
    ha, store = app.state.ha, app.state.store
    cutoff = time.time() - max(1, days) * 86400

    # Build SQL query with filters to avoid LIMIT truncating before filtering
    where_clauses = [
        "created >= ?",
        "(json_extract(result, '$.hidden') IS NULL OR json_extract(result, '$.hidden') != 1)",
    ]
    params = [cutoff]
    if status:
        where_clauses.append("json_extract(result, '$.status') = ?")
        params.append(status)
    if request_id:
        where_clauses.append("id = ?")
        params.append(request_id)
    where_sql = " AND ".join(where_clauses)

    count_row = store.db.execute(
        f"SELECT COUNT(*) FROM requests WHERE {where_sql}", params
    ).fetchone()
    total_matching = count_row[0] if count_row else 0

    query = (
        f"SELECT id, created, result FROM requests WHERE {where_sql} ORDER BY created DESC LIMIT ?"
    )
    rows = store.db.execute(query, (*params, limit)).fetchall()
    truncated = total_matching > len(rows)

    # Extract raw string secret values (handles SecretStr properly)
    options = getattr(app.state.provider, "options", None)
    known_secrets = set()
    if options:
        opt_or = getattr(options, "openrouter_api_key", None)
        if opt_or:
            val = opt_or.get_secret_value() if hasattr(opt_or, "get_secret_value") else str(opt_or)
            if val:
                known_secrets.add(val)
        opt_az = getattr(options, "azure_api_key", None)
        if opt_az:
            val = opt_az.get_secret_value() if hasattr(opt_az, "get_secret_value") else str(opt_az)
            if val:
                known_secrets.add(val)
    for env_var in (
        "SUPERVISOR_TOKEN",
        "FHC_STANDALONE_TOKEN",
        "OPENROUTER_API_KEY",
        "AZURE_API_KEY",
    ):
        val = os.environ.get(env_var)
        if val:
            known_secrets.add(val)

    entity_map = {}
    name_map = {}
    area_map = {}
    choice_map = {}

    def mask_secret_strings(s: str) -> str:
        if not isinstance(s, str):
            return str(s)
        res = s
        for sec in known_secrets:
            if sec and sec in res:
                res = res.replace(sec, "[REDACTED_SECRET]")
        return res

    def sanitize_action(a: dict) -> dict:
        ent_id = a.get("entity_id", "")
        raw_name = a.get("name", "")
        raw_area = a.get("area", "")

        out = {
            "domain": a.get("domain", ""),
            "service": a.get("service", ""),
            "status": a.get("status", "unknown"),
            "entity_id": mask_secret_strings(ent_id)
            if include_text
            else entity_map.setdefault(ent_id, f"anon_entity_{len(entity_map) + 1}"),
            "name": mask_secret_strings(raw_name)
            if include_text
            else name_map.setdefault(raw_name, f"device_{len(name_map) + 1}"),
            "area": mask_secret_strings(raw_area)
            if include_text
            else area_map.setdefault(raw_area, f"area_{len(area_map) + 1}"),
        }
        if "ha_ack_ms" in a:
            out["ha_ack_ms"] = a["ha_ack_ms"]
        if "context_id" in a:
            out["context_id"] = a["context_id"]
        if a.get("is_query"):
            out["is_query"] = True

        raw_data = a.get("service_data") or {}
        clean_data = {}
        for k, v in raw_data.items():
            k_lower = k.lower()
            if any(
                sec_k in k_lower
                for sec_k in ("key", "token", "password", "secret", "auth", "session", "cookie")
            ):
                clean_data[k] = "[REDACTED_SECRET]"
            elif k_lower in (
                "temperature",
                "brightness_pct",
                "brightness_step_pct",
                "percentage",
                "position",
                "humidity",
                "hvac_mode",
                "fan_mode",
                "volume_level",
                "is_volume_muted",
                "skip_condition",
                "stop_actions",
            ):
                clean_data[k] = v
            elif k_lower in ("value", "message", "text"):
                clean_data[k] = mask_secret_strings(str(v)) if include_text else "[REDACTED_VALUE]"
            else:
                clean_data[k] = mask_secret_strings(str(v)) if include_text else "[REDACTED]"
        if clean_data:
            out["service_data"] = clean_data
        return out

    def build_diagnostic_dto(rec: dict) -> dict:
        dto = {
            "id": rec.get("id"),
            "created": rec.get("created"),
            "status": rec.get("status"),
            "reason": rec.get("reason"),
            "phase": rec.get("phase"),
            "timings_ms": rec.get("timings_ms", {}),
            "providers": rec.get("providers", []),
            "model": rec.get("model"),
            "model_calls": rec.get("model_calls", 0),
        }
        if "verification_score" in rec:
            dto["verification_score"] = rec["verification_score"]
        if "condition_result" in rec:
            dto["condition_result"] = rec["condition_result"]
        if "condition_evaluation" in rec and isinstance(rec["condition_evaluation"], dict):
            c_diag = rec["condition_evaluation"]
            dto["condition_evaluation"] = {
                "sensor_id": mask_secret_strings(c_diag.get("entity_id", ""))
                if include_text
                else entity_map.setdefault(
                    c_diag.get("entity_id", ""), f"anon_entity_{len(entity_map) + 1}"
                ),
                "sensor_name": mask_secret_strings(c_diag.get("sensor_name", ""))
                if include_text
                else name_map.setdefault(
                    c_diag.get("sensor_name", ""), f"device_{len(name_map) + 1}"
                ),
                "raw_value": c_diag.get("raw_value"),
                "sensor_unit": c_diag.get("sensor_unit"),
                "observed_value": c_diag.get("observed_value"),
                "observed_unit": c_diag.get("observed_unit"),
                "target_value": c_diag.get("target_value"),
                "target_unit": c_diag.get("target_unit"),
                "operator": c_diag.get("operator"),
                "result": c_diag.get("result"),
            }
        if "decisions" in rec and isinstance(rec["decisions"], dict):
            clean_d = {}
            for k, v in rec["decisions"].items():
                if not isinstance(v, dict):
                    continue
                chosen = v.get("choice")
                if not include_text:
                    safe = safe_choice(chosen)
                    if safe is None:
                        safe = (
                            str(chosen)
                            if not isinstance(chosen, str)
                            else choice_map.setdefault(chosen, f"anon_choice_{len(choice_map) + 1}")
                        )
                    chosen = safe
                clean_d[k] = {
                    "choice": chosen,
                    "probability": round(v.get("probability", 0), 3)
                    if isinstance(v.get("probability"), (int, float))
                    else None,
                }
            dto["decisions"] = clean_d
        if "model_trace" in rec and isinstance(rec["model_trace"], list):
            dto["model_trace"] = [
                {
                    "provider": tr.get("provider"),
                    "requested_model": tr.get("requested_model"),
                    "returned_model": tr.get("returned_model"),
                    "error": tr.get("error"),
                    "http_code": tr.get("http_code"),
                }
                for tr in rec["model_trace"]
                if isinstance(tr, dict)
            ]
        if include_text:
            dto["text"] = mask_secret_strings(rec.get("text", ""))
        else:
            dto["text"] = "[REDACTED_COMMAND]"

        dto["actions"] = [sanitize_action(a) for a in rec.get("actions", [])]

        if "query_results" in rec:
            clean_q = []
            for q in rec.get("query_results", []):
                eid = q.get("entity_id", "")
                q_name = q.get("name", "")
                st_val = q.get("state")
                # Classification is mode/feature based (at record time), never ID substrings.
                classified = q.get("sensitive")
                current = ha.states.get(eid)
                mode_sensitive = bool(
                    isinstance(current, dict)
                    and str(eid).split(".", 1)[0] == "input_text"
                    and (current.get("attributes") or {}).get("mode") == "password"
                )
                conservative = classified is None or current is None
                safe_state = (
                    "[REDACTED_SENSITIVE]"
                    if classified is True or mode_sensitive
                    else (
                        st_val
                        if isinstance(st_val, (int, float))
                        or (
                            isinstance(st_val, str)
                            and st_val
                            in {
                                "on",
                                "off",
                                "open",
                                "closed",
                                "docked",
                                "cleaning",
                                "idle",
                                "paused",
                                "unknown",
                            }
                        )
                        else "[REDACTED_STATE]"
                    )
                )
                if classified is True or mode_sensitive:
                    state_out = "[REDACTED_SENSITIVE]"
                elif include_text and conservative:
                    # Unclassified or deleted-entity history is excluded conservatively.
                    state_out = "[UNCLASSIFIED_STATE_EXCLUDED]"
                elif include_text:
                    state_out = mask_secret_strings(str(st_val))
                else:
                    state_out = safe_state
                clean_q.append(
                    {
                        "entity_id": mask_secret_strings(eid)
                        if include_text
                        else entity_map.setdefault(eid, f"anon_entity_{len(entity_map) + 1}"),
                        "name": mask_secret_strings(q_name)
                        if include_text
                        else name_map.setdefault(q_name, f"device_{len(name_map) + 1}"),
                        "unit": q.get("unit"),
                        "classified": classified if classified is not None else "absent",
                        "state": state_out,
                    }
                )
            dto["query_results"] = clean_q
        return dto

    exported_records = []
    status_counts = {}
    timing_sums = {}
    timing_counts = {}
    providers = set()

    for _rid, _created, raw in rows:
        try:
            item = json.loads(raw)
        except Exception:
            continue
        if item.get("hidden"):
            continue

        st = item.get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
        for p in item.get("providers", []):
            providers.add(p)
        for t_k, t_v in item.get("timings_ms", {}).items():
            if isinstance(t_v, (int, float)):
                timing_sums[t_k] = timing_sums.get(t_k, 0) + t_v
                timing_counts[t_k] = timing_counts.get(t_k, 0) + 1

        dto = build_diagnostic_dto(item)
        exported_records.append(dto)

    avg_timings = {
        k: round(timing_sums[k] / timing_counts[k], 1)
        for k in timing_sums
        if timing_counts.get(k, 0) > 0
    }

    utc_now = datetime.now(timezone.utc)
    utc_str = utc_now.strftime("%Y%m%dT%H%M%SZ")

    manifest = {
        "export_schema_version": "1.1",
        "app_version": VERSION,
        "ha_version": getattr(ha, "version", None),
        "created_at": utc_now.isoformat(),
        "timezone": "UTC",
        "include_text": include_text,
        "requested_range_days": days,
        "status_filter": status,
        "request_id_filter": request_id,
        "records_count": len(exported_records),
        "total_matching": total_matching,
        "truncated": truncated,
    }

    summary = {
        "total_records": len(exported_records),
        "status_counts": status_counts,
        "average_timings_ms": avg_timings,
        "providers_used": list(providers),
    }

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("summary.json", json.dumps(summary, indent=2, ensure_ascii=False))
        requests_jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in exported_records)
        zf.writestr("requests.jsonl", requests_jsonl)

    filename = f"fhc-diagnostics-{VERSION}-{utc_str}.zip"
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


app.mount("/static", StaticFiles(directory=STATIC), name="static")
