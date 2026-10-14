import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from conftest import FakeHA, ScriptedProvider
from fastapi.testclient import TestClient
from fhc.actions import (
    extract_message,
    is_already_in_state,
    literals,
    make_action,
    make_actions,
    options_for,
    validate_fresh,
)
from fhc.catalog import Catalog
from fhc.config import Options, save_options
from fhc.main import app
from fhc.provider import DecisionError, Provider
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
    assert set(options_for(e, literals("50프로"))) == {"power", "query"}


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

    async def public_options(current):
        return current

    monkeypatch.setattr("fhc.main.read_public_options", public_options)
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


def test_no_singleton_decision_choices(ha):
    climate(ha)
    ha.states["light.living"]["attributes"].update(
        supported_color_modes=["color_temp"], min_color_temp_kelvin=2000, max_color_temp_kelvin=6500
    )
    for entity in Catalog(ha, {"light": True, "climate": True}).entities.values():
        assert all(
            len(criteria) >= 2 for criteria in options_for(entity, literals("불 켜줘")).values()
        )


async def test_unreported_step_is_continuous_and_units_fallback(ha, store):
    climate(ha, target_temp_step=None, temperature_unit=None)
    ha.temperature_unit = "°C"
    result = await execute(
        ha, store, ScriptedProvider({"거실 에어컨": {"temperature": "v0"}}), "거실 에어컨24.5도"
    )
    assert result["status"] == "succeeded"
    assert ha.calls[0][3]["temperature"] == 24.5


def test_public_command_response_excludes_admin_diagnostics():
    from fhc.main import command_summary

    public = command_summary(
        {
            "id": "id",
            "status": "rejected",
            "phase": "actions",
            "decisions": {"e1": 0.8},
            "scope_scores": {"e1": 0.9},
            "proposed_plan": [],
            "model_trace": [{"provider": "openrouter"}],
            "actions": [],
            "reason": "low_confidence",
        }
    )
    assert set(public) == {"id", "status", "actions", "reason"}


def test_f1_swap_and_cycle_renames_preserve_exclusion(store):
    class MockHA:
        def __init__(self, registry):
            self.registry = registry

    # 1. Swap rename: light.a (id-a, excluded) <-> light.b (id-b, allowed)
    store.set_entity_policy("light.a", False, "id-a")
    store.set_entity_policy("light.b", True, "id-b")
    ha_swap = MockHA(
        [
            {"entity_id": "light.b", "id": "id-a"},
            {"entity_id": "light.a", "id": "id-b"},
        ]
    )
    store.reconcile_registry(ha_swap)
    p = store.policy()
    assert p.is_allowed("light", "light.b", "id-a") is False
    assert p.is_allowed("light", "light.a", "id-b") is True

    # 2. 3-way cycle: a -> b -> c -> a with id-b excluded
    store.set_entity_policy("light.a", True, "id-a")
    store.set_entity_policy("light.b", False, "id-b")
    store.set_entity_policy("light.c", True, "id-c")
    ha_cycle = MockHA(
        [
            {"entity_id": "light.b", "id": "id-a"},
            {"entity_id": "light.c", "id": "id-b"},
            {"entity_id": "light.a", "id": "id-c"},
        ]
    )
    store.reconcile_registry(ha_cycle)
    p2 = store.policy()
    assert p2.is_allowed("light", "light.c", "id-b") is False
    assert p2.is_allowed("light", "light.b", "id-a") is True
    assert p2.is_allowed("light", "light.a", "id-c") is True


def test_f2_clear_history_strictly_wipes_proposed_plan_and_contents(store):
    record = store.insert("req-review-1", "민감한 방 조명 켜줘")
    record["proposed_plan"] = [
        {"name": "비밀방", "entity_id": "light.secret_room", "service_data": {"brightness_pct": 50}}
    ]
    record["query_results"] = [{"name": "비밀방", "state": "25"}]
    record["status"] = "rejected"
    store.save("req-review-1", record)

    store.clear_history()

    # Verify directly in SQLite row that proposed_plan and private contents are wiped
    row = store.db.execute("SELECT text, result FROM requests WHERE id='req-review-1'").fetchone()
    assert row[0] == ""
    data = json.loads(row[1])
    assert "proposed_plan" not in data
    assert "query_results" not in data
    assert data["text"] == ""
    assert data["actions"] == []
    assert data["hidden"] is True
    assert data["status"] == "rejected"
    assert data["id"] == "req-review-1"


def test_f3_domains_endpoint_detailed_counts(ha, store, monkeypatch, tmp_path):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    ha.registry.append({"entity_id": "sensor.living_temp", "id": "sens-1"})
    ha.states["sensor.living_temp"] = {"state": "24.5", "attributes": {"unit_of_measurement": "°C"}}

    with TestClient(app, client=("172.30.32.2", 1)) as c:

        async def mock_admin(uid):
            return uid == "admin-1"

        app.state.ha, app.state.store = ha, store
        app.state.ha.is_admin = mock_admin
        res = c.get("/api/domains", headers={"X-Remote-User-Id": "admin-1"})
        assert res.status_code == 200
        data = res.json()
        by_dom = {d["domain"]: d for d in data}

        # Light domain: control and read aggregation are independent (FIX_05 R2).
        assert "light" in by_dom
        light_dom = by_dom["light"]
        assert light_dom["discovered_count"] >= 2
        assert light_dom["controllable_count"] >= 2
        assert light_dom["queryable_count"] >= 2
        assert light_dom["allowed_query_count"] >= 2
        assert light_dom["status"] == "supported"
        assert all(
            ("queryable" in e and "read_enabled" in e and "controllable" in e)
            for e in light_dom["entities"]
        )

        # Sensor domain
        assert "sensor" in by_dom
        s = by_dom["sensor"]
        assert s["discovered_count"] >= 1
        assert s["queryable_count"] >= 1
        assert s["controllable_count"] == 0
        assert s["status"] == "query_only"

        # Deferred domain (ai_task)
        assert "ai_task" in by_dom
        ai = by_dom["ai_task"]
        assert ai["status"] == "deferred"
        assert "보류" in ai["note"]


def test_f4_diagnostic_export_zip_and_redaction(ha, store, monkeypatch, tmp_path):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    import io
    import zipfile

    # Insert a record with secrets and a sensitive command
    rec = store.insert("req-diag-1", "비밀 토큰 test-secret-token 거실불 켜줘")
    rec["status"] = "succeeded"
    rec["timings_ms"] = {"total": 120}
    store.save("req-diag-1", rec)

    # Insert a hidden/cleared record
    rec_hidden = store.insert("req-diag-hidden", "지워진 명령")
    rec_hidden["hidden"] = True
    store.save("req-diag-hidden", rec_hidden)

    with patch.dict("os.environ", {"SUPERVISOR_TOKEN": "super-secret-token"}):
        with TestClient(app, client=("172.30.32.2", 1)) as c:

            async def mock_admin(uid):
                return uid == "admin-1"

            app.state.ha, app.state.store = ha, store
            app.state.ha.is_admin = mock_admin

            # Set SecretStr in provider options to verify R2 (no TypeError with SecretStr)
            from fhc.config import Options

            app.state.provider.options = Options(openrouter_api_key="synthetic-secret-key")

            # 1. Non-admin access rejected
            res_denied = c.get("/api/history/export", headers={"X-Remote-User-Id": "regular-user"})
            assert res_denied.status_code == 403

            # 2. Admin access accepted, anonymized by default
            res = c.get("/api/history/export", headers={"X-Remote-User-Id": "admin-1"})
            assert res.status_code == 200
            assert res.headers["content-type"] == "application/zip"
            assert "attachment; filename=" in res.headers["content-disposition"]

            # Inspect zip contents
            zf = zipfile.ZipFile(io.BytesIO(res.content))
            names = zf.namelist()
            assert "manifest.json" in names
            assert "summary.json" in names
            assert "requests.jsonl" in names

            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["export_schema_version"] in {"1.0", "1.1"}
            assert manifest["include_text"] is False
            assert manifest["records_count"] == 1  # Hidden record excluded!

            requests_lines = zf.read("requests.jsonl").decode("utf-8").strip().split("\n")
            assert len(requests_lines) == 1
            exported_rec = json.loads(requests_lines[0])
            assert exported_rec["id"] == "req-diag-1"
            assert exported_rec["text"] == "[REDACTED_COMMAND]"

            # 3. Export with include_text=True
            res_text = c.get(
                "/api/history/export?include_text=true",
                headers={"X-Remote-User-Id": "admin-1"},
            )
            zf_text = zipfile.ZipFile(io.BytesIO(res_text.content))
            req_text_rec = json.loads(zf_text.read("requests.jsonl").decode("utf-8").strip())
            assert "거실불 켜줘" in req_text_rec["text"]
            assert "synthetic-secret-key" not in res_text.text


async def test_expanded_b_domains_execution(ha, store):
    # Vacuum
    ha.services["vacuum"] = {s: {} for s in ["start", "pause", "stop", "return_to_base"]}
    ha.states["vacuum.robot"] = {"state": "cleaning", "attributes": {"friendly_name": "로봇청소기"}}
    ha.registry.append({"entity_id": "vacuum.robot", "id": "vac-1"})

    # Fan
    ha.services["fan"] = {s: {} for s in ["turn_on", "turn_off", "set_percentage"]}
    ha.states["fan.living"] = {"state": "off", "attributes": {"friendly_name": "선풍기"}}
    ha.registry.append({"entity_id": "fan.living", "id": "fan-1"})

    # Cover
    ha.services["cover"] = {s: {} for s in ["open_cover", "close_cover", "set_cover_position"]}
    ha.states["cover.blind"] = {"state": "closed", "attributes": {"friendly_name": "블라인드"}}
    ha.registry.append({"entity_id": "cover.blind", "id": "cov-1"})

    # Button
    ha.services["button"] = {"press": {}}
    ha.states["button.doorbell"] = {"state": "unknown", "attributes": {"friendly_name": "초인종"}}
    ha.registry.append({"entity_id": "button.doorbell", "id": "btn-1"})

    # Policy allow all
    store.set_policy(
        {
            "domains": {
                "vacuum": True,
                "fan": True,
                "cover": True,
                "button": True,
                "light": True,
                "switch": True,
                "climate": True,
            },
            "entities": {},
        }
    )

    # Test vacuum return to base
    res_vac = await execute(
        ha,
        store,
        ScriptedProvider({"로봇청소기": {"vacuum_action": "return_to_base"}}),
        "청소기 충전대로 보내줘",
    )
    assert res_vac["status"] == "succeeded"
    assert ha.calls[-1] == ("vacuum", "return_to_base", "vacuum.robot")

    # Test button press
    res_btn = await execute(
        ha, store, ScriptedProvider({"초인종": {"button_action": "press"}}), "초인종 눌러줘"
    )
    assert res_btn["status"] == "succeeded"
    assert ha.calls[-1] == ("button", "press", "button.doorbell")


