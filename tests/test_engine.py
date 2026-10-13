import uuid

import pytest
from conftest import ScriptedProvider
from fhc.catalog import Catalog
from fhc.engine import Engine


async def execute(ha, store, provider, text):
    request_id = str(uuid.uuid4())
    store.insert(request_id, text)
    await Engine(ha, provider, store).run(request_id, text)
    return store.get(request_id)[1]


@pytest.mark.parametrize(
    "text", ["거실불 꺼줘", "거실전등 꺼줘", "거실조명 꺼줘", "응접실 좀 밝혀줄래"]
)
async def test_all_catalog_reaches_model_without_local_phrase_filter(ha, store, text):
    provider = ScriptedProvider()
    result = await execute(ha, store, provider, text)
    catalog = provider.inputs[0][0]["catalog"]
    names = {e["name"] for group in catalog for e in group["entities"]}
    assert names == {"천장등", "침실등", "콘센트"}
    assert provider.inputs[0][0]["command"] == text
    assert result["status"] == "succeeded"
    assert ha.calls == [("light", "turn_off", "light.living")]
    # Prescribed decisions: this does NOT measure the input's semantic interpretation.


async def test_partial_or_unsupported_request_never_executes(ha, store):
    result = await execute(ha, store, ScriptedProvider(supported=False), "거실불 끄고 문 열어줘")
    assert result["status"] == "rejected"
    assert ha.calls == []


async def test_final_plan_rejection_stops_all_calls(ha, store):
    result = await execute(ha, store, ScriptedProvider(exact=False), "거실불 꺼줘")
    assert result["reason"] == "plan_not_verified"
    assert not ha.calls


async def test_all_targets_preflight_before_dispatch(ha, store):
    ha.states["light.bedroom"]["state"] = "unavailable"
    provider = ScriptedProvider({"천장등": "turn_off", "침실등": "turn_off"})
    result = await execute(ha, store, provider, "집 전체 조명 꺼줘")
    assert result["status"] == "rejected"
    assert not ha.calls


async def test_lost_ack_is_uncertain_and_not_retried(ha, store):
    ha.timeout = True
    result = await execute(ha, store, ScriptedProvider(), "거실불 꺼줘")
    assert result["status"] == "uncertain"
    assert result["actions"][0]["status"] == "uncertain"
    assert len(ha.calls) == 1


async def test_policy_change_during_inference_prevents_execution(ha, store):
    provider = ScriptedProvider()
    original = provider.decide

    async def decide(state, questions):
        result = await original(state, questions)
        if "exact" in questions:
            store.set_policy({"light": False, "switch": True})
        return result

    provider.decide = decide
    result = await execute(ha, store, provider, "거실불 꺼줘")
    assert result["reason"] == "environment_changed"
    assert not ha.calls


def test_catalog_enforces_hidden_disabled_and_domains(ha):
    ha.registry[0]["hidden_by"] = "user"
    ha.states["lock.door"] = {"entity_id": "lock.door", "state": "locked", "attributes": {}}
    catalog = Catalog(ha, {"light": True, "switch": False, "lock": True})
    assert [e.entity_id for e in catalog.entities.values()] == ["light.bedroom"]


def test_hundreds_of_entities_are_not_truncated_or_lexically_filtered(ha):
    for index in range(500):
        entity_id = f"light.test_{index}"
        ha.states[entity_id] = {
            "state": "off",
            "attributes": {"friendly_name": f"테스트 조명 {index}"},
        }
        ha.registry.append(
            {"entity_id": entity_id, "area_id": "living", "aliases": [f"별칭{index}"]}
        )
    catalog = Catalog(ha, {"light": True, "switch": True})
    exposed = [e for group in catalog.compact() for e in group["entities"]]
    assert len(exposed) == 503
    assert {f"별칭{i}" for i in range(500)}.issubset(
        {a for e in exposed for a in e.get("aliases", [])}
    )


async def test_already_off_is_noop(ha, store):
    ha.states["light.living"]["state"] = "off"
    result = await execute(ha, store, ScriptedProvider(), "거실불 꺼줘")
    assert result["status"] == "succeeded"
    assert result["actions"][0]["status"] == "already_in_state"
    assert not ha.calls


async def test_climate_fan_only_and_temperature(ha, store):
    ha.services["climate"] = {
        "set_hvac_mode": {},
        "set_temperature": {},
        "turn_on": {},
        "turn_off": {},
    }
    ha.states["climate.living"] = {
        "entity_id": "climate.living",
        "state": "off",
        "attributes": {
            "friendly_name": "거실 에어컨",
            "hvac_modes": ["off", "cool", "fan_only"],
            "min_temp": 18,
            "supported_features": 385,
            "temperature_unit": "°C",
            "target_temp_step": 1,
            "max_temp": 30,
            "temperature": 26,
        },
    }
    ha.registry.append({"entity_id": "climate.living", "area_id": "living"})

    # 1. 송풍 모드
    provider = ScriptedProvider({"거실 에어컨": "mode_fan_only"})
    result = await execute(ha, store, provider, "에어컨 켜줘 송풍모드")
    assert result["status"] == "succeeded"
    assert ha.calls == [("climate", "set_hvac_mode", "climate.living", {"hvac_mode": "fan_only"})]

    # 2. 온도 설정
    ha.calls.clear()
    provider = ScriptedProvider({"거실 에어컨": "set_temp"})
    result = await execute(ha, store, provider, "거실 에어컨 25도로")
    assert result["status"] == "succeeded"
    assert ha.calls == [("climate", "set_temperature", "climate.living", {"temperature": 25.0})]

    # 3. 범위 밖 온도
    ha.calls.clear()
    provider = ScriptedProvider({"거실 에어컨": "set_temp"})
    result = await execute(ha, store, provider, "거실 에어컨 50도로")
    assert result["status"] == "rejected"
    assert result["reason"] == "temperature_out_of_range"
    assert not ha.calls


async def test_light_color_and_brightness_not_noop_when_on(ha, store):
    ha.states["light.living"]["attributes"]["supported_color_modes"] = ["rgb", "brightness"]
    ha.states["light.living"]["attributes"]["brightness"] = 200
    ha.states["light.living"]["state"] = "on"

    # 1. 색상 변경 (on 상태여도 no-op이 아님)
    provider = ScriptedProvider({"천장등": "set_color"})
    result = await execute(ha, store, provider, "거실 조명 빨간색으로")
    assert result["status"] == "succeeded"
    assert ha.calls == [("light", "turn_on", "light.living", {"rgb_color": [255, 0, 0]})]

    # 2. 조금 어둡게 (on 상태여도 no-op이 아님)
    ha.calls.clear()
    provider = ScriptedProvider({"천장등": "dim_down"})
    result = await execute(ha, store, provider, "조명 조금 어둡게")
    assert result["status"] == "succeeded"
    assert ha.calls == [("light", "turn_on", "light.living", {"brightness_step_pct": -10})]


async def test_entity_policy_exclusion(ha, store):
    store.set_entity_policy("light.living", False)
    provider = ScriptedProvider()
    _ = await execute(ha, store, provider, "거실불 꺼줘")
    catalog = provider.inputs[0][0]["catalog"]
    entity_ids = [e["name"] for group in catalog for e in group["entities"]]
    assert "천장등" not in entity_ids
