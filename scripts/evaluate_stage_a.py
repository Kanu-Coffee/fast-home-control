"""Live Microsoft Decision and TypeSafe Jev evaluation against the disposable HAOS fixture only.

Load ignored .local credentials/options prepared by the test operator. No physical
HA host, arbitrary model, or other provider may be substituted. See docs/testing.md.
"""

import argparse
import asyncio
import contextlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from fhc.config import load_options
from fhc.engine import Engine
from fhc.ha import HA
from fhc.provider import Provider
from fhc.store import Store

BASE = "http://127.0.0.1:18180"

# (text, expected_state_changes, options)
# options: negative (must reject, 0 dispatch), condition_false, response (service_data
# and response-shape assertions), requires (entity ids that must exist on the fixture).
CASES = [
    ("거실 에어컨 켜줘 송풍모드", {"climate.hvac": {"state": "fan_only"}}, {}),
    ("거실 에어컨 바람만 나오게 해줘", {"climate.hvac": {"state": "fan_only"}}, {}),
    ("거실 에어컨 제습으로 바꿔", {"climate.hvac": {"state": "dry"}}, {}),
    ("거실 에어컨 냉방 25도로", {"climate.hvac": {"state": "cool", "temperature": 25}}, {}),
    (
        "거실 에어컨 26도, 침실 에어컨 24도로",
        {"climate.hvac": {"temperature": 26}, "climate.heatpump": {"temperature": 24}},
        {},
    ),
    (
        "천장등 빨간색 밝기 30프로",
        {"light.ceiling_lights": {"rgb_color": [255, 0, 0], "brightness": 76}},
        {},
    ),
    ("천장등 색온도 3500K로", {"light.ceiling_lights": {"color_temp_kelvin": 3500}}, {}),
    (
        "천장등 조금 어둡게 해줘",
        # Seeded at 200/255 (~78%). A real -10%p lands near 174/255, not "any change".
        {"light.ceiling_lights": {"brightness": (174, 13)}},
        {"seed": ("light", "turn_on", "light.ceiling_lights", {"brightness": 200})},
    ),
    (
        "거실불 꺼줘",
        {
            "light.ceiling_lights": {"state": "off"},
            "light.living_room_rgbww_lights": {"state": "off"},
        },
        {},
    ),
    (
        "거실전등 켜줘",
        {
            "light.ceiling_lights": {"state": "on"},
            "light.living_room_rgbww_lights": {"state": "on"},
        },
        {},
    ),
    ("거실 에어컨 -25도로", {}, {"negative": True}),
    ("천장등 밝기 -20%", {}, {"negative": True}),
    ("거실 불 끄고 현관문 열어줘", {}, {"negative": True}),
    ("아무거나 켜줘", {}, {"negative": True}),
    ("거실 불 켜져 있으면 꺼줘", {}, {"negative": True}),
    # --- B/C corpus (FIX_05 R4/R5): typed effects, not service-name presence ---
    (
        "천장등 온도가 -50도 이상이면 꺼줘",
        {},
        {"condition_false": True, "requires": ["climate.hvac"]},
    ),
    (
        "시간별 날씨 예보 알려줘",
        {},
        {"response": {"service": "get_forecasts", "type": "hourly"}, "requires": ["weather.home"]},
    ),
    (
        "내 일정 상태 알려줘",
        {},
        {"response": {"service": "query_state"}, "requires": ["weather.home"]},
    ),
    (
        "내일 일정 알려줘",
        {},
        {"response": {"service": "get_events"}, "requires": ["calendar.calendar_1"]},
    ),
    (
        "할 일 목록 알려줘",
        {},
        {"response": {"service": "get_items"}, "requires": ["todo.shopping_list"]},
    ),
]

ALLOWED_MODELS = {"microsoft/microsoft-decision-1", "typesafe/jev-1.13"}
LIVE_POLICY_DOMAINS = [
    "light",
    "switch",
    "climate",
    "sensor",
    "binary_sensor",
    "weather",
    "calendar",
    "todo",
    "media_player",
    "input_boolean",
    "scene",
    "input_datetime",
]


class SetupError(Exception):
    pass


