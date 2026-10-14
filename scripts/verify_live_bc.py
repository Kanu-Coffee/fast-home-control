"""FIX_06 live B/C verification against the disposable HAOS fixture only.

Three distinct outcome layers, never conflated (FIX_06 R5):
  * e2e_model        — real model selection from the Korean command through the effect.
  * service_contract — scripted-mock selections (labeled as mock) driving REAL HA
                       services; asserts payload schema and read-back values.
                       If a service never executed the state is not_exercised and
                       is never counted as a pass.
  * safety_negative  — ambiguity/unsupported cases that must produce 0 control sends.

Real-model failures stay recorded as failures; safety thresholds are never lowered.
Secrets are never printed or stored. See docs/testing.md.
"""

import argparse
import asyncio
import contextlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fhc.config import load_options
from fhc.engine import Engine
from fhc.ha import HA
from fhc.provider import Provider
from fhc.store import Store

BASE = "http://127.0.0.1:18180"
ALLOWED = {"microsoft/microsoft-decision-1", "typesafe/jev-1.13"}
# Fixture clarity: the demo ships eight English media_players that are not in the
# entity registry (cannot be renamed). Keep ONE candidate speaker for TTS routing
# tests and exclude the rest by entity policy — an app/fixture config, not user
# manual mapping.
TTS_KEEP_MP = "media_player.bedroom"

LIVE_DOMAINS = [
    "light",
    "switch",
    "climate",
    "media_player",
    "tts",
    "weather",
    "calendar",
    "todo",
    "sensor",
    "input_datetime",
]


def sent(result):
    return [a for a in result["actions"] if a["status"] in {"sent", "uncertain"}]


def queried(result):
    return [a for a in result["actions"] if a["status"] == "query_succeeded"]


class ScriptedMock:
    """Mock model with prescribed picks over real HA services. Explicitly labeled."""

    def __init__(self):
        self.picks = {}
        self.calls = 0
        self.trace = []

    async def decide(self, state, questions):
        self.calls += 1
        answers = {}
        for key, q in questions.items():
            if q["type"] == "noul":
                answers[key] = {"type": "noul", "noul": 0.99}
                continue
            criteria = q["criteria"]
            prop = key.split("_", 1)[1] if "_" in key else key
            want = self.picks.get(prop)
            selected = "none"
            if want is not None:
                if want in criteria:
                    selected = want
                else:
                    hits = [k for k, v in criteria.items() if isinstance(v, str) and str(want) in v]
                    if len(hits) == 1:
                        selected = hits[0]
            probs = {
                name: (0.97 if name == selected else 0.03 / max(1, len(criteria) - 1))
                for name in criteria
            }
            answers[key] = {"type": "choice", "choice": selected, "probabilities": probs}
        return answers, "scripted_mock_labeled"


async def engine_case(ha, provider, store, text):
    rid = str(uuid.uuid4())
    store.insert(rid, text)
    await Engine(ha, provider, store).run(rid, text)
    return store.get(rid)[1]


async def read_service(ha, domain, service, entity_id, data):
    resp = await ha.call(domain, service, entity_id, service_data=data, return_response=True)
    val = resp.get("response", resp) if isinstance(resp, dict) else resp
    if isinstance(val, dict) and entity_id in val:
        val = val[entity_id]
    return val


async def prep_fixture(ha):
    notes = []
    # Deterministic A-path seed: living-room lights ON, 거실 에어컨 cooled to 20.
    with contextlib.suppress(Exception):
        await ha.call("light", "turn_on", "light.ceiling_lights")
        await ha.call("light", "turn_on", "light.living_room_rgbww_lights")
        await ha.call("climate", "set_temperature", "climate.hvac", {"temperature": 20})
    items = await read_service(
        ha, "todo", "get_items", "todo.shopping_list", {"status": ["needs_action", "completed"]}
    )
    for x in (items or {}).get("items", []):
        if str(x.get("summary", "")).startswith("FHC"):
            await ha.call(
                "todo", "remove_item", "todo.shopping_list", service_data={"item": x["uid"]}
            )
    await ha.call("todo", "add_item", "todo.shopping_list", service_data={"item": "FHC 우유"})
    await ha.call("todo", "add_item", "todo.shopping_list", service_data={"item": "FHC 우유"})
    notes.append("duplicate-name todo pair seeded for ambiguity proof")
    idt = next((eid for eid in ha.states if eid.startswith("input_datetime.")), None)
    notes.append(f"input_datetime helper: {idt or 'absent'}")
    cal = next(
        (
            eid
            for eid, st in ha.states.items()
            if eid.startswith("calendar.")
            and "FHC" in str((st.get("attributes") or {}).get("friendly_name", ""))
        ),
        None,
    )
    notes.append(f"writable FHC calendar: {cal or 'absent'}")
    return idt, cal, notes


