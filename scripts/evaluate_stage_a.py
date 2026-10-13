"""Live Microsoft Decision evaluation against the disposable HAOS fixture only.

Load ignored .local credentials/options prepared by the test operator. No physical
HA host, arbitrary model, or other provider may be substituted. See docs/testing.md.
"""

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
CASES = [
    ("거실 에어컨 켜줘 송풍모드", {"climate.hvac": {"state": "fan_only"}}),
    ("거실 에어컨 바람만 나오게 해줘", {"climate.hvac": {"state": "fan_only"}}),
    ("거실 에어컨 제습으로 바꿔", {"climate.hvac": {"state": "dry"}}),
    ("거실 에어컨 냉방 25도로", {"climate.hvac": {"state": "cool", "temperature": 25}}),
    (
        "거실 에어컨 26도, 침실 에어컨 24도로",
        {"climate.hvac": {"temperature": 26}, "climate.heatpump": {"temperature": 24}},
    ),
    (
        "천장등 빨간색 밝기 30프로",
        {"light.ceiling_lights": {"rgb_color": [255, 0, 0], "brightness": 76}},
    ),
    ("천장등 색온도 3500K로", {"light.ceiling_lights": {"color_temp_kelvin": 3500}}),
    ("천장등 조금 어둡게 해줘", {"light.ceiling_lights": {}}),
    (
        "거실불 꺼줘",
        {
            "light.ceiling_lights": {"state": "off"},
            "light.living_room_rgbww_lights": {"state": "off"},
        },
    ),
    (
        "거실전등 켜줘",
        {
            "light.ceiling_lights": {"state": "on"},
            "light.living_room_rgbww_lights": {"state": "on"},
        },
    ),
    ("거실 에어컨 -25도로", {}),
    ("천장등 밝기 -20%", {}),
    ("거실 불 끄고 현관문 열어줘", {}),
    ("아무거나 켜줘", {}),
    ("거실 불 켜져 있으면 꺼줘", {}),
]


async def main():
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
    if options.openrouter_model != "microsoft/microsoft-decision-1" or options.configured() != [
        "openrouter"
    ]:
        raise RuntimeError("This test is authorized for Microsoft Decision-1 via OpenRouter only")
    provider = Provider(options)
    assert provider.options.openrouter_model == "microsoft/microsoft-decision-1"
    task = asyncio.create_task(ha.run())
    results = []
    try:
        for _ in range(200):
            if ha.ready:
                break
            await asyncio.sleep(0.1)
        assert ha.ready
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td))
            engine = Engine(ha, provider, store)
            for text, expected in CASES:
                rid = str(uuid.uuid4())
                store.insert(rid, text)
                await engine.run(rid, text)
                result = store.get(rid)[1]
                actual = {
                    eid: {"state": ha.states[eid]["state"], **ha.states[eid]["attributes"]}
                    for eid in expected
                }
                # Fetch fresh state after service acknowledgment to verify actual attributes.
                for eid in expected:
                    st = await ha.fresh_state(eid)
                    actual[eid] = {"state": st["state"], **st["attributes"]}
                targets = {a["entity_id"] for a in result["actions"]}
                ok = (
                    (
                        result["status"] == "succeeded"
                        and targets == set(expected)
                        and all(
                            all(
                                actual[eid].get(k) == v
                                or (k == "brightness" and abs(actual[eid].get(k, 0) - v) <= 1)
                                for k, v in wanted.items()
                            )
                            for eid, wanted in expected.items()
                        )
                    )
                    if expected
                    else (
                        result["status"] == "rejected"
                        and not any(a["status"] in {"sent", "uncertain"} for a in result["actions"])
                    )
                )
                results.append(
                    {
                        "text": text,
                        "expected": expected,
                        "pass": ok,
                        "result": result,
                        "states": actual,
                    }
                )
                await asyncio.to_thread(
                    Path(".local/stage-a-evaluation.json").write_text,
                    json.dumps(results, ensure_ascii=False, indent=2),
                )
                print(
                    json.dumps(
                        {
                            "text": text,
                            "pass": ok,
                            "status": result["status"],
                            "reason": result["reason"],
                            "verify": result.get("verification_score"),
                            "total": result["timings_ms"]["total"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            store.close()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await ha.close()
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