def expected_ok(expected_values, actual_values):
    for key, want in expected_values.items():
        got = actual_values.get(key)
        if isinstance(want, tuple):
            target, tol = want
            if not isinstance(got, (int, float)) or abs(got - target) > tol:
                return False
        elif isinstance(want, list):
            if got != want:
                return False
        elif got != want:
            return False
    return True


async def reset_ha_case(ha: HA, options):
    """Seed initial state; failures are reported as setup_failed, never swallowed."""
    seed = options.get("seed")
    if not seed:
        return
    domain, service, entity_id, data = seed
    await ha.call(domain, service, entity_id, service_data=data)
    await asyncio.sleep(0.2)
    st = await ha.fresh_state(entity_id)
    for key, want in (data or {}).items():
        got = st.get("attributes", {}).get(key)
        if got != want:
            raise SetupError(f"reset_not_fresh:{entity_id}:{key}")
    if "brightness" in (data or {}):
        # Relative-delta cases must start from a fresh, verified absolute value.
        if st.get("attributes", {}).get("brightness") is None:
            raise SetupError(f"reset_brightness_missing:{entity_id}")


async def response_ok(ha: HA, result, spec):
    actions = [a for a in result["actions"] if a.get("status") == "query_succeeded"]
    if not actions:
        return False, "no_response_query"
    action = actions[0]
    if spec.get("service") and action["service"] != spec["service"]:
        return False, f"service={action['service']}"
    data = action.get("service_data") or {}
    if spec.get("type") and data.get("type") != spec["type"]:
        return False, f"type={data.get('type')}"
    if spec["service"] == "get_events" and not (
        data.get("start_date_time") and data.get("end_date_time")
    ):
        return False, "calendar_window_missing"
    if spec["service"] == "get_events" and not data["start_date_time"].startswith(
        str(_local_today(ha, 1))
    ):
        return False, "calendar_window_not_tomorrow"
    if spec["service"] == "get_forecasts" and not (
        isinstance(action.get("query_result"), str) and "예보" in action["query_result"]
    ):
        return False, "forecast_display_missing"
    return True, action.get("query_result")


def _local_today(ha: HA, offset_days=0):
    import datetime as _dt
    from zoneinfo import ZoneInfo

    tz = getattr(ha, "time_zone", None) or "UTC"
    return (_dt.datetime.now(ZoneInfo(tz)) + _dt.timedelta(days=offset_days)).date()