async def recreate_calendar(ha):
    """Owner-fixture hygiene: delete+recreate the local_calendar entry so runs
    accumulate nothing (get_events payloads carry no uid for per-event deletes)."""
    import httpx

    token = os.environ["FHC_HA_TOKEN"]
    base = BASE + "/api"
    async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
        h = {"Authorization": f"Bearer {token}"}
        entries = (await c.get(base + "/config/config_entries/entry", headers=h)).json()
        for e in entries:
            if e.get("domain") == "local_calendar":
                await c.delete(base + f"/config/config_entries/entry/{e['entry_id']}", headers=h)
        fr = (
            await c.post(
                base + "/config/config_entries/flow", headers=h, json={"handler": "local_calendar"}
            )
        ).json()
        fid = fr["flow_id"]
        done = (
            await c.post(
                base + f"/config/config_entries/flow/{fid}",
                headers=h,
                json={"calendar_name": "FHC 로컬 일정", "import": "create_empty"},
            )
        ).json()
        if done.get("type") != "create_entry":
            raise RuntimeError(f"calendar recreate failed: {done.get('type')}")
        await asyncio.sleep(0.5)
    cal = next(
        (
            eid
            for eid, st in ha.states.items()
            if eid.startswith("calendar.")
            and "FHC" in str((st.get("attributes") or {}).get("friendly_name", ""))
        ),
        None,
    )
    return cal