async def test_c_domain_query_and_condition_evaluation(ha, store):
    # Sensor query
    ha.registry.append({"entity_id": "sensor.living_room_temperature", "id": "sens-temp"})
    ha.states["sensor.living_room_temperature"] = {
        "state": "29.0",
        "attributes": {"friendly_name": "거실 온도", "unit_of_measurement": "°C"},
    }
    climate(ha)
    store.set_policy(
        {
            "domains": {"sensor": True, "climate": True, "light": True, "switch": True},
            "entities": {},
        }
    )

    # Query sensor
    res_q = await execute(
        ha, store, ScriptedProvider({"거실 온도": {"query": "query_state"}}), "거실 온도 알려줘"
    )
    assert res_q["status"] == "succeeded"
    assert res_q["reason"] == "query_succeeded"
    assert len(res_q["query_results"]) == 1
    assert res_q["query_results"][0]["state"] == "29.0"

    # Explicit condition TRUE: "거실 온도가 28도 이상이면 에어컨 냉방 25도로"
    ha.calls.clear()
    res_cond_true = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "거실 에어컨": {"hvac": "cool", "temperature": "v1"},
                "__condition__": {
                    "source": "거실 온도",
                    "operator": "gte",
                    "value": "v0",
                    "unit": "°C",
                },
            }
        ),
        "거실 온도가 28도 이상이면 에어컨 냉방 25도로",
    )
    assert res_cond_true["status"] == "succeeded"
    assert res_cond_true.get("condition_result") is True
    assert res_cond_true["condition_evaluation"]["selection"] == "model_typed"
    assert len(ha.calls) == 1
    assert ha.calls[0][3] == {"temperature": 25, "hvac_mode": "cool"}

    # Explicit condition FALSE: sensor is 29, condition requires >= 35
    ha.calls.clear()
    res_cond_false = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "거실 에어컨": {"hvac": "cool", "temperature": "v1"},
                "__condition__": {
                    "source": "거실 온도",
                    "operator": "gte",
                    "value": "v0",
                    "unit": "°C",
                },
            }
        ),
        "거실 온도가 35도 이상이면 에어컨 냉방 25도로",
    )
    assert res_cond_false["status"] == "succeeded"
    assert res_cond_false["reason"] == "condition_not_met"
    assert res_cond_false.get("condition_result") is False
    assert len(ha.calls) == 0  # 0 physical calls!


def cond(source="거실 온도", operator="gte", value="v0", unit="none"):
    return {
        "source": source,
        "operator": operator,
        "value": value,
        "unit": unit,
    }


async def test_r1_condition_guard_and_unit_conversion(ha, store):
    ha.states["light.living"]["state"] = "on"
    store.set_policy({"domains": {"light": True, "switch": True, "sensor": True}, "entities": {}})

    # 1. Missing sensor in catalog -> model can select none -> fail closed, 0 calls
    ha.calls.clear()
    res_no_sensor = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"power": "turn_off"}, "__condition__": cond(source="없음")}),
        "거실 온도가 28도 이상이면 거실불 꺼줘",
    )
    assert res_no_sensor["status"] == "rejected"
    assert res_no_sensor["reason"] == "condition_evaluation_failed"
    assert len(ha.calls) == 0

    # 2. Sensor state unknown -> fail closed, 0 calls
    ha.registry.append({"entity_id": "sensor.living_temp", "id": "sens-lt"})
    ha.states["sensor.living_temp"] = {
        "state": "unknown",
        "attributes": {"friendly_name": "거실 온도", "device_class": "temperature"},
    }
    ha.calls.clear()
    res_unk_sensor = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"power": "turn_off"}, "__condition__": cond()}),
        "거실 온도가 28도 이상이면 거실불 꺼줘",
    )
    assert res_unk_sensor["status"] == "rejected"
    assert res_unk_sensor["reason"] == "condition_evaluation_failed"
    assert len(ha.calls) == 0

    # 3. Unit conversion: 70°F is 21.11°C, condition requires 28도 (Celsius) -> False, 0 calls
    ha.temperature_unit = "°C"
    ha.states["sensor.living_temp"] = {
        "state": "70.0",
        "attributes": {
            "friendly_name": "거실 온도",
            "device_class": "temperature",
            "unit_of_measurement": "°F",
        },
    }
    ha.calls.clear()
    res_unit_conv = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"power": "turn_off"}, "__condition__": cond()}),
        "거실 온도가 28도 이상이면 거실불 꺼줘",
    )
    assert res_unit_conv["status"] == "succeeded"
    assert res_unit_conv["reason"] == "condition_not_met"
    assert res_unit_conv.get("condition_result") is False
    assert len(ha.calls) == 0

    # 4. 28℃ representation parses and condition succeeds when 85°F (29.44°C) >= 28°C
    ha.states["sensor.living_temp"]["state"] = "85.0"
    ha.calls.clear()
    res_celsius_symbol = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"power": "turn_off"}, "__condition__": cond(unit="°C")}),
        "거실 온도가 28℃ 이상이면 거실불 꺼줘",
    )
    assert res_celsius_symbol["status"] == "succeeded"
    assert res_celsius_symbol.get("condition_result") is True
    assert len(ha.calls) == 1
    assert ha.calls[0] == ("light", "turn_off", "light.living")


async def test_r4_automation_skip_condition_and_stop_actions(ha, store):
    ha.services["automation"] = {"trigger": {}, "turn_off": {}, "turn_on": {}}
    ha.states["automation.morning"] = {"state": "on", "attributes": {"friendly_name": "아침 알림"}}
    ha.registry.append({"entity_id": "automation.morning", "id": "auto-1"})
    store.set_policy({"domains": {"automation": True}, "entities": {}})

    # Trigger passes skip_condition: False
    res_trig = await execute(
        ha,
        store,
        ScriptedProvider({"아침 알림": {"automation_action": "trigger"}}),
        "아침 알림 자동화 실행해줘",
    )
    assert res_trig["status"] == "succeeded"
    assert ha.calls[-1] == (
        "automation",
        "trigger",
        "automation.morning",
        {"skip_condition": False},
    )

    # Turn off passes stop_actions: True and is not no-oped even if off
    ha.states["automation.morning"]["state"] = "off"
    ha.calls.clear()
    res_off = await execute(
        ha,
        store,
        ScriptedProvider({"아침 알림": {"automation_action": "turn_off"}}),
        "아침 알림 자동화 꺼줘",
    )
    assert res_off["status"] == "succeeded"
    assert ha.calls[-1] == ("automation", "turn_off", "automation.morning", {"stop_actions": True})


def test_r5_capabilities_and_cover_protection(ha, store):
    # Fan with supported_features=0 (only on/off)
    ha.services["fan"] = {"turn_on": {}, "turn_off": {}, "set_percentage": {}, "oscillate": {}}
    ha.states["fan.basic"] = {
        "state": "off",
        "attributes": {"friendly_name": "기본 팬", "supported_features": 0},
    }
    ha.registry.append({"entity_id": "fan.basic", "id": "fan-b"})
    e_basic = next(
        e for e in Catalog(ha, {"fan": True}).entities.values() if e.entity_id == "fan.basic"
    )
    basic_opts = options_for(e_basic, literals("50프로"))
    assert "power" in basic_opts
    assert "percentage" not in basic_opts
    assert "oscillate" not in basic_opts

    # Fan with SET_SPEED (flag=1)
    ha.states["fan.speedy"] = {
        "state": "off",
        "attributes": {"friendly_name": "스피드 팬", "supported_features": 1},
    }
    ha.registry.append({"entity_id": "fan.speedy", "id": "fan-s"})
    e_speedy = next(
        e for e in Catalog(ha, {"fan": True}).entities.values() if e.entity_id == "fan.speedy"
    )
    speedy_opts = options_for(e_speedy, literals("50프로"))
    assert "percentage" in speedy_opts

    # Cover garage door protection
    ha.services["cover"] = {"open_cover": {}, "close_cover": {}}
    ha.states["cover.garage_door"] = {
        "state": "closed",
        "attributes": {
            "friendly_name": "차고문",
            "device_class": "garage",
            "supported_features": 3,
        },
    }
    ha.registry.append({"entity_id": "cover.garage_door", "id": "cov-gar"})
    e_gar = next(
        e
        for e in Catalog(ha, {"cover": True}).entities.values()
        if e.entity_id == "cover.garage_door"
    )
    act_gar = make_action(e_gar, {"cover_action": "open_cover"}, [])
    with pytest.raises(DecisionError, match="sensitive_cover_protected"):
        validate_fresh(e_gar, act_gar, ha.states["cover.garage_door"], ha.services)

    # Input text password mode protection: excluded from catalog entirely (FIX_05 R1)
    ha.services["input_text"] = {"set_value": {}}
    ha.states["input_text.pin"] = {
        "state": "secret",
        "attributes": {"friendly_name": "비밀번호", "mode": "password"},
    }
    ha.states["input_text.note"] = {
        "state": "plain",
        "attributes": {"friendly_name": "메모", "mode": "text"},
    }
    ha.registry.append({"entity_id": "input_text.pin", "id": "txt-pin"})
    ha.registry.append({"entity_id": "input_text.note", "id": "txt-note"})
    catalog_pts = Catalog(ha, {"input_text": True})
    assert all(e.entity_id != "input_text.pin" for e in catalog_pts.entities.values())
    note_entity = next(e for e in catalog_pts.entities.values() if e.entity_id == "input_text.note")
    assert "text_action" in options_for(note_entity, [])


def test_r6_conflicts_and_shortcuts_filtering(tmp_path):
    # 1. Fan conflicting actions
    ha_fake = FakeHA()
    ha_fake.services["fan"] = {"turn_on": {}, "turn_off": {}, "set_percentage": {}}
    ha_fake.states["fan.living"] = {
        "state": "on",
        "attributes": {"friendly_name": "거실팬", "supported_features": 1},
    }
    ha_fake.registry.append({"entity_id": "fan.living", "id": "fan-l"})
    e_fan = next(
        e for e in Catalog(ha_fake, {"fan": True}).entities.values() if e.entity_id == "fan.living"
    )
    with pytest.raises(DecisionError, match="conflicting_actions"):
        make_action(e_fan, {"power": "turn_off", "percentage": "v0"}, [{"id": "v0", "value": 50}])

    # 2. Extract message from command
    from fhc.actions import extract_message

    assert extract_message("거실 스피커로 '문이 열렸습니다'라고 방송해줘") == "문이 열렸습니다"
    assert (
        extract_message('거실 알림에 "빨래가 완료되었습니다"라고 보내줘') == "빨래가 완료되었습니다"
    )

    # 3. Store.recent_shortcuts filtering
    s = Store(tmp_path)
    # Insert a pure query
    s.insert("r1", "거실 온도 알려줘")
    s.save(
        "r1", {"status": "succeeded", "reason": "query_succeeded", "actions": [{"is_query": True}]}
    )
    # Insert a condition_not_met
    s.insert("r2", "거실 온도가 30도 이상이면 불 꺼줘")
    s.save(
        "r2",
        {
            "status": "succeeded",
            "reason": "condition_not_met",
            "condition_result": False,
            "actions": [],
        },
    )
    # Insert a text message
    s.insert("r3", "거실 알림에 '안녕' 보내줘")
    s.save(
        "r3",
        {
            "status": "succeeded",
            "reason": "ha_ack",
            "actions": [{"domain": "notify", "service": "send_message", "status": "sent"}],
        },
    )
    # Insert a valid physical device action
    s.insert("r4", "거실불 켜줘")
    s.save(
        "r4",
        {
            "status": "succeeded",
            "reason": "ha_ack",
            "actions": [{"domain": "light", "service": "turn_on", "status": "sent"}],
        },
    )

    shortcuts = s.recent_shortcuts()
    assert shortcuts == ["거실불 켜줘"]
    s.close()


