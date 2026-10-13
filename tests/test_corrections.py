import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from conftest import ScriptedProvider
from fastapi.testclient import TestClient
from fhc.actions import is_already_in_state, literals, options_for
from fhc.catalog import Catalog
from fhc.config import Options, save_options
from fhc.main import app
from fhc.store import Store
from test_engine import execute


def climate(ha, eid="climate.living", name="거실 에어컨", **attrs):
    ha.services["climate"] = {
        s: {} for s in ["turn_on", "turn_off", "set_temperature", "set_hvac_mode"]
    }
    ha.states[eid] = {
        "state": "cool",
        "attributes": {
            "friendly_name": name,
            "hvac_modes": ["off", "cool", "heat", "fan_only", "dry", "auto"],
            "supported_features": 385,
            "temperature_unit": "°C",
            "min_temp": 16,
            "max_temp": 30,
            "target_temp_step": 1,
            "temperature": 27,
            **attrs,
        },
    }
    ha.registry.append({"entity_id": eid, "id": eid + "-identity"})


async def test_per_target_literals_and_combined_mode(ha, store):
    climate(ha)
    climate(ha, "climate.bedroom", "침실 에어컨")
    result = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "거실 에어컨": {"hvac": "cool", "temperature": "v0"},
                "침실 에어컨": {"temperature": "v1"},
            }
        ),
        "거실 에어컨 냉방 25도, 침실 에어컨 24도",
    )
    assert result["status"] == "succeeded"
    values = {c[2]: c[3] for c in ha.calls}
    assert values["climate.living"] == {"temperature": 25, "hvac_mode": "cool"}
    assert values["climate.bedroom"] == {"temperature": 24}


@pytest.mark.parametrize("text", ["에어컨 바람만 나오게", "제습으로", "자동 모드", "whatever"])
def test_supported_modes_do_not_depend_on_words(ha, text):
    climate(ha)
    entity = next(e for e in Catalog(ha, {"climate": True}).entities.values())
    assert {"fan_only", "dry", "auto"} <= set(options_for(entity, literals(text))["hvac"])


@pytest.mark.parametrize(
    "text, expected", [("온도 -25도", -25), ("밝기 −20%", -20), ("온도 +24.5℃", 24.5)]
)
def test_signed_literal_spans(text, expected):
    item = literals(text)[0]
    assert item["value"] == expected
    assert text[slice(*item["span"])] == item["text"]


@pytest.mark.parametrize(
    "attrs,text,reason",
    [
        ({}, "에어컨 -25도", "temperature_out_of_range"),
        ({"target_temp_step": 1}, "에어컨 24.5도", "temperature_step_invalid"),
        ({"temperature_unit": None}, "에어컨 25도", "temperature_unit_unknown"),
    ],
)
async def test_invalid_temperature_never_dispatches(ha, store, attrs, text, reason):
    climate(ha, **attrs)
    result = await execute(
        ha, store, ScriptedProvider({"거실 에어컨": {"temperature": "v0"}}), text
    )
    assert result["reason"] == reason
    assert not ha.calls


async def test_fahrenheit_conversion_and_range_only(ha, store):
    climate(ha, temperature_unit="°F", min_temp=50, max_temp=90, target_temp_step=1)
    result = await execute(
        ha, store, ScriptedProvider({"거실 에어컨": {"temperature": "v0"}}), "에어컨 25℃"
    )
    assert result["status"] == "succeeded"
    assert ha.calls[0][3]["temperature"] == 77
    ha.states["climate.living"]["attributes"]["supported_features"] = 2
    entity = next(iter(Catalog(ha, {"climate": True}).entities.values()))
    assert "temperature" not in options_for(entity, literals("25도"))


async def test_combined_color_brightness_and_noop(ha, store):
    ha.states["light.living"]["attributes"].update(
        supported_color_modes=["rgb"], brightness=128, rgb_color=[0, 0, 255]
    )
    result = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"brightness": "v0", "color": "red"}}),
        "거실 조명 빨간색 밝기 50프로",
    )
    assert result["status"] == "succeeded"
    assert ha.calls[0][3] == {"brightness_pct": 50, "rgb_color": [255, 0, 0]}
    assert not is_already_in_state(
        result["actions"][0],
        {"state": "on", "attributes": {"brightness": 128, "rgb_color": [0, 0, 255]}},
    )


async def test_kelvin_supported_and_onoff_no_brightness(ha, store):
    ha.states["light.living"]["attributes"].update(
        supported_color_modes=["color_temp"], min_color_temp_kelvin=2000, max_color_temp_kelvin=6500
    )
    result = await execute(
        ha, store, ScriptedProvider({"천장등": {"color_temp": "v0"}}), "거실 3500K"
    )
    assert result["status"] == "succeeded"
    assert ha.calls[0][3] == {"color_temp_kelvin": 3500}
    ha.states["light.living"]["attributes"]["supported_color_modes"] = ["onoff"]
    e = next(
        e for e in Catalog(ha, {"light": True}).entities.values() if e.entity_id == "light.living"
    )
    assert set(options_for(e, literals("50프로"))) == {"power"}


async def test_fresh_capability_change_aborts_all(ha, store):
    ha.states["light.living"]["attributes"].update(supported_color_modes=["rgb"])
    original = ha.fresh_state

    async def fresh(eid):
        state = await original(eid)
        state["attributes"]["supported_color_modes"] = ["onoff"]
        return state

    ha.fresh_state = fresh
    result = await execute(ha, store, ScriptedProvider({"천장등": {"color": "red"}}), "빨간색으로")
    assert result["reason"] == "environment_changed"
    assert not ha.calls