async def run_scripted(ha, store, out, fixture_notes, fhc_cal, idt):
    mock = ScriptedMock()
    evidence = []

    async def case(name, picks, text, layer, check, extra=None):
        mock.picks = dict(picks)
        r = await engine_case(ha, mock, store, text)
        executed, ok, detail = check(r)
        entry = {
            "case": name,
            "layer": layer,
            "model": "scripted-mock (real HA services underneath)",
            "status": r["status"],
            "reason": r.get("reason"),
            "executed": executed,
            "pass": ok if executed or layer == "safety_negative" else "not_exercised",
            "detail": detail,
        }
        if extra:
            entry.update(extra)
        evidence.append(entry)
        print(f"[scripted/{layer}] {name}: pass={entry['pass']} {r['status']}/{r.get('reason')}")
        return r

    # calendar create (start+end) then read back the real event via get_events.
    await case(
        "calendar_create_typed_window",
        {
            "calendar_action": "create_event",
            "calendar_day": "tomorrow",
            "calendar_time": "14:30",
            "calendar_end_time": "16:00",
        },
        "내일 14:30부터 16시까지 'FHC 회의'라고 일정 만들어줘",
        "service_contract",
        lambda r: (
            any(a["service"] == "create_event" and a["status"] == "sent" for a in r["actions"]),
            any(
                a["service"] == "create_event"
                and a["service_data"].get("end_date_time")
                and not a["service_data"].get("duration")
                and a["status"] == "sent"
                for a in r["actions"]
            ),
            [a["service_data"] for a in r["actions"] if a["service"] == "create_event"],
        ),
    )

    tz = ZoneInfo(ha.time_zone or "UTC")
    tomorrow = (datetime.now(tz) + timedelta(days=1)).date()
    rb = await read_service(
        ha,
        "calendar",
        "get_events",
        fhc_cal,
        {
            "start_date_time": f"{tomorrow}T00:00:00+09:00",
            "end_date_time": f"{tomorrow + timedelta(days=1)}T00:00:00+09:00",
        },
    )
    summaries = [ev.get("summary") for ev in (rb or {}).get("events", [])]
    evidence.append(
        {
            "case": "calendar_readback",
            "layer": "service_contract",
            "model": "direct-service",
            "executed": True,
            "pass": "FHC 회의" in summaries,
            "summaries": summaries[:10],
        }
    )
    print(f"[scripted] calendar_readback: FHC 회의 in {summaries[:10]}")

    # get_events with a non-empty real list must show the title (FIX_06 R1 shape).
    await case(
        "calendar_events_nonempty_display",
        {"calendar_action": "get_events", "calendar_range": "tomorrow"},
        "내일 일정 알려줘",
        "service_contract",
        lambda r: (
            bool(queried(r)),
            any(
                a.get("response_contract") == "ok" and "FHC 회의" in (a.get("query_result") or "")
                for a in queried(r)
            ),
            [(a.get("response_contract"), (a.get("query_result") or "")[:160]) for a in queried(r)],
        ),
    )

    # weather: real forecast response, discovered daily type only.
    await case(
        "weather_forecast_daily",
        {"weather_action": "get_forecasts_daily"},
        "날씨 예보 알려줘",
        "service_contract",
        lambda r: (
            bool(queried(r)),
            any(
                a["service_data"].get("type") == "daily"
                and a.get("response_contract") in {"ok", "empty"}
                for a in queried(r)
            ),
            [(a.get("response_contract"), (a.get("query_result") or "")[:160]) for a in queried(r)],
        ),
    )

    # TTS: schema-valid payload with the SELECTED output target reaches real HA.
    await case(
        "tts_speak_target_payload",
        {"text_action": "apply", "broadcast_output": "output"},
        "침실 스피커로 'FHC 테스트'라고 방송해",
        "service_contract",
        lambda r: (
            bool(sent(r)),
            any(
                a["service"] == "speak"
                and a["service_data"].get("media_player_entity_id") == "media_player.bedroom"
                for a in sent(r)
            ),
            [a["service_data"] for a in sent(r)],
        ),
    )

    # todo: duplicate names must be refused BEFORE any write (preflight).
    await case(
        "todo_duplicate_refused_before_write",
        {"todo_action": "update_item", "todo_status": "completed", "power": "turn_off"},
        "거실불 끄고 장보기 목록에서 'FHC 우유' 완료로 바꿔줘",
        "safety_negative",
        lambda r: (
            bool(sent(r)),
            r["status"] == "rejected" and r.get("reason") == "todo_item_ambiguous" and not sent(r),
            [(a["domain"], a["service"], a["status"]) for a in r["actions"]],
        ),
    )

    # input_datetime if a helper exists: real value write + read-back.
    if idt:
        await case(
            "input_datetime_value",
            {"datetime_action": "set_datetime", "datetime_time_value": "20:30"},
            "기상 시각을 오후 8시 30분으로 설정해줘",
            "service_contract",
            lambda r: (bool(sent(r)), bool(sent(r)), None),
        )
        st = await ha.fresh_state(idt)
        evidence.append(
            {
                "case": "input_datetime_readback",
                "layer": "service_contract",
                "executed": True,
                "pass": st.get("state") == "20:30:00",
                "state": st.get("state"),
            }
        )
    else:
        evidence.append(
            {
                "case": "input_datetime_value",
                "layer": "service_contract",
                "executed": False,
                "pass": "not_exercised",
                "note": "fixture has no input_datetime helper; creating one needs the HA UI/"
                "config flow, which this harness must not fake as a pass",
            }
        )

    # B regression: climate value reaches the device.
    await case(
        "climate_set_temperature_24",
        {"temperature": "24"},
        "거실 에어컨 24도로",
        "service_contract",
        lambda r: (
            bool(sent(r)) or any(a["status"] == "already_in_state" for a in r["actions"]),
            any(a["service"] == "set_temperature" for a in sent(r))
            or any(a["status"] == "already_in_state" for a in r["actions"]),
            [a["service_data"] for a in sent(r)],
        ),
    )
    st = await ha.fresh_state("climate.hvac")
    evidence[-1]["readback_temperature"] = st.get("attributes", {}).get("temperature")
    evidence[-1]["pass"] = bool(
        evidence[-1]["pass"] and st.get("attributes", {}).get("temperature") == 24
    )

    await asyncio.to_thread(
        out.write_text,
        json.dumps(
            {
                "model": "scripted-mock",
                "mode": "scripted",
                "fixture_notes": fixture_notes,
                "cases": evidence,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return evidence


def e2e_cases():
    return [
        (
            "A_light_off",
            "거실불 꺼줘",
            lambda r: any(
                a["service"] == "turn_off" and a["status"] == "sent" for a in r["actions"]
            ),
        ),
        (
            "R5_condition_false",
            "밖에 온도가 20도 이상이면 천장등 꺼줘",
            lambda r: (
                (r.get("condition_evaluation") or {}).get("selection") == "model_typed"
                and r.get("condition_result") is False
                and r.get("reason") == "condition_not_met"
                and not sent(r)
            ),
        ),
        (
            "R3_tts_named_output",
            "Bedroom 스피커로 'FHC 테스트'라고 방송해줘",
            lambda r: any(
                a["service"] == "speak"
                and a["service_data"].get("media_player_entity_id") == "media_player.bedroom"
                for a in sent(r)
            ),
        ),
        (
            "R3_tts_ambiguous_zero",
            "'FHC 테스트'라고 방송해줘",
            lambda r: r["status"] == "rejected" and not sent(r),
        ),
        (
            "R4_calendar_tomorrow",
            "내일 일정 알려줘",
            lambda r: any(
                a["service"] == "get_events"
                and a["status"] == "query_succeeded"
                and a.get("response_contract") in {"ok", "empty"}
                for a in r["actions"]
            ),
        ),
        (
            "R4_weather_forecast",
            "일별 날씨 예보 알려줘",
            lambda r: any(
                a["service"] == "get_forecasts"
                and a["service_data"].get("type") == "daily"
                and a["status"] == "query_succeeded"
                for a in r["actions"]
            ),
        ),
        (
            "R4_todo_not_found_zero",
            "장보기 목록에서 'FHC 없는 항목' 완료로 바꿔줘",
            lambda r: r.get("reason") == "todo_item_not_found" and not sent(r),
        ),
        (
            "B_climate_value",
            "거실 에어컨 24도로 맞춰줘",
            lambda r: (
                any(
                    a["service"] == "set_temperature" and a["service_data"].get("temperature") == 24
                    for a in sent(r)
                )
                or any(a["status"] == "already_in_state" for a in r["actions"])
            ),
        ),
    ]


async def run_model(ha, provider, store, out, model_name, fixture_notes):
    evidence = []
    for name, text, check in e2e_cases():
        r = await engine_case(ha, provider, store, text)
        executed = (
            bool(sent(r))
            or bool(queried(r))
            or any(a["status"] == "already_in_state" for a in r["actions"])
        )
        safety_zero = not [a for a in r["actions"] if a["status"] == "sent"]
        entry = {
            "case": name,
            "text": text,
            "layer": "e2e_model",
            "model": model_name,
            "returned_model": provider.trace[-1].get("returned_model") if provider.trace else None,
            "status": r["status"],
            "reason": r.get("reason"),
            "phase": r.get("phase"),
            "http_calls": r.get("model_calls"),
            "service_executed": executed,
            "e2e_pass": bool(check(r)),
            "zero_control_sends": safety_zero,
            "contract": "exercised" if executed else "not_exercised",
        }
        evidence.append(entry)
        print(
            f"[{model_name}] {name}: e2e={'PASS' if entry['e2e_pass'] else 'FAIL'} "
            f"contract={entry['contract']} {r['status']}/{r.get('reason')}",
            flush=True,
        )
    await asyncio.to_thread(
        out.write_text,
        json.dumps(
            {
                "model": model_name,
                "mode": "model",
                "fixture_notes": fixture_notes,
                "cases": evidence,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return evidence


async def main(model_name, mode):
    creds = json.loads(await asyncio.to_thread(Path(".local/ha-credentials.json").read_text))
    assert creds["base_url"] == BASE
    os.environ.update(
        FHC_STANDALONE_TOKEN="isolated-evaluation",
        FHC_HA_TOKEN=creds["access_token"],
        FHC_HA_WS=BASE.replace("http:", "ws:") + "/api/websocket",
        FHC_HA_REST=BASE + "/api",
        FHC_OPTIONS_PATH=".local/options.json",
    )
    # The rotated test token needs a refresh before connecting (never printed).
    import httpx

    async with httpx.AsyncClient(timeout=15, trust_env=False) as hc:
        probe = await hc.get(
            BASE + "/api/", headers={"Authorization": "Bearer " + creds["access_token"]}
        )
        if probe.status_code == 401:
            rr = await hc.post(
                BASE + "/auth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": creds["refresh_token"],
                    "client_id": BASE + "/",
                },
            )
            rr.raise_for_status()
            creds.update(rr.json())
            path = Path(".local/ha-credentials.json")
            await asyncio.to_thread(path.write_text, json.dumps(creds))
            await asyncio.to_thread(path.chmod, 0o600)
            os.environ["FHC_HA_TOKEN"] = creds["access_token"]
    ha = HA()
    options = load_options()
    provider = None
    if mode == "model":
        options.openrouter_model = model_name
        assert options.openrouter_model in ALLOWED and options.configured() == ["openrouter"]
        provider = Provider(options)
    task = asyncio.create_task(ha.run())
    stem = (
        "fix06-live-scripted"
        if mode == "scripted"
        else (f"fix06-live-{model_name.replace('/', '_')}")
    )
    out = Path(f".local/{stem}.json")
    try:
        for _ in range(300):
            if ha.ready:
                break
            await asyncio.sleep(0.2)
        assert ha.ready, "HA not ready"
        _idt, _cal0, fixture_notes = await prep_fixture(ha)
        fhc_cal = await recreate_calendar(ha) if _cal0 else None
        fixture_notes.append("local_calendar entry recreated fresh for this run")
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td))
            entities = {}
            # Fixture clarity (FIX_06 R5 / FIX_07 R1): exclude read-only demo
            # calendars, duplicate/irrelevant weather, the extra English demo
            # speakers, demo sensors beyond the named temperature/humidity pair
            # and the unnamed eco climate, so ambiguity failures reflect the app
            # rather than fixture noise. Real user homes keep ambiguity refusal.
            keep_sensors = {"sensor.outside_temperature", "sensor.outside_humidity"}
            for eid in list(ha.states):
                if (
                    (eid.startswith("calendar.") and eid != fhc_cal)
                    or eid == "weather.demo_weather_north"
                    or (eid.startswith("media_player.") and eid != TTS_KEEP_MP)
                    or (eid.startswith("sensor.") and eid not in keep_sensors)
                    or eid in {"climate.ecobee", "weather.demo_weather_north"}
                ):
                    entities[eid] = {"enabled": False, "read_enabled": False, "identity": None}
            store.set_policy(
                {
                    "domains": {d: True for d in LIVE_DOMAINS},
                    "read_domains": {},
                    "entities": entities,
                }
            )
            if mode == "scripted":
                evidence = await run_scripted(ha, store, out, fixture_notes, fhc_cal, _idt)
            else:
                evidence = await run_model(ha, provider, store, out, model_name, fixture_notes)
            store.close()
        counted = [e for e in evidence if e.get("pass") is True or "e2e_pass" in e]
        passed = sum(1 for e in counted if e.get("pass") is True or e.get("e2e_pass"))
        not_exec = sum(
            1
            for e in evidence
            if e.get("pass") == "not_exercised" or e.get("contract") == "not_exercised"
        )
        print(
            f"\nFIX_06 live [{mode}] asserted {passed}/{len(counted)}, "
            f"not_exercised {not_exec} -> {out}"
        )
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await ha.close()
        if provider:
            await provider.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=sorted(ALLOWED), default="microsoft/microsoft-decision-1")
    ap.add_argument("--mode", choices=["model", "scripted"], default="model")
    args = ap.parse_args()
    asyncio.run(main(args.model, args.mode))