# ==============================================================================
# FIX_04 Verification Tests (R1 ~ R5)
# ==============================================================================


async def test_fix04_r1_condition_guard_and_rejections(ha, store):
    ha.registry.append({"entity_id": "sensor.living_temp", "area_id": "living"})
    ha.states["sensor.living_temp"] = {
        "entity_id": "sensor.living_temp",
        "state": "29",
        "attributes": {
            "friendly_name": "거실 온도",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
        },
    }
    ha.states["light.living"]["state"] = "on"

    def provider(**cond_kw):
        return ScriptedProvider(
            {
                "천장등": "turn_off",
                "__condition__": {
                    "source": "거실 온도",
                    "operator": "gt",
                    "value": "v0",
                    "unit": "none",
                    **cond_kw,
                },
            }
        )

    # 1. Greater than: 29 > 28 -> executes turn_off
    res = await execute(ha, store, provider(), "거실 온도가 28도보다 높다면 거실불 꺼줘")
    assert res["status"] == "succeeded"
    assert res.get("condition_result") is True
    assert ha.calls == [("light", "turn_off", "light.living")]

    # 2. Threshold not met: temp is 27, asked > 28 -> condition_not_met, 0 calls
    ha.calls.clear()
    ha.states["sensor.living_temp"]["state"] = "27"
    res = await execute(ha, store, provider(), "거실 온도가 28도보다 높다면 거실불 꺼줘")
    assert res["status"] == "succeeded"
    assert res["reason"] == "condition_not_met"
    assert res.get("condition_result") is False
    assert len(ha.calls) == 0

    # 3. Boundary: "28도를 넘으면" is strictly greater; exactly 28 -> not met (FIX_05 R5)
    ha.calls.clear()
    ha.states["sensor.living_temp"]["state"] = "28"
    res = await execute(ha, store, provider(), "거실 온도가 28도를 넘으면 거실불 꺼줘")
    assert res["status"] == "succeeded"
    assert res["reason"] == "condition_not_met"
    assert res["condition_evaluation"]["operator"] == ">"
    assert len(ha.calls) == 0

    # 4. gte boundary: 28 이상 at exactly 28 -> executes
    ha.calls.clear()
    ha.states["light.living"]["state"] = "on"
    res = await execute(
        ha, store, provider(operator="gte"), "거실 온도가 28도 이상이면 거실불 꺼줘"
    )
    assert res["status"] == "succeeded"
    assert res.get("condition_result") is True
    assert ha.calls == [("light", "turn_off", "light.living")]

    # 5. Qualitative condition without threshold -> none selection -> 0 calls
    ha.calls.clear()
    res = await execute(ha, store, provider(operator="none"), "만약 거실 온도가 높다면 거실불 꺼줘")
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_evaluation_failed"
    assert len(ha.calls) == 0

    # 6. Negation condition -> backend refuses unsupported semantics even if operator slipped through
    ha.calls.clear()
    res = await execute(
        ha, store, provider(operator="lt"), "거실 온도가 28도 이상이 아니면 거실불 꺼줘"
    )
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_evaluation_failed"
    assert len(ha.calls) == 0

    # 7. Compound condition -> 0 calls
    ha.calls.clear()
    res = await execute(
        ha,
        store,
        provider(operator="gte"),
        "거실 온도가 28도 이상이고 습도가 70% 이상이면 거실불 꺼줘",
    )
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_evaluation_failed"
    assert len(ha.calls) == 0

    # 8. Untranslatable sensor unit 'K' -> rejected with an explicit unit code
    ha.calls.clear()
    ha.states["sensor.living_temp"]["attributes"]["unit_of_measurement"] = "K"
    res = await execute(ha, store, provider(unit="°C"), "거실 온도가 28도보다 높다면 거실불 꺼줘")
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_unit_unspecified"
    assert len(ha.calls) == 0

    # 9. Non-conditional names with '면': 장면/벽면 execute normally without condition path
    ha.states["sensor.living_temp"]["attributes"]["unit_of_measurement"] = "°C"
    ha.services["scene"] = {"turn_on": {}}
    ha.states["scene.movie"] = {
        "state": "scening",
        "attributes": {"friendly_name": "거실 장면"},
    }
    ha.registry.append({"entity_id": "scene.movie", "area_id": "living"})
    store.set_policy({"domains": {"scene": True, "light": True}, "entities": {}})
    ha.calls.clear()
    res_scene = await execute(
        ha,
        store,
        ScriptedProvider({"거실 장면": {"scene_action": "turn_on"}}),
        "거실 장면 실행해줘",
    )
    assert res_scene["status"] == "succeeded"
    assert res_scene.get("condition_result") is None
    assert ha.calls == [("scene", "turn_on", "scene.movie")]
    ha.calls.clear()
    res_wall = await execute(ha, store, ScriptedProvider({"천장등": "turn_off"}), "벽면 조명 꺼줘")
    assert res_wall["status"] == "succeeded"
    assert res_wall.get("condition_result") is None


async def test_fix04_r2_controllable_domain_query_and_policy_separation(ha, store):
    ha.registry.append({"entity_id": "vacuum.living", "area_id": "living"})
    ha.states["vacuum.living"] = {
        "entity_id": "vacuum.living",
        "state": "docked",
        "attributes": {"friendly_name": "청소기"},
    }
    ha.services["vacuum"] = {"start": {}, "return_to_base": {}}
    store.set_policy({"domains": {"vacuum": True, "light": True, "switch": True}, "entities": {}})

    # 1. Query controllable entity unconditionally in options_for
    c = Catalog(ha, store.policy())
    vac_entity = next(e for e in c.entities.values() if e.entity_id == "vacuum.living")
    opts = options_for(vac_entity, literals("청소기 상태 어때"))
    assert "query" in opts
    assert "vacuum_action" in opts

    # Query via execute -> returns query_results, 0 calls
    res = await execute(
        ha,
        store,
        ScriptedProvider({"청소기": {"query": "query_state"}}),
        "청소기 상태 어때",
    )
    assert res["status"] == "succeeded"
    assert res.get("query_results")
    assert res["query_results"][0]["state"] == "docked"
    assert len(ha.calls) == 0

    # 2. Policy separation: vacuum write=False, read=True
    policy = store.policy()
    store.set_policy(
        {
            "domains": {**policy.domains, "vacuum": False},
            "read_domains": {"vacuum": True},
            "entities": policy.entities,
        }
    )

    c_read_only = Catalog(ha, store.policy())
    vac_ro = next(e for e in c_read_only.entities.values() if e.entity_id == "vacuum.living")
    assert vac_ro.read_allowed is True
    assert vac_ro.write_allowed is False
    opts_ro = options_for(vac_ro, literals("청소기"))
    assert "query" in opts_ro
    assert "vacuum_action" not in opts_ro

    # Query succeeds under read-only policy
    res_query = await execute(
        ha,
        store,
        ScriptedProvider({"청소기": {"query": "query_state"}}),
        "청소기 상태 어때",
    )
    assert res_query["status"] == "succeeded"
    assert res_query["query_results"][0]["state"] == "docked"


async def test_fix04_r3_multi_attributes_and_step_and_script_restart(ha, store):
    store.set_policy(
        {
            "domains": {"fan": True, "input_number": True, "script": True, "light": True},
            "entities": {},
        }
    )

    # 1. Multi-attribute fan: speed + oscillate
    ha.registry.append({"entity_id": "fan.living", "area_id": "living"})
    ha.states["fan.living"] = {
        "entity_id": "fan.living",
        "state": "on",
        "attributes": {
            "friendly_name": "선풍기",
            "percentage": 20,
            "oscillating": False,
            "speed_count": 100,
        },
    }
    ha.services["fan"] = {
        "set_percentage": {},
        "oscillate": {},
        "turn_on": {},
        "turn_off": {},
    }

    c = Catalog(ha, store.policy())
    fan_entity = next(e for e in c.entities.values() if e.entity_id == "fan.living")
    actions = make_actions(
        fan_entity,
        {"percentage": "v0", "oscillate": "oscillate_on"},
        [{"id": "v0", "value": 50}],
    )
    assert len(actions) == 2
    assert actions[0]["service"] == "set_percentage"
    assert actions[0]["service_data"] == {"percentage": 50}
    assert actions[1]["service"] == "oscillate"
    assert actions[1]["service_data"] == {"oscillating": True}

    # 2. Number step validation: step=2, value 3 fails, value 4 succeeds
    ha.registry.append({"entity_id": "input_number.target", "area_id": "living"})
    ha.states["input_number.target"] = {
        "entity_id": "input_number.target",
        "state": "0",
        "attributes": {"friendly_name": "목표값", "min": 0, "max": 10, "step": 2},
    }
    ha.services["input_number"] = {"set_value": {}}
    c2 = Catalog(ha, store.policy())
    num_entity = next(e for e in c2.entities.values() if e.entity_id == "input_number.target")
    with pytest.raises(Exception, match="number_step_invalid"):
        make_actions(num_entity, {"number_value": "v0"}, [{"id": "v0", "value": 3}])
    actions_valid = make_actions(num_entity, {"number_value": "v0"}, [{"id": "v0", "value": 4}])
    assert actions_valid[0]["service_data"] == {"value": 4.0}

    # 3. Script turn_on in state 'on' is NOT already_in_state
    ha.registry.append({"entity_id": "script.welcome", "area_id": "living"})
    ha.states["script.welcome"] = {
        "entity_id": "script.welcome",
        "state": "on",
        "attributes": {"friendly_name": "환영 스크립트"},
    }
    ha.services["script"] = {"turn_on": {}}
    c3 = Catalog(ha, store.policy())
    script_entity = next(e for e in c3.entities.values() if e.entity_id == "script.welcome")
    action = make_actions(script_entity, {"script_action": "turn_on"})[0]
    assert not is_already_in_state(action, ha.states["script.welcome"])