async def main(model_name: str):
    creds = json.loads(await asyncio.to_thread(Path(".local/ha-credentials.json").read_text))
    assert creds["base_url"] == BASE, "Only the disposable localhost test HAOS is allowed"
    os.environ.update(
        FHC_STANDALONE_TOKEN="isolated-evaluation",
        FHC_HA_TOKEN=creds["access_token"],
        FHC_HA_WS=BASE.replace("http:", "ws:") + "/api/websocket",
        FHC_HA_REST=BASE + "/api",
        FHC_OPTIONS_PATH=".local/options.json",
    )
    ha = HA()
    options = load_options()
    options.openrouter_model = model_name
    if options.openrouter_model not in ALLOWED_MODELS or options.configured() != ["openrouter"]:
        raise RuntimeError(
            f"This test is authorized for models in {ALLOWED_MODELS} via OpenRouter only"
        )
    provider = Provider(options)
    assert provider.options.openrouter_model in ALLOWED_MODELS
    task = asyncio.create_task(ha.run())
    results = []
    out_stem = f"stage-a-evaluation-{model_name.replace('/', '_')}.json"
    out_file = Path(f".local/{out_stem}")

    print("\n=======================================================")
    print(f"Starting Live Evaluation with model: {model_name}")
    print("=======================================================\n")

    try:
        for _ in range(200):
            if ha.ready:
                break
            await asyncio.sleep(0.1)
        assert ha.ready
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td))
            store.set_policy(
                {
                    "domains": {d: True for d in LIVE_POLICY_DOMAINS},
                    "read_domains": {},
                    "entities": {},
                }
            )
            engine = Engine(ha, provider, store)
            for text, expected, opts in CASES:
                missing = [e for e in opts.get("requires", []) if e not in ha.states]
                if missing:
                    results.append(
                        {"text": text, "setup_failed": True, "missing_entities": missing}
                    )
                    print(f"[SKIP] '{text}' missing fixture entities {missing}", flush=True)
                    continue
                entry = {"text": text, "expected": expected, "options": opts}
                try:
                    await reset_ha_case(ha, opts)
                except Exception as exc:  # reset/seed problems are never counted as model fails
                    entry.update(setup_failed=str(exc)[:200], passed=False)
                    results.append(entry)
                    await asyncio.to_thread(
                        out_file.write_text, json.dumps(results, ensure_ascii=False, indent=2)
                    )
                    print(f"[SETUP-FAILED] '{text}': {exc}", flush=True)
                    continue

                rid = str(uuid.uuid4())
                store.insert(rid, text)
                initial_calls = provider.calls
                await engine.run(rid, text)
                result = store.get(rid)[1]
                http_calls = provider.calls - initial_calls
                entry.update(
                    requested_model=model_name,
                    returned_model=provider.trace[-1]["returned_model"] if provider.trace else None,
                    http_calls=http_calls,
                    result=result,
                )
                dispatched = [a for a in result["actions"] if a["status"] in {"sent", "uncertain"}]

                if opts.get("negative"):
                    ok = result["status"] == "rejected" and not dispatched
                elif opts.get("condition_false"):
                    ok = (
                        result.get("condition_result") is False
                        and result.get("condition_evaluation", {}).get("selection") == "model_typed"
                        and result.get("reason") == "condition_not_met"
                        and not dispatched
                    )
                elif opts.get("response"):
                    ok, detail = await response_ok(ha, result, opts["response"])
                    entry["response_detail"] = str(detail)[:300]
                else:
                    actual = {}
                    for eid in expected:
                        st = await ha.fresh_state(eid)
                        actual[eid] = {"state": st["state"], **st["attributes"]}
                    entry["states"] = actual
                    targets = {a["entity_id"] for a in result["actions"]}
                    ok = (
                        result["status"] == "succeeded"
                        and targets == set(expected)
                        and all(
                            expected_ok(wanted, actual[eid]) for eid, wanted in expected.items()
                        )
                    )
                entry["pass"] = bool(ok)
                results.append(entry)
                await asyncio.to_thread(
                    out_file.write_text, json.dumps(results, ensure_ascii=False, indent=2)
                )
                await asyncio.to_thread(
                    Path(".local/stage-a-evaluation.json").write_text,
                    json.dumps(results, ensure_ascii=False, indent=2),
                )
                status_str = "PASS" if ok else "FAIL"
                print(
                    f"[{status_str}] '{text}' -> status={result['status']} "
                    f"reason={result.get('reason')} verify={result.get('verification_score')} "
                    f"total_ms={result['timings_ms']['total']} calls={http_calls}",
                    flush=True,
                )
            store.close()

        executed = [r for r in results if not r.get("setup_failed") and "pass" in r]
        setup_failed = [r for r in results if r.get("setup_failed")]
        passed_count = sum(1 for r in executed if r["pass"])
        total_count = len(executed)
        valid = [r for r in executed if r.get("expected") and not r["options"].get("negative")]
        neg = [r for r in executed if r["options"].get("negative")]
        avg_ms = (
            round(
                sum(r["result"]["timings_ms"]["total"] for r in executed) / total_count,
                1,
            )
            if total_count
            else None
        )

        print("\n-------------------------------------------------------")
        print(f"Summary for {model_name}:")
        print(f"Executed cases: {passed_count}/{total_count}")
        print(f"Value/effect cases: {sum(1 for r in valid if r['pass'])}/{len(valid)}")
        print(f"Reject cases: {sum(1 for r in neg if r['pass'])}/{len(neg)}")
        print(f"Setup failed (reported separately): {len(setup_failed)}")
        if avg_ms is not None:
            print(f"Average Total Latency: {avg_ms}ms")
        print(f"Saved results to {out_file}")
        print("-------------------------------------------------------\n")

    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await ha.close()
        await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Stage A against HAOS fixture")
    parser.add_argument(
        "--model",
        choices=sorted(list(ALLOWED_MODELS)),
        default="microsoft/microsoft-decision-1",
        help="Target model on OpenRouter (microsoft/microsoft-decision-1 or typesafe/jev-1.13)",
    )
    cli_args = parser.parse_args()
    asyncio.run(main(cli_args.model))
