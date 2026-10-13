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


async def test_already_off_is_noop(ha, store):
    ha.states["light.living"]["state"] = "off"
    result = await execute(ha, store, ScriptedProvider(), "거실불 꺼줘")
    assert result["status"] == "succeeded"
    assert result["actions"][0]["status"] == "already_in_state"
    assert not ha.calls