def test_fix04_r4_message_extraction_and_diagnostics_export(tmp_path, monkeypatch):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FHC_STANDALONE_TOKEN", raising=False)
    # 1. extract_message tests
    assert extract_message("입력란에 오늘 저녁 7시 회의라고 입력해줘") == "오늘 저녁 7시 회의"
    assert extract_message("거실 알림에 안녕 보내줘") == "안녕"
    with pytest.raises(Exception, match="invalid_message_span"):
        extract_message("그냥 켜줘")

    # 2. Diagnostics export endpoint with sensitive redaction & typed DTO
    ha_fake = FakeHA()
    ha_fake.services["input_text"] = {"set_value": {}}
    ha_fake.states["input_text.pin"] = {
        "state": "1234",
        "attributes": {"friendly_name": "PIN", "mode": "password"},
    }
    store_fake = Store(tmp_path)

    async def mock_admin(uid):
        return uid == "admin-1"

    # Save a record with sensitive query state
    store_fake.insert("req-sens", "비밀번호 확인")
    store_fake.save(
        "req-sens",
        {
            "id": "req-sens",
            "text": "비밀번호 확인",
            "status": "succeeded",
            "condition_evaluation": {
                "entity_id": "sensor.living_temp",
                "sensor_name": "거실 온도",
                "raw_value": "25.0",
                "sensor_unit": "°C",
                "observed_value": 25.0,
                "observed_unit": "°C",
                "target_value": 24.0,
                "target_unit": "°C",
                "operator": ">",
                "result": True,
            },
            "query_results": [{"entity_id": "input_text.pin", "name": "PIN", "state": "1234"}],
            "decisions": {"천장등": {"choice": "turn_off", "probability": 0.98}},
            "model_trace": [
                {
                    "provider": "openrouter",
                    "requested_model": "test-m",
                    "returned_model": "test-m",
                }
            ],
            "actions": [],
        },
    )

    with TestClient(app, client=("172.30.32.2", 1)) as c:
        app.state.ha = ha_fake
        app.state.store = store_fake
        app.state.ha.is_admin = mock_admin
        res = c.get(
            "/api/history/export?include_text=true",
            headers={"X-Remote-User-Id": "admin-1"},
        )
        import io
        import zipfile

        assert res.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        assert "requests.jsonl" in zf.namelist()
        lines = zf.read("requests.jsonl").decode("utf-8").strip().splitlines()
        requests = [json.loads(line) for line in lines]
        assert len(requests) >= 1
        req = next(r for r in requests if r["id"] == "req-sens")
        assert req["condition_evaluation"]["operator"] == ">"
        assert req["decisions"]["천장등"]["choice"] == "turn_off"
        assert req["model_trace"][0]["requested_model"] == "test-m"
        # Sensitive PIN state must be masked even with include_text=true!
        assert req["query_results"][0]["state"] == "[REDACTED_SENSITIVE]"
    store_fake.close()


async def test_fix04_r5_bc_services_and_domain_counts(ha, store):
    # Vacuum fan speed
    ha.registry.append({"entity_id": "vacuum.robot", "id": "vac-1"})
    ha.states["vacuum.robot"] = {
        "entity_id": "vacuum.robot",
        "state": "cleaning",
        "attributes": {"friendly_name": "로봇청소기", "fan_speed_list": ["standard", "max"]},
    }
    ha.services["vacuum"] = {"set_fan_speed": {}, "start": {}}
    store.set_policy({"domains": {"vacuum": True}, "entities": {}})

    c = Catalog(ha, store.policy())
    vac_entity = next(e for e in c.entities.values() if e.entity_id == "vacuum.robot")
    opts = options_for(vac_entity, [])
    assert "fan_speed" in opts

    actions = make_actions(vac_entity, {"fan_speed": "max"})
    assert actions[0]["service"] == "set_fan_speed"
    assert actions[0]["service_data"] == {"fan_speed": "max"}

    # Select step
    ha.registry.append({"entity_id": "select.mode", "id": "sel-1"})
    ha.states["select.mode"] = {
        "entity_id": "select.mode",
        "state": "eco",
        "attributes": {"friendly_name": "모드선택", "options": ["eco", "comfort", "boost"]},
    }
    ha.services["select"] = {
        "select_option": {},
        "select_next": {},
        "select_previous": {},
        "select_first": {},
        "select_last": {},
    }
    store.set_policy({"domains": {"select": True}, "entities": {}})
    c2 = Catalog(ha, store.policy())
    sel_entity = next(e for e in c2.entities.values() if e.entity_id == "select.mode")
    assert "select_step" in options_for(sel_entity, [])
    act_step = make_actions(sel_entity, {"select_step": "next"})
    assert act_step[0]["service"] == "select_next"

    # Input datetime
    ha.registry.append({"entity_id": "input_datetime.wake", "id": "dt-1"})
    ha.states["input_datetime.wake"] = {
        "entity_id": "input_datetime.wake",
        "state": "07:00:00",
        "attributes": {"friendly_name": "기상시간", "has_date": False, "has_time": True},
    }
    ha.services["input_datetime"] = {"set_datetime": {}}
    store.set_policy({"domains": {"input_datetime": True}, "entities": {}})
    c3 = Catalog(ha, store.policy())
    dt_entity = next(e for e in c3.entities.values() if e.entity_id == "input_datetime.wake")

    # FIX_05 R4: set_datetime must bind a real time token; empty payloads are rejected.
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI

    from fhc.actions import temporal_tokens as _tt

    now = _dt(2026, 10, 14, 9, 0, tzinfo=_ZI("Asia/Seoul"))
    text = "기상시간 08:00으로 설정해줘"
    temporal = _tt(text, now=now)
    opts = options_for(dt_entity, literals(text), temporal=temporal)
    assert "datetime_action" in opts and "datetime_time_value" in opts
    time_tok = next(x for x in temporal if x["kind"] == "time")
    assert time_tok["clock"] == "08:00"
    with pytest.raises(Exception, match="datetime_value_required"):
        make_actions(dt_entity, {"datetime_action": "set_datetime"})
    act_dt = make_actions(
        dt_entity,
        {"datetime_action": "set_datetime", "datetime_time_value": time_tok["id"]},
        temporal=temporal,
        now=now,
    )
    assert act_dt[0]["service"] == "set_datetime"
    assert act_dt[0]["service_data"] == {"time": "08:00:00"}

    # has_time=False must reject a time token.
    ha.states["input_datetime.wake"]["attributes"]["has_time"] = False
    c_ro = Catalog(ha, store.policy())
    dt_date_only = next(e for e in c_ro.entities.values() if e.entity_id == "input_datetime.wake")
    with pytest.raises(Exception, match="datetime_value_invalid"):
        make_actions(
            dt_date_only,
            {"datetime_action": "set_datetime", "datetime_time_value": time_tok["id"]},
            temporal=temporal,
            now=now,
        )


# ==============================================================================
# FIX_05 Verification Tests (R1 ~ R6)
# ==============================================================================


def add_input_text_password(ha):
    ha.services["input_text"] = {"set_value": {}}
    ha.states["input_text.note"] = {
        "state": "PRIVATE_PASSWORD_MARKER",
        "attributes": {"friendly_name": "기록", "mode": "password"},
    }
    ha.registry.append({"entity_id": "input_text.note", "id": "txt-note"})


async def test_fix05_r1_password_never_reaches_model_or_query(ha, store):
    add_input_text_password(ha)
    store.set_policy(
        {
            "domains": {"input_text": True, "light": True, "switch": True},
            "read_domains": {},
            "entities": {},
        }
    )
    provider = ScriptedProvider({"기록": {"query": "query_state"}})
    result = await execute(ha, store, provider, "기록 값 알려줘")
    # Excluded at catalog build: no option, no plan, no query result.
    assert result["status"] == "rejected"
    assert not result.get("query_results")
    for state, questions in provider.inputs:
        blob = json.dumps(state, ensure_ascii=False) + json.dumps(questions, ensure_ascii=False)
        assert "PRIVATE_PASSWORD_MARKER" not in blob
        assert "input_text.note" not in blob

    # Backend defenses even if a crafted action appears.
    from fhc.catalog import Entity

    crafted = Entity(
        ref="e99",
        entity_id="input_text.note",
        name="기록",
        aliases=(),
        domain="input_text",
        area="거실",
        area_aliases=(),
        device="",
        state="PRIVATE_PASSWORD_MARKER",
        features={"services": ["set_value"], "mode": "password"},
    )
    with pytest.raises(DecisionError, match="sensitive_input_protected"):
        make_actions(crafted, {"query": "query_state"})
    action = dict(
        entity_id="input_text.note",
        name="기록",
        domain="input_text",
        service="query_state",
        service_data={},
        ref="e99",
        status="pending",
        selected={},
        access="read",
        is_query=True,
        return_response=False,
        temperature_unit=None,
    )
    with pytest.raises(DecisionError, match="sensitive_input_protected"):
        validate_fresh(crafted, action, ha.states["input_text.note"], ha.services)


def test_fix05_r1_read_denied_query_blocked_candidate_and_backend(ha, store):
    store.set_policy(
        {
            "domains": {"light": True, "switch": True},
            "read_domains": {"light": False},
            "entities": {},
        }
    )
    c = Catalog(ha, store.policy())
    light_entity = next(e for e in c.entities.values() if e.entity_id == "light.living")
    assert light_entity.read_allowed is False
    assert light_entity.write_allowed is True
    assert "query" not in options_for(light_entity, literals("거실불 상태 알려줘"))
    with pytest.raises(DecisionError, match="read_policy_denied"):
        make_actions(light_entity, {"query": "query_state"})


async def test_fix05_r2_read_denied_engine_never_executes_query(ha, store):
    store.set_policy(
        {
            "domains": {"light": True, "switch": True},
            "read_domains": {"light": False},
            "entities": {},
        }
    )
    result = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"query": "query_state"}}),
        "거실불 상태 알려줘",
    )
    assert result["status"] == "rejected"
    assert not result.get("query_results")
    assert len(ha.calls) == 0
    assert len(ha.response_calls) == 0


def test_fix05_r2_personal_domains_require_explicit_optin(ha, store):
    for eid in ("person.lee", "device_tracker.phone", "zone.home"):
        ha.states[eid] = {"state": "home", "attributes": {"friendly_name": eid}}
        ha.registry.append({"entity_id": eid, "id": eid + "-id"})
    p = store.policy()
    assert p.is_domain_allowed("sensor", access="read") is True
    assert p.is_domain_allowed("weather", access="read") is True
    assert p.is_domain_allowed("person", access="read") is False
    assert p.is_domain_allowed("device_tracker", access="read") is False
    assert p.is_domain_allowed("zone", "read") is False
    assert p.is_domain_allowed("calendar", access="read") is False
    assert p.is_domain_allowed("todo", access="read") is False
    c = Catalog(ha, p)
    assert all(e.domain not in {"person", "device_tracker", "zone"} for e in c.entities.values())
    # Explicit opt-in only
    store.set_policy(
        {"domains": p.domains, "read_domains": {"person": True}, "entities": p.entities}
    )
    c2 = Catalog(ha, store.policy())
    assert any(e.entity_id == "person.lee" for e in c2.entities.values())