async def test_group_leaves_exclusion_dedup_and_cycles(ha, store):
    ha.states["light.group"] = {
        "state": "on",
        "attributes": {
            "friendly_name": "전체등",
            "entity_id": ["light.living", "light.bedroom", "light.living"],
        },
    }
    store.set_entity_policy("light.bedroom", False)
    result = await execute(ha, store, ScriptedProvider({"천장등": "turn_off"}), "전체등 꺼줘")
    assert result["status"] == "succeeded"
    assert ha.calls == [("light", "turn_off", "light.living")]
    catalog = Catalog(ha, store.policy())
    assert all(e.entity_id != "light.group" for e in catalog.entities.values())
    assert "전체등" in next(iter(catalog.entities.values())).aliases
    ha.states["light.group"]["attributes"]["entity_id"] = ["light.group"]
    assert all("전체등" not in e.aliases for e in Catalog(ha, store.policy()).entities.values())


def test_policy_identity_rename_and_id_reuse(ha, store):
    ha.registry[0]["id"] = "stable"
    store.set_entity_policy("light.living", False, "stable")
    ha.registry[0]["entity_id"] = "light.renamed"
    ha.states["light.renamed"] = ha.states.pop("light.living")
    store.reconcile_registry(ha)
    assert not store.policy().is_allowed("light", "light.renamed", "stable")
    assert "light.living" not in store.policy().entities
    assert store.policy()["revision"] >= 2
    store.set_policy(
        {"domains": {"light": False}, "entities": {"light.renamed": {"enabled": True}}}
    )
    assert not store.policy().is_allowed("light", "light.renamed")


def legacy_db(path, policy, version=1):
    db = sqlite3.connect(path / "fhc.sqlite")
    db.executescript(
        "CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE requests(id TEXT PRIMARY KEY,text TEXT NOT NULL,created REAL NOT NULL,result TEXT NOT NULL);"
    )
    db.execute("INSERT INTO settings VALUES (?,?)", ("policy", policy))
    db.execute(f"PRAGMA user_version={version}")
    db.commit()
    db.close()


def test_legacy_upgrade_never_enables_climate(tmp_path):
    legacy_db(tmp_path, json.dumps({"light": False, "switch": False}))
    s = Store(tmp_path)
    assert s.policy().domains == {"light": False, "switch": False, "climate": False}
    assert s.db.execute("PRAGMA user_version").fetchone()[0] == 3
    s.close()


@pytest.mark.parametrize("version,raw", [(1, "{invalid"), (99, "{}")])
def test_bad_or_future_db_preserved(tmp_path, version, raw):
    legacy_db(tmp_path, raw, version)
    with pytest.raises(ValueError):
        Store(tmp_path)
    db = sqlite3.connect(tmp_path / "fhc.sqlite")
    assert db.execute("PRAGMA user_version").fetchone()[0] == version
    assert db.execute("SELECT value FROM settings").fetchone()[0] == raw
    db.close()


async def test_supervisor_canonical_merge_and_failure(monkeypatch):
    monkeypatch.delenv("FHC_STANDALONE_TOKEN", raising=False)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-only")
    real_client = httpx.AsyncClient
    saved = []

    def respond(req):
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "result": "ok",
                    "data": {
                        "options": {"openrouter_api_key": "new-native-key", "history_days": 15}
                    },
                },
            )
        saved.append(json.loads(req.content)["options"])
        return httpx.Response(200, json={"result": "ok"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond))
    )
    with patch.object(
        Path, "write_text", side_effect=AssertionError("Must not write Supervisor options")
    ):
        result = await save_options(
            {"openrouter_model": "microsoft/microsoft-decision-1"},
            Options(openrouter_api_key="stale"),
        )
    assert result.openrouter_api_key.get_secret_value() == "new-native-key"
    assert saved[0]["history_days"] == 15
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    with pytest.raises(ValueError, match="options_save_failed"):
        await save_options({}, Options())


async def test_standalone_persistence_failure_is_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test")
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(tmp_path / "options.json"))
    with patch("os.replace", side_effect=PermissionError):
        with pytest.raises(ValueError, match="options_save_failed"):
            await save_options({"provider": "azure"}, Options())
    assert not (tmp_path / "options.json").exists()


def test_ingress_admin_fail_closed_and_revocation(tmp_path, monkeypatch):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FHC_STANDALONE_TOKEN", raising=False)
    active = {"value": True}
    with TestClient(app, client=("172.30.32.2", 1)) as c:

        async def admin(uid):
            return active["value"] and uid == "verified"

        app.state.ha.is_admin = admin
        for path in ["config", "domains", "policy", "history"]:
            assert c.get("/api/" + path).status_code == 403
            assert c.get("/api/" + path, headers={"X-Remote-User-Id": "unknown"}).status_code == 403
            assert (
                c.get("/api/" + path, headers={"X-Remote-User-Id": "verified"}).status_code == 200
            )
        active["value"] = False
        assert c.get("/api/config", headers={"X-Remote-User-Id": "verified"}).status_code == 403


def test_settings_block_planning_and_apply_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(tmp_path / "options.json"))
    monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test")
    headers = {"Authorization": "Bearer test", "X-FHC-Request": "1"}
    with TestClient(app) as c:

        class Job:
            def done(self):
                return False

        job = Job()
        app.state.tasks.add(job)
        assert c.post("/api/config", json={"rescan_hours": 2}, headers=headers).status_code == 409
        app.state.tasks.clear()
        assert (
            c.post(
                "/api/config",
                json={"rescan_hours": 2, "history_days": 3, "history_limit": 50},
                headers=headers,
            ).status_code
            == 200
        )
        assert app.state.ha.rescan_hours == 2
        assert (app.state.store.days, app.state.store.limit) == (3, 50)
        assert c.post("/api/config", json={"history_days": 0}, headers=headers).status_code == 400
