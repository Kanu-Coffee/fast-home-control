"""Live Decision-1 evaluation against only the disposable localhost HAOS fixture.

Reads ignored .local files; never prints credentials. Not part of automated CI.
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

LIVING = {"light.ceiling_lights", "light.living_room_rgbww_lights"}
LIGHTS = LIVING | {
    "light.bed_light",
    "light.kitchen_lights",
    "light.office_rgbw_lights",
    "light.entrance_color_white_lights",
}
SWITCH = "switch.decorative_lights"
CASES = [
    ("거실불 꺼줘", LIVING, "turn_off"),
    ("거실전등 꺼줘", LIVING, "turn_off"),
    ("거실조명 꺼줘", LIVING, "turn_off"),
    ("거실 불 켜줘", LIVING, "turn_on"),
    ("침실 조명 전부 꺼줘", {"light.bed_light"}, "turn_off"),
    ("집에 있는 조명 전부 꺼줘", LIGHTS, "turn_off"),
    ("거실 불 끄고 거실 콘센트 켜줘", LIVING | {SWITCH}, "mixed"),
    ("거실 불 켜져 있으면 꺼줘", set(), None),
    ("거실 불 끄고 10분 뒤 다시 켜줘", set(), None),
    ("아무거나 꺼줘", set(), None),
    ("불 꺼줘", set(), None),
    ("거실 불 꺼줘 그리고 현관문 열어줘", set(), None),
    ("거실 불 꺼줘라는 문장을 영어로 번역해줘", set(), None),
    ("거실 불 끄지 마", set(), None),
    ("10분 뒤 거실 불 꺼줘", set(), None),
]


async def main():
    credentials = json.loads(await asyncio.to_thread(Path(".local/ha-credentials.json").read_text))
    base = credentials["base_url"]
    if base != "http://127.0.0.1:18180":
        raise RuntimeError("Only the project-owned disposable HAOS is allowed")
    os.environ.update(
        FHC_STANDALONE_TOKEN="isolated-evaluation",
        FHC_HA_TOKEN=credentials["access_token"],
        FHC_HA_WS=base.replace("http:", "ws:") + "/api/websocket",
        FHC_HA_REST=base + "/api",
        FHC_OPTIONS_PATH=".local/options.json",
    )
    ha, provider = HA(), Provider(load_options())
    task = asyncio.create_task(ha.run())
    results = []
    try:
        for _ in range(300):
            if ha.ready:
                break
            await asyncio.sleep(0.1)
        if not ha.ready:
            raise RuntimeError("Test HA not ready")
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            engine = Engine(ha, provider, store)
            for text, expected, service in CASES:
                # Seed opposite states to prove dispatch, not just no-op success.
                for entity_id in LIGHTS | {SWITCH}:
                    seed = "turn_on" if service != "turn_on" and entity_id in LIGHTS else "turn_off"
                    await ha.call(entity_id.split(".")[0], seed, entity_id)
                await asyncio.sleep(0.1)
                before = {e: (await ha.fresh_state(e))["state"] for e in LIGHTS | {SWITCH}}
                request_id = str(uuid.uuid4())
                store.insert(request_id, text)
                calls = provider.calls
                await engine.run(request_id, text)
                result = store.get(request_id)[1]
                after = {e: (await ha.fresh_state(e))["state"] for e in before}
                actual = {a["entity_id"] for a in result["actions"]}
                unchanged = all(after[e] == before[e] for e in before if e not in expected)
                intended = all(
                    after[e] == ("on" if service == "turn_on" or e == SWITCH else "off")
                    for e in expected
                )
                passed = (
                    actual == expected
                    and unchanged
                    and intended
                    and (
                        result["status"] == "succeeded"
                        if expected
                        else result["status"] == "rejected"
                    )
                )
                result.update(
                    passed=passed, model_calls=provider.calls - calls, before=before, after=after
                )
                results.append(result)
                print(
                    text,
                    result["status"],
                    result["reason"],
                    "PASS" if passed else "FAIL",
                    flush=True,
                )
            store.close()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await ha.close()
        await provider.close()
        await asyncio.to_thread(
            Path(".local/real-ha-evaluation.json").write_text,
            json.dumps(results, ensure_ascii=False, indent=2),
        )
    print(f"{sum(r['passed'] for r in results)}/{len(results)} passed")


if __name__ == "__main__":
    asyncio.run(main())