def test_fix05_r2_partial_policy_writes_preserve_read_settings(store):
    store.set_policy(
        {
            "domains": {"light": True, "switch": True},
            "read_domains": {"light": False, "sensor": True},
            "entities": {
                "light.living": {
                    "enabled": True,
                    "read_enabled": False,
                    "identity": "stable",
                }
            },
        }
    )
    # Unrelated domain-only write must not drop read_domains (FIX_05 R2 scenario 2).
    store.set_policy(
        {
            "domains": {"light": True, "switch": False},
            "entities": store.policy().entities,
        }
    )
    p = store.policy()
    assert p.read_domains == {"light": False, "sensor": True}
    assert p.is_allowed("light", "light.living", "stable", access="read") is False

    # Entity write toggle keeps its read_enabled and identity.
    store.set_entity_policy("light.living", False, "stable")
    p2 = store.policy()
    entry = p2.entities["light.living"]
    assert entry["enabled"] is False
    assert entry["read_enabled"] is False
    assert entry["identity"] == "stable"
    assert p2.is_domain_allowed("sensor", access="read") is True

    # Rename preserves read_enabled (scenario 3).
    class MockHA:
        def __init__(self, registry):
            self.registry = registry
            self.renames = {}

    store.reconcile_registry(MockHA([{"entity_id": "light.new", "id": "stable"}]))
    p3 = store.policy()
    assert "light.new" in p3.entities
    assert p3.entities["light.new"]["read_enabled"] is False
    assert p3.read_domains == {"light": False, "sensor": True}


def test_fix05_r2_invalid_policy_types_and_keys_rejected(store):
    with pytest.raises(ValueError, match="invalid_policy"):
        store.set_policy({"domains": {"light": "yes"}, "entities": {}})
    with pytest.raises(ValueError, match="invalid_policy"):
        store.set_policy({"domains": {}, "read_domains": {"light": 1}, "entities": {}})
    with pytest.raises(ValueError, match="invalid_policy"):
        store.set_policy({"domains": {}, "entities": {"x.y": {"enabled": True, "role": "admin"}}})
    with pytest.raises(ValueError, match="invalid_policy"):
        store.set_policy({"domains": {}, "entities": {}, "unknown_section": {}})


def test_fix05_r2_policy_api_roundtrip(ha, tmp_path, monkeypatch):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    store_fake = Store(tmp_path)
    with TestClient(app, client=("172.30.32.2", 1)) as c:

        async def mock_admin(uid):
            return uid == "admin-1"

        app.state.ha, app.state.store = ha, store_fake
        app.state.ha.is_admin = mock_admin
        headers = {"X-Remote-User-Id": "admin-1", "X-FHC-Request": "1"}

        assert (
            c.put(
                "/api/policy", json={"read_domains": {"light": False}}, headers=headers
            ).status_code
            == 200
        )
        assert (
            c.put(
                "/api/policy",
                json={"entities": {"light.bedroom": {"read_enabled": False}}},
                headers=headers,
            ).status_code
            == 200
        )
        # An unrelated write-only save preserves both read settings.
        res = c.put("/api/policy", json={"domains": {"switch": False}}, headers=headers)
        assert res.status_code == 200
        pol = res.json()["policy"]
        assert pol["read_domains"] == {"light": False}
        assert pol["entities"]["light.bedroom"]["read_enabled"] is False

        # Unknown fields / wrong types are rejected, never silently allowed.
        assert c.put("/api/policy", json={"junk": True}, headers=headers).status_code == 422
        assert (
            c.put(
                "/api/policy",
                json={"entities": {"light.bedroom": {"bogus": True}}},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            c.put(
                "/api/policy", json={"read_domains": {"light": "no"}}, headers=headers
            ).status_code
            == 422
        )
    store_fake.close()


async def test_fix05_r2_readonly_calendar_get_events_end_to_end(ha, store):
    ha.services["calendar"] = {"get_events": {}, "create_event": {}}
    ha.states["calendar.local"] = {"state": "on", "attributes": {"friendly_name": "내 일정"}}
    ha.registry.append({"entity_id": "calendar.local", "id": "cal-1"})
    # Real Core 2026.10 calendar contract: payload is {"events": [...]} with ISO strings.
    ha.responses[("calendar", "get_events")] = {
        "events": [{"summary": "치과", "start": "2026-10-15T10:00:00+09:00"}]
    }
    store.set_policy(
        {
            "domains": {"calendar": False, "light": True},
            "read_domains": {"calendar": True},
            "entities": {},
        }
    )
    c = Catalog(ha, store.policy())
    cal = next(e for e in c.entities.values() if e.entity_id == "calendar.local")
    assert cal.write_allowed is False and cal.read_allowed is True
    opts = options_for(cal, literals("내일 일정 알려줘"))
    assert "calendar_action" in opts and "calendar_range" in opts
    assert "create_event" not in opts["calendar_action"]  # write-only option gone

    res = await execute(
        ha,
        store,
        ScriptedProvider(
            {"내 일정": {"calendar_action": "get_events", "calendar_range": "tomorrow"}}
        ),
        "내일 일정 알려줘",
    )
    assert res["status"] == "succeeded"
    assert res["reason"] == "query_succeeded"
    assert len(ha.calls) == 0  # no control dispatch
    dom, svc, eid, data = ha.response_calls[-1]
    assert (dom, svc, eid) == ("calendar", "get_events", "calendar.local")
    # The engine resolves "tomorrow" against the live Asia/Seoul clock; assert the
    # same window instead of pinning the date the test was written on.
    seoul_now = datetime.now(ZoneInfo("Asia/Seoul"))
    tomorrow = (seoul_now + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (seoul_now + timedelta(days=2)).strftime("%Y-%m-%d")
    assert data["start_date_time"].startswith(tomorrow)
    assert data["end_date_time"].startswith(day_after)
    assert "치과" in res["actions"][0]["query_result"]
    assert res["actions"][0]["response_contract"] == "ok"


async def test_fix05_r3_tts_requires_discovered_output_target(ha, store):
    ha.services["tts"] = {"speak": {}}
    ha.services["media_player"] = {"turn_on": {}, "turn_off": {}}
    ha.states["tts.google"] = {"state": "idle", "attributes": {"friendly_name": "구글 TTS"}}
    ha.states["media_player.living"] = {
        "state": "idle",
        "attributes": {"friendly_name": "거실 스피커"},
    }
    ha.states["media_player.bedroom"] = {
        "state": "idle",
        "attributes": {"friendly_name": "침실 스피커"},
    }
    ha.registry.extend(
        [
            {"entity_id": "tts.google", "id": "tts-1"},
            {"entity_id": "media_player.living", "id": "mp-1"},
            {"entity_id": "media_player.bedroom", "id": "mp-2"},
        ]
    )
    store.set_policy({"domains": {"tts": True, "media_player": True}, "entities": {}})
    res = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "구글 TTS": {"text_action": "apply"},
                "침실 스피커": {"broadcast_output": "output"},
            }
        ),
        "침실 스피커로 '안녕'이라고 방송해줘",
    )
    assert res["status"] == "succeeded"
    call = ha.calls[-1]
    assert call[0] == "tts" and call[1] == "speak"
    assert call[3]["media_player_entity_id"] == "media_player.bedroom"
    assert "media_player.living_room" not in json.dumps(call[3])
    assert res["actions"][0]["secondary"]["entity_id"] == "media_player.bedroom"

    # Missing/ambiguous target: zero transmissions, no fixed fallback.
    ha.calls.clear()
    res_none = await execute(
        ha,
        store,
        ScriptedProvider({"구글 TTS": {"text_action": "apply"}}),
        "'안녕'이라고 방송해줘",
    )
    assert res_none["status"] == "rejected"
    assert res_none["reason"] == "tts_output_target_required"
    assert len(ha.calls) == 0

    # Output excluded by policy: option not offered; crafted selection is denied.
    store.set_policy(
        {
            "domains": {"tts": True, "media_player": True, "light": True},
            "read_domains": {"media_player": True},
            "entities": {"media_player.bedroom": {"enabled": False, "identity": "mp-2"}},
        }
    )
    res_excluded = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "구글 TTS": {"text_action": "apply"},
                "침실 스피커": {"broadcast_output": "output"},
            }
        ),
        "침실 스피커로 '안녕'이라고 방송해줘",
    )
    assert res_excluded["status"] == "rejected"
    assert res_excluded["reason"] == "tts_output_target_required"
    assert len(ha.calls) == 0
    from fhc.catalog import Entity

    tts_entity = Entity(
        ref="e0",
        entity_id="tts.google",
        name="구글 TTS",
        aliases=(),
        domain="tts",
        area="",
        area_aliases=(),
        device="",
        state="idle",
        features={"services": ["speak"]},
    )
    denied_mp = Entity(
        ref="e9",
        entity_id="media_player.bedroom",
        name="침실 스피커",
        aliases=(),
        domain="media_player",
        area="",
        area_aliases=(),
        device="",
        state="idle",
        features={"services": ["turn_on"]},
        write_allowed=False,
    )
    with pytest.raises(DecisionError, match="output_policy_denied"):
        make_actions(
            tts_entity,
            {"text_action": "apply", "tts_output": "e9"},
            text="'안녕'이라고 방송해",
            scope={"e9": denied_mp},
        )

    # Unavailable output device fails in preflight before any dispatch.
    store.set_policy({"domains": {"tts": True, "media_player": True}, "entities": {}})
    ha.states["media_player.bedroom"]["state"] = "unavailable"
    ha.calls.clear()
    res_unavail = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "구글 TTS": {"text_action": "apply"},
                "침실 스피커": {"broadcast_output": "output"},
            }
        ),
        "침실 스피커로 '안녕'이라고 방송해줘",
    )
    assert res_unavail["status"] == "rejected"
    assert res_unavail["reason"] == "output_entity_unavailable"
    assert len(ha.calls) == 0


async def test_fix05_r4_calendar_create_and_weather_forecast_typed(ha, store):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fhc.actions import temporal_tokens

    now = datetime(2026, 10, 14, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    ha.services["calendar"] = {"get_events": {}, "create_event": {}}
    ha.states["calendar.local"] = {"state": "on", "attributes": {"friendly_name": "내 일정"}}
    ha.registry.append({"entity_id": "calendar.local", "id": "cal-1"})
    ha.services["weather"] = {"get_forecasts": {}}
    ha.states["weather.home"] = {
        "state": "sunny",
        "attributes": {"friendly_name": "집 날씨", "supported_features": 3},
    }
    ha.registry.append({"entity_id": "weather.home", "id": "wx-1"})
    store.set_policy({"domains": {"calendar": True, "weather": True}, "entities": {}})

    c = Catalog(ha, store.policy())
    cal = next(e for e in c.entities.values() if e.entity_id == "calendar.local")
    wx = next(e for e in c.entities.values() if e.entity_id == "weather.home")

    text = "내일 14:30부터 16시까지 '팀 회의'라고 일정 만들어줘"
    temporal = temporal_tokens(text, now=now)
    opts = options_for(cal, literals(text), temporal=temporal)
    assert "calendar_day" in opts and "calendar_time" in opts
    toks = [x for x in temporal if x["kind"] == "time"]
    time_tok, end_tok = toks[0], toks[1]
    assert time_tok["clock"] == "14:30" and end_tok["clock"] == "16:00"
    act = make_actions(
        cal,
        {
            "calendar_action": "create_event",
            "calendar_day": "tomorrow",
            "calendar_time": time_tok["id"],
            "calendar_end_time": end_tok["id"],
        },
        temporal=temporal,
        now=now,
        text=text,
    )[0]
    assert act["service_data"]["summary"] == "팀 회의"
    assert act["service_data"]["start_date_time"].startswith("2026-10-15T14:30")
    assert act["service_data"]["end_date_time"].startswith("2026-10-15T16:00")
    assert "duration" not in act["service_data"]
    # A timed event without an explicit end is refused: no invented 1-hour default.
    with pytest.raises(DecisionError, match="calendar_end_required"):
        make_actions(
            cal,
            {
                "calendar_action": "create_event",
                "calendar_day": "tomorrow",
                "calendar_time": time_tok["id"],
            },
            temporal=temporal,
            now=now,
            text=text,
        )
    with pytest.raises(DecisionError, match="calendar_start_required"):
        make_actions(
            cal,
            {"calendar_action": "create_event", "calendar_time": time_tok["id"]},
            temporal=temporal,
            now=now,
            text=text,
        )
    # A model-selected day token never becomes a guessed calendar date:
    with pytest.raises(DecisionError, match="calendar_start_required"):
        make_actions(
            cal,
            {"calendar_action": "create_event"},
            temporal=temporal,
            now=now,
            text=text,
        )
    with pytest.raises(DecisionError, match="calendar_range_required"):
        make_actions(
            cal,
            {"calendar_action": "get_events"},
            temporal=temporal,
            now=now,
            text=text,
        )

    # Weather forecast is ONE exclusive choice from discovered support (FIX_07 R1).
    wx_opts = options_for(wx, literals("시간별 날씨 어때"))
    assert set(wx_opts["weather_action"]) >= {
        "none",
        "query_state",
        "get_forecasts_hourly",
        "get_forecasts_daily",
    }
    assert "get_forecasts_twice_daily" not in wx_opts["weather_action"]
    act_h = make_actions(wx, {"weather_action": "get_forecasts_hourly"})[0]
    assert act_h["service_data"] == {"type": "hourly"}
    with pytest.raises(DecisionError, match="forecast_type_unsupported"):
        make_actions(wx, {"weather_action": "get_forecasts_twice_daily"})
    act_q = make_actions(wx, {"weather_action": "query_state"})[0]
    assert act_q["is_query"] is True

    ha.states["weather.home"]["attributes"]["supported_features"] = 0
    wx_none = next(
        e for e in Catalog(ha, store.policy()).entities.values() if e.entity_id == "weather.home"
    )
    opts_none = options_for(wx_none, literals("날씨 어때"))
    assert "weather_action" not in opts_none
    assert "query" in opts_none


async def test_fix05_r4_todo_uid_resolution_and_explicit_status(ha, store):
    ha.services["todo"] = {
        "get_items": {},
        "add_item": {},
        "update_item": {},
        "remove_item": {},
    }
    ha.states["todo.list"] = {
        "state": "needs_action",
        "attributes": {"friendly_name": "장보기 목록"},
    }
    ha.registry.append({"entity_id": "todo.list", "id": "todo-1"})
    store.set_policy({"domains": {"todo": True}, "entities": {}})
    ha.responses[("todo", "get_items")] = {
        "items": [{"uid": "u-42", "summary": "우유", "status": "needs_action"}]
    }

    provider_ok = ScriptedProvider(
        {"장보기 목록": {"todo_action": "update_item", "todo_status": "completed"}}
    )
    res = await execute(ha, store, provider_ok, "'우유' 완료로 수정해줘")
    assert res["status"] == "succeeded"
    call = ha.calls[-1]
    assert call[1] == "update_item"
    assert call[3] == {"item": "u-42", "status": "completed"}
    assert res["actions"][0]["todo_item_resolution"]["uid"] == "u-42"

    # needs_action (undo) must be expressible, not forced to completed.
    ha.calls.clear()
    res_undo = await execute(
        ha,
        store,
        ScriptedProvider(
            {"장보기 목록": {"todo_action": "update_item", "todo_status": "needs_action"}}
        ),
        "'우유' 완료 아닌 걸로 되돌려줘",
    )
    assert res_undo["status"] == "succeeded"
    assert ha.calls[-1][3]["status"] == "needs_action"

    # No explicit status -> never defaults to completed.
    ha.calls.clear()
    res_status = await execute(
        ha,
        store,
        ScriptedProvider({"장보기 목록": {"todo_action": "update_item"}}),
        "'우유' 수정해줘",
    )
    assert res_status["status"] == "rejected"
    assert res_status["reason"] == "todo_status_required"
    assert len(ha.calls) == 0

    # Ambiguous same-name items -> refuse.
    ha.calls.clear()
    ha.responses[("todo", "get_items")] = {
        "items": [
            {"uid": "u-1", "summary": "우유", "status": "needs_action"},
            {"uid": "u-2", "summary": "우유", "status": "needs_action"},
        ]
    }
    res_amb = await execute(ha, store, provider_ok, "'우유' 완료로 수정해줘")
    assert res_amb["status"] == "rejected"
    assert res_amb["reason"] == "todo_item_ambiguous"
    assert len(ha.calls) == 0

    # Unknown item -> refuse.
    ha.calls.clear()
    ha.responses[("todo", "get_items")] = {
        "items": [{"uid": "u-9", "summary": "계란", "status": "needs_action"}]
    }
    res_miss = await execute(ha, store, provider_ok, "'우유' 완료로 수정해줘")
    assert res_miss["status"] == "rejected"
    assert res_miss["reason"] == "todo_item_not_found"
    assert len(ha.calls) == 0


def test_fix05_r4_response_query_not_exempt_from_validation():
    from fhc.catalog import Entity

    e = Entity(
        ref="e0",
        entity_id="calendar.local",
        name="내 일정",
        aliases=(),
        domain="calendar",
        area="",
        area_aliases=(),
        device="",
        state="on",
        features={"services": ["get_events"]},
    )
    action = dict(
        entity_id="calendar.local",
        name="내 일정",
        domain="calendar",
        service="get_events",
        service_data={},
        ref="e0",
        status="pending",
        selected={},
        access="read",
        is_query=False,
        return_response=True,
        temperature_unit=None,
    )
    with pytest.raises(DecisionError, match="entity_unavailable"):
        validate_fresh(
            e, action, {"state": "unavailable", "attributes": {}}, {"calendar": {"get_events": {}}}
        )
    # Missing service in the fresh registry is an environment change, not a free pass.
    with pytest.raises(DecisionError, match="environment_changed"):
        validate_fresh(e, action, {"state": "on", "attributes": {}}, {"calendar": {}})


def test_fix05_r6_export_sanitizes_user_choices_and_keeps_safe_enums(
    ha, store, monkeypatch, tmp_path
):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    store.insert("req-choice", "모드 부스트로")
    rec = store.get("req-choice")[1]
    rec.update(
        status="succeeded",
        decisions={
            "e3_select_option": {"choice": "PRIVATE_ENUM_NAME", "probability": 0.98},
            "e0_power": {"choice": "turn_on", "probability": 0.99},
            "e1_temperature": {"choice": "v0", "probability": 0.97},
        },
        actions=[],
    )
    store.save("req-choice", rec)
    with TestClient(app, client=("172.30.32.2", 1)) as c:

        async def mock_admin(uid):
            return uid == "admin-1"

        app.state.ha, app.state.store = ha, store
        app.state.ha.is_admin = mock_admin
        import io
        import zipfile

        res = c.get("/api/history/export", headers={"X-Remote-User-Id": "admin-1"})
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        body = zf.read("requests.jsonl").decode("utf-8")
        assert "PRIVATE_ENUM_NAME" not in body
        exported = json.loads(body.strip())
        assert exported["decisions"]["e3_select_option"]["choice"] == "anon_choice_1"
        assert exported["decisions"]["e0_power"]["choice"] == "turn_on"
        assert exported["decisions"]["e1_temperature"]["choice"] == "v0"

        res_raw = c.get(
            "/api/history/export?include_text=true", headers={"X-Remote-User-Id": "admin-1"}
        )
        raw = json.loads(
            zipfile.ZipFile(io.BytesIO(res_raw.content))
            .read("requests.jsonl")
            .decode("utf-8")
            .strip()
        )
        assert raw["decisions"]["e3_select_option"]["choice"] == "PRIVATE_ENUM_NAME"


def test_fix05_r1_export_legacy_unclassified_history_conservative(ha, store, monkeypatch, tmp_path):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    add_input_text_password(ha)
    store.insert("req-legacy", "기록 값 알려줘")
    rec = store.get("req-legacy")[1]
    rec.update(
        status="succeeded",
        actions=[],
        query_results=[
            {"entity_id": "input_text.note", "name": "기록", "state": "PRIVATE_PASSWORD_MARKER"}
        ],
    )
    store.save("req-legacy", rec)
    with TestClient(app, client=("172.30.32.2", 1)) as c:

        async def mock_admin(uid):
            return uid == "admin-1"

        app.state.ha, app.state.store = ha, store
        app.state.ha.is_admin = mock_admin
        import io
        import zipfile

        # Mode-based redaction, not ID substring: marker absent even with include_text.
        res = c.get(
            "/api/history/export?include_text=true", headers={"X-Remote-User-Id": "admin-1"}
        )
        body = zipfile.ZipFile(io.BytesIO(res.content)).read("requests.jsonl").decode("utf-8")
        assert "PRIVATE_PASSWORD_MARKER" not in body
        exported = json.loads(body.strip())
        assert exported["query_results"][0]["state"] == "[REDACTED_SENSITIVE]"

        # A deleted entity without classification is also excluded from raw export.
        store.insert("req-deleted", "옛날 조회")
        rec2 = store.get("req-deleted")[1]
        rec2.update(
            status="succeeded",
            actions=[],
            query_results=[{"entity_id": "sensor.long_gone", "name": "x", "state": "21.5"}],
        )
        store.save("req-deleted", rec2)
        res2 = c.get(
            "/api/history/export?include_text=true&request_id=req-deleted",
            headers={"X-Remote-User-Id": "admin-1"},
        )
        rec3 = json.loads(
            zipfile.ZipFile(io.BytesIO(res2.content)).read("requests.jsonl").decode("utf-8").strip()
        )
        assert rec3["query_results"][0]["state"] == "[UNCLASSIFIED_STATE_EXCLUDED]"


async def test_fix05_r6_provider_trace_has_timings_and_question_counts():
    provider = Provider(Options(openrouter_api_key="test-only"))
    await provider.http.aclose()
    provider.http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "answers": {
                        k: {"type": "noul", "noul": 0.9} for k in json.loads(r.content)["questions"]
                    }
                },
            )
        )
    )
    await provider.decide({"c": 1}, {"a": {"type": "noul"}, "b": {"type": "noul"}})
    entry = provider.trace[-1]
    assert entry["questions"] == 2
    assert isinstance(entry["elapsed_ms"], int)
    assert "raw_prompt" not in entry and "body" not in entry
    await provider.close()


# ==============================================================================
# FIX_06 Verification Tests (R1 ~ R4)
# ==============================================================================


def test_fix06_r1_calendar_response_contract():
    from fhc.engine import format_response

    # Real Core shape: {"events": [...]} with ISO string starts.
    display, state = format_response(
        "calendar",
        "get_events",
        {"events": [{"summary": "실제 회의", "start": "2026-10-15T09:00:00+09:00"}]},
    )
    assert state == "ok"
    assert "실제 회의" in display and "2026-10-15T09:00" in display
    display, state = format_response("calendar", "get_events", {"events": []})
    assert (display, state) == ("일정이 없습니다.", "empty")
    # A schema error must never be reported as an empty successful list.
    display, state = format_response("calendar", "get_events", {"unexpected": 1})
    assert state == "malformed" and "형식" in display
    display, state = format_response("calendar", "get_events", "not-a-mapping")
    assert state == "malformed"
    # Old Google-style dict starts still parse.
    display, state = format_response(
        "calendar",
        "get_events",
        {"events": [{"summary": "구형", "start": {"dateTime": "2026-10-15T09:00:00+09:00"}}]},
    )
    assert state == "ok" and "구형" in display
    # todo/weather malformed separation
    assert format_response("todo", "get_items", {"wrong": 1})[1] == "malformed"
    assert format_response("weather", "get_forecasts", {"forecast": "oops"})[1] == "malformed"
    assert format_response("weather", "get_forecasts", {"forecast": []})[1] == "empty"


async def test_fix06_r1_engine_malformed_calendar_display(ha, store):
    ha.services["calendar"] = {"get_events": {}}
    ha.states["calendar.local"] = {"state": "on", "attributes": {"friendly_name": "내 일정"}}
    ha.registry.append({"entity_id": "calendar.local", "id": "cal-1"})
    ha.responses[("calendar", "get_events")] = {"unexpected_key": True}
    store.set_policy({"domains": {"calendar": True}, "entities": {}})
    res = await execute(
        ha,
        store,
        ScriptedProvider({"내 일정": {"calendar_action": "get_events", "calendar_range": "today"}}),
        "오늘 일정 알려줘",
    )
    assert res["status"] == "succeeded"
    action = res["actions"][0]
    assert action["response_contract"] == "malformed"
    assert "형식" in action["query_result"]


def test_fix06_r2_korean_time_tokens_and_pairs():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fhc.actions import temporal_tokens

    now = datetime(2026, 10, 14, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    toks = temporal_tokens("기상을 오후 8시 30분으로 설정해줘", now=now)
    t = next(x for x in toks if x["kind"] == "time")
    assert (t["hour"], t["minute"], t["clock"]) == (20, 30, "20:30")
    assert t["ambiguous_period"] is False
    toks = temporal_tokens("밤 10시에 알려줘", now=now)
    t = next(x for x in toks if x["kind"] == "time")
    assert t["ambiguous_period"] is True
    toks = temporal_tokens("10월 20일 08:00 일정", now=now)
    d = next(x for x in toks if x["kind"] == "month_day")
    assert d["date"] == "2026-10-20"
    t = next(x for x in toks if x["kind"] == "time")
    assert t["clock"] == "08:00"
    # 내일모레-style overlap: 모레 wins first, 내일 not double counted from it
    toks = temporal_tokens("모레 일정", now=now)
    assert [x["text"] for x in toks if x["kind"] == "day"] == ["모레"]


def test_fix06_r2_input_datetime_date_plus_time_and_ambiguity():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fhc.actions import temporal_tokens
    from fhc.catalog import Entity

    now = datetime(2026, 10, 14, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    e = Entity(
        ref="e0",
        entity_id="input_datetime.meet",
        name="모임 시각",
        aliases=(),
        domain="input_datetime",
        area="",
        area_aliases=(),
        device="",
        state="2026-01-01 00:00:00",
        features={"services": ["set_datetime"], "has_date": True, "has_time": True},
    )
    text = "모임 일시를 10월 20일 15:30으로 설정"
    temporal = temporal_tokens(text, now=now)
    d = next(x for x in temporal if x["kind"] == "month_day")
    t = next(x for x in temporal if x["kind"] == "time")
    opts = options_for(e, literals(text), temporal=temporal)
    assert "datetime_day_value" in opts and "datetime_time_value" in opts
    act = make_actions(
        e,
        {
            "datetime_action": "set_datetime",
            "datetime_day_value": d["id"],
            "datetime_time_value": t["id"],
        },
        temporal=temporal,
        now=now,
    )[0]
    assert act["service_data"] == {"datetime": "2026-10-20 15:30:00"}
    amb = next(x for x in temporal_tokens("밤 10시로 설정", now=now) if x["kind"] == "time")
    with pytest.raises(DecisionError, match="datetime_value_invalid"):
        make_actions(
            e,
            {"datetime_action": "set_datetime", "datetime_time_value": amb["id"]},
            temporal=[amb],
            now=now,
        )


def test_fix06_r2_timezone_unknown_blocks_time_writes():
    from datetime import datetime

    from fhc.catalog import Entity

    cal = Entity(
        ref="e0",
        entity_id="calendar.local",
        name="내 일정",
        aliases=(),
        domain="calendar",
        area="",
        area_aliases=(),
        device="",
        state="on",
        features={"services": ["get_events", "create_event"]},
    )
    naive = datetime(2026, 10, 14, 9, 0)
    with pytest.raises(DecisionError, match="timezone_unknown"):
        make_actions(
            cal,
            {"calendar_action": "get_events", "calendar_range": "today"},
            temporal=[],
            now=naive,
            text="오늘 일정",
        )
    with pytest.raises(DecisionError, match="timezone_unknown"):
        make_actions(
            cal,
            {"calendar_action": "get_events", "calendar_range": "today"},
            temporal=[],
            now=None,
            text="오늘 일정",
        )


async def test_fix06_r3_todo_ambiguity_rejects_before_first_write(ha, store):
    # Mixed command: light turn_off + todo update with duplicate summaries.
    ha.services["todo"] = {"get_items": {}, "update_item": {}}
    ha.states["todo.list"] = {
        "state": "needs_action",
        "attributes": {"friendly_name": "장보기 목록"},
    }
    ha.registry.append({"entity_id": "todo.list", "id": "todo-1"})
    store.set_policy({"domains": {"light": True, "todo": True}, "entities": {}})
    ha.responses[("todo", "get_items")] = {
        "items": [
            {"uid": "u-a", "summary": "우유", "status": "needs_action"},
            {"uid": "u-b", "summary": "우유", "status": "needs_action"},
        ]
    }
    res = await execute(
        ha,
        store,
        ScriptedProvider(
            {
                "천장등": {"power": "turn_off"},
                "장보기 목록": {"todo_action": "update_item", "todo_status": "completed"},
            }
        ),
        "거실불 끄고 장보기 목록에서 '우유' 완료해줘",
    )
    # The read (get_items) may happen, but NO control service was dispatched —
    # including the light that appears before the todo action.
    assert res["status"] == "rejected"
    assert res["reason"] == "todo_item_ambiguous"
    assert len(ha.calls) == 0
    assert all(a["status"] == "not_sent" for a in res["actions"])
    assert ha.response_calls  # read service call distinguishes lookup from write


def test_fix07_r3_time_date_literal_no_truncation():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fhc.actions import temporal_tokens

    now = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    # 오후 + HH:MM must read the meridian, not only the numeric part.
    toks = temporal_tokens("오후 8:30으로 설정", now=now)
    t = next(x for x in toks if x["kind"] == "time")
    assert (t["hour"], t["minute"]) == (20, 30)
    assert t["span"]  # full span including 오후
    assert toks[0]["text"] == "오후 8:30"

    # Explicit year is honoured verbatim.
    toks = temporal_tokens("2028년 10월 20일로 설정", now=now)
    d = next(x for x in toks if x["kind"] == "month_day")
    assert d["date"] == "2028-10-20"

    # Invalid minute invalidates the whole token: no truncated 20:00 candidate.
    toks = temporal_tokens("오후 8시 75분으로 설정", now=now)
    assert not [x for x in toks if x["kind"] == "time"]

    # Boundaries: 오전 12시 = 00:00, 오후 12시 = 12:00, 연말 date without year.
    toks = temporal_tokens("오전 12시 정각", now=now)
    assert next(x for x in toks if x["kind"] == "time")["clock"] == "00:00"
    toks = temporal_tokens("오후 12시에", now=now)
    assert next(x for x in toks if x["kind"] == "time")["clock"] == "12:00"
    toks = temporal_tokens("12월 31일로 설정", now=now)
    assert next(x for x in toks if x["kind"] == "month_day")["date"] == "2026-12-31"
    # Already-passed month/day rolls to next year; explicit 2월 30일 yields no token.
    toks = temporal_tokens("1월 5일로 설정", now=now)
    assert next(x for x in toks if x["kind"] == "month_day")["date"] == "2027-01-05"
    toks = temporal_tokens("2월 30일로 설정", now=now)
    assert not [x for x in toks if x["kind"] == "month_day"]

    # Binding the truncated-value candidates must be impossible end-to-end:
    from fhc.catalog import Entity

    e = Entity(
        ref="e0",
        entity_id="input_datetime.wake",
        name="기상",
        aliases=(),
        domain="input_datetime",
        area="",
        area_aliases=(),
        device="",
        state="00:00:00",
        features={"services": ["set_datetime"], "has_date": False, "has_time": True},
    )
    text = "오후 8:30으로 설정"
    temporal = temporal_tokens(text, now=now)
    opts = options_for(e, literals(text), temporal=temporal)
    tid = next(iter(k for k in opts["datetime_time_value"] if k != "none"))
    act = make_actions(
        e,
        {"datetime_action": "set_datetime", "datetime_time_value": tid},
        temporal=temporal,
        now=now,
    )[0]
    assert act["service_data"] == {"time": "20:30:00"}


def test_fix07_r4_explicit_power_preserved_with_attributes():
    from fhc.catalog import Entity

    def ent(domain, services, features_extra=None, state="off"):
        f = {"services": services}
        f.update(features_extra or {})
        return Entity(
            ref="e0",
            entity_id=f"{domain}.x",
            name="장치",
            aliases=(),
            domain=domain,
            area="",
            area_aliases=(),
            device="",
            state=state,
            features=f,
        )

    fan = ent("fan", ["turn_on", "turn_off", "oscillate"], {"supported_features": 2})
    acts = make_actions(fan, {"power": "turn_on", "oscillate": "oscillate_on"})
    assert [a["service"] for a in acts] == ["turn_on", "oscillate"]
    with pytest.raises(DecisionError, match="conflicting_actions"):
        make_actions(fan, {"power": "turn_off", "oscillate": "oscillate_on"})

    hum = ent(
        "humidifier",
        ["turn_on", "set_mode"],
        {"supported_features": 0, "available_modes": ["auto"]},
    )
    acts = make_actions(hum, {"power": "turn_on", "mode": "auto"})
    assert [a["service"] for a in acts] == ["turn_on", "set_mode"]

    mp = ent(
        "media_player",
        ["turn_on", "turn_off", "volume_set"],
        {"supported_features": 4},
    )
    vals = [
        {"id": "v0", "value": 20.0, "unit": "%", "span": [0, 3], "text": "20%", "kind": "number"}
    ]
    acts = make_actions(mp, {"power": "turn_on", "volume": "v0"}, vals)
    assert [a["service"] for a in acts] == ["turn_on", "volume_set"]
    assert acts[1]["service_data"] == {"volume_level": 0.2}
    # power-only and attr-only regressions unchanged
    assert [a["service"] for a in make_actions(fan, {"power": "turn_on"})] == ["turn_on"]
    assert [a["service"] for a in make_actions(fan, {"oscillate": "oscillate_off"})] == [
        "oscillate"
    ]


def test_fix07_r1_state_and_response_query_are_one_exclusive_choice(ha):
    ha.services["weather"] = {"get_forecasts": {}}
    ha.states["weather.home"] = {
        "state": "sunny",
        "attributes": {"friendly_name": "집 날씨", "supported_features": 1},
    }
    ha.registry.append({"entity_id": "weather.home", "id": "wx-1"})
    ha.services["calendar"] = {"get_events": {}, "create_event": {}}
    ha.states["calendar.local"] = {"state": "on", "attributes": {"friendly_name": "내 일정"}}
    ha.registry.append({"entity_id": "calendar.local", "id": "cal-1"})
    store_pol = {"domains": {"weather": True, "calendar": True}, "entities": {}}
    c = Catalog(ha, store_pol)
    wx = next(e for e in c.entities.values() if e.entity_id == "weather.home")
    cal = next(e for e in c.entities.values() if e.entity_id == "calendar.local")

    wx_opts = options_for(wx, literals("날씨"))
    assert "query" not in wx_opts  # merged into weather_action
    assert "query_state" in wx_opts["weather_action"]
    assert "get_forecasts_daily" in wx_opts["weather_action"]
    cal_opts = options_for(cal, literals("일정"))
    assert "query" not in cal_opts
    assert "query_state" in cal_opts["calendar_action"]
    # The old conflict shape (query_state + get_events) is no longer selectable:
    # one question, one value. A crafted query+other combo still conflicts.
    from fhc.provider import DecisionError as DE

    with pytest.raises(DE, match="conflicting_actions"):
        make_actions(cal, {"calendar_action": "query_state", "calendar_range": "today"})


async def test_fix07_r1_calendar_query_via_merged_choice(ha, store):
    ha.services["calendar"] = {"get_events": {}}
    ha.states["calendar.local"] = {"state": "on", "attributes": {"friendly_name": "내 일정"}}
    ha.registry.append({"entity_id": "calendar.local", "id": "cal-1"})
    store.set_policy({"domains": {"calendar": True}, "entities": {}})
    res = await execute(
        ha,
        store,
        ScriptedProvider({"내 일정": {"calendar_action": "query_state"}}),
        "캘린더 상태 알려줘",
    )
    assert res["status"] == "succeeded"
    assert res["actions"][0]["is_query"] is True
    assert res["query_results"][0]["state"] == "on"


async def test_fix07_r4_fan_power_plus_attribute_end_to_end(ha, store):
    ha.services["fan"] = {"turn_on": {}, "turn_off": {}, "oscillate": {}}
    ha.states["fan.living"] = {
        "state": "off",
        "attributes": {"friendly_name": "선풍기", "supported_features": 2},
    }
    ha.registry.append({"entity_id": "fan.living", "id": "fan-1"})
    store.set_policy({"domains": {"fan": True}, "entities": {}})
    res = await execute(
        ha,
        store,
        ScriptedProvider({"선풍기": {"power": "turn_on", "oscillate": "oscillate_on"}}),
        "선풍기 켜고 회전도 켜줘",
    )
    assert res["status"] == "succeeded"
    assert ha.calls == [
        ("fan", "turn_on", "fan.living"),
        ("fan", "oscillate", "fan.living", {"oscillating": True}),
    ]
    assert res["actions"][0]["previous_state"] == "off"


async def test_fix06_r4_condition_unclear_and_unit_guards(ha, store):
    ha.registry.append({"entity_id": "sensor.living_temp", "area_id": "living"})
    ha.states["sensor.living_temp"] = {
        "entity_id": "sensor.living_temp",
        "state": "29",
        "attributes": {"friendly_name": "거실 온도", "unit_of_measurement": "°C"},
    }
    ha.states["light.living"]["state"] = "on"
    store.set_policy({"domains": {"light": True, "sensor": True}, "entities": {}})

    # 1. unclear classification -> distinct reason, 0 sends.
    res = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": "turn_off", "__condition__": "unclear"}),
        "거실 온도가 28도 이상이고 습도가 낮으면 거실불 꺼줘",
    )
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_unsupported"
    assert len(ha.calls) == 0

    # 2. Source without any native unit -> refused instead of guessing °C.
    ha.states["sensor.living_temp"]["attributes"].pop("unit_of_measurement")
    res = await execute(
        ha,
        store,
        ScriptedProvider({"천장등": {"power": "turn_off"}, "__condition__": cond(unit="°C")}),
        "거실 온도가 28도보다 높다면 거실불 꺼줘",
    )
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_unit_unspecified"
    assert len(ha.calls) == 0

    # 3. Model-selected unit may not overwrite an explicit literal unit.
    ha.states["sensor.living_temp"]["attributes"]["unit_of_measurement"] = "°C"
    res = await execute(
        ha,
        store,
        ScriptedProvider(
            {"천장등": {"power": "turn_off"}, "__condition__": cond(operator="gt", unit="°F")}
        ),
        "거실 온도가 28℃보다 높다면 거실불 꺼줘",
    )
    assert res["status"] == "rejected"
    assert res["reason"] == "condition_unit_conflict"
    assert len(ha.calls) == 0

    # 4. A certain non-conditional command still executes normally.
    res_ok = await execute(ha, store, ScriptedProvider({"천장등": "turn_off"}), "거실불 꺼줘")
    assert res_ok["status"] == "succeeded"
    assert ha.calls == [("light", "turn_off", "light.living")]


class DoubtfulConditionProvider(ScriptedProvider):
    """Scope classification stuck between typed and none: must NOT fall through."""

    async def decide(self, state, questions):
        answers, name = await super().decide(state, questions)
        if "condition_class" in questions:
            answers["condition_class"] = {
                "type": "choice",
                "choice": "typed",
                "probabilities": {"none": 0.16, "typed": 0.68, "unclear": 0.16},
            }
        return answers, name


async def test_fix06_r4_inbetween_condition_confidence_never_executes(ha, store):
    ha.states["light.living"]["state"] = "on"
    store.set_policy({"domains": {"light": True, "sensor": True}, "entities": {}})
    res = await execute(
        ha,
        store,
        DoubtfulConditionProvider({"천장등": {"power": "turn_off"}}),
        "거실 온도가 28도 이상이면 거실불 꺼줘",
    )
    # 0.68 typed: not a condition-less execution; refused as low confidence.
    assert res["status"] == "rejected"
    assert res["reason"] == "low_confidence"
    assert "condition_result" not in res or res.get("condition_result") is None
    assert len(ha.calls) == 0


class MutatedUnitProvider(ScriptedProvider):
    def __init__(self, targets=None, unit_answer=None, **kwargs):
        super().__init__(targets=targets, **kwargs)
        self.unit_answer = unit_answer

    async def decide(self, state, questions):
        answers, name = await super().decide(state, questions)
        if "condition_unit" in questions and self.unit_answer is not None:
            import copy

            answers["condition_unit"] = copy.deepcopy(self.unit_answer)
        return answers, name


async def test_fix08_r1_malformed_condition_unit_fails_closed(ha, store):
    ha.states["light.living"]["state"] = "on"
    ha.registry.append({"entity_id": "sensor.living_temp", "id": "sens-lt"})
    ha.states["sensor.living_temp"] = {
        "state": "29",
        "attributes": {
            "friendly_name": "거실 온도",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
        },
    }
    store.set_policy({"domains": {"light": True, "sensor": True}, "entities": {}})

    cmd = "거실 온도가 28℃ 이상이면 거실불 꺼줘"
    base_targets = {
        "천장등": {"power": "turn_off"},
        "__condition__": {"source": "거실 온도", "operator": "gte", "value": "v0"},
    }

    # 1. Reviewer repro: invalid probability string
    ha.calls.clear()
    prov_invalid_str = MutatedUnitProvider(
        base_targets,
        unit_answer={
            "type": "choice",
            "choice": "°C",
            "probabilities": {"°C": "not-a-probability"},
        },
    )
    res = await execute(ha, store, prov_invalid_str, cmd)
    assert res["status"] == "rejected"
    assert res["reason"] == "invalid_model_response"
    assert len(ha.calls) == 0

    # 2. Malformed type (not 'choice')
    ha.calls.clear()
    prov_bad_type = MutatedUnitProvider(
        base_targets,
        unit_answer={"type": "invalid_type", "choice": "°C", "probabilities": {"°C": 1.0}},
    )
    res = await execute(ha, store, prov_bad_type, cmd)
    assert res["status"] == "rejected"
    assert res["reason"] == "invalid_model_response"
    assert len(ha.calls) == 0

    # 3. Probabilities sum mismatch (0.5 instead of ~1.0)
    ha.calls.clear()
    prov_bad_sum = MutatedUnitProvider(
        base_targets,
        unit_answer={
            "type": "choice",
            "choice": "°C",
            "probabilities": {"°C": 0.5, "°F": 0.0, "%": 0.0, "none": 0.0},
        },
    )
    res = await execute(ha, store, prov_bad_sum, cmd)
    assert res["status"] == "rejected"
    assert res["reason"] == "invalid_model_response"
    assert len(ha.calls) == 0

    # 4. Probabilities labels mismatch
    ha.calls.clear()
    prov_bad_labels = MutatedUnitProvider(
        base_targets,
        unit_answer={"type": "choice", "choice": "°C", "probabilities": {"wrong_label": 1.0}},
    )
    res = await execute(ha, store, prov_bad_labels, cmd)
    assert res["status"] == "rejected"
    assert res["reason"] == "invalid_model_response"
    assert len(ha.calls) == 0

    # 5. Low confidence unit: valid structure, but confidence is low (e.g. 0.45 < 0.6)
    # Must fallback to unit="none", derive from literal/native, and SUCCEED!
    ha.calls.clear()
    prov_low_conf = MutatedUnitProvider(
        base_targets,
        unit_answer={
            "type": "choice",
            "choice": "°C",
            "probabilities": {"°C": 0.45, "°F": 0.35, "%": 0.1, "none": 0.1},
        },
    )
    res = await execute(ha, store, prov_low_conf, cmd)
    assert res["status"] == "succeeded"
    assert res.get("condition_result") is True
    assert ha.calls == [("light", "turn_off", "light.living")]
