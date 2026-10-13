import uuid

from conftest import ScriptedProvider
from fastapi.testclient import TestClient
from fhc.main import app


def test_ingress_spoofed_forwarding_header_does_not_authorize(monkeypatch, tmp_path):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("FHC_STANDALONE_TOKEN", raising=False)
    with TestClient(app) as client:
        assert (
            client.get("/api/status", headers={"x-forwarded-for": "172.30.32.2"}).status_code == 403
        )
        assert client.get("/healthz").status_code == 200


def test_command_idempotency_conflict_and_origin_guard(monkeypatch, tmp_path, ha):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test-session-only")
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(tmp_path / "options.json"))
    with TestClient(app) as client:
        from fhc.engine import Engine

        original_ha, original_provider = app.state.ha, app.state.provider
        app.state.ha = ha
        provider = ScriptedProvider()
        provider.options = type("Options", (), {"configured": lambda _: ["scripted"]})()
        app.state.provider = provider
        app.state.engine = Engine(ha, provider, app.state.store)
        body = {"text": "거실불 꺼줘", "request_id": str(uuid.uuid4())}
        headers = {"Authorization": "Bearer test-session-only", "X-FHC-Request": "1"}
        assert (
            client.post(
                "/api/commands", json=body, headers={"Authorization": headers["Authorization"]}
            ).status_code
            == 403
        )
        assert client.post("/api/commands", json=body, headers=headers).status_code == 202
        assert client.post("/api/commands", json=body, headers=headers).status_code == 202
        assert len(ha.calls) == 1
        assert (
            client.post(
                "/api/commands", json={**body, "text": "다른 명령"}, headers=headers
            ).status_code
            == 409
        )
        assert client.get("/api/status").status_code == 403
        app.state.ha, app.state.provider = original_ha, original_provider


def test_no_key_still_has_working_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test-session-only")
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(tmp_path / "options.json"))
    with TestClient(app) as client:
        response = client.get("/api/status", headers={"Authorization": "Bearer test-session-only"})
        assert response.status_code == 200
        assert response.json()["configured_providers"] == []
        assert "access_token" not in response.text
        assert "api_key" not in response.text


def test_restart_does_not_replay_inflight_request(tmp_path):
    from fhc.store import Store

    store = Store(tmp_path)
    key = str(uuid.uuid4())
    record = store.insert(key, "거실불 꺼줘")
    record["status"] = "executing"
    store.save(key, record)
    store.close()
    reopened = Store(tmp_path)
    assert reopened.get(key)[1]["status"] == "uncertain"
    reopened.close()


def test_config_and_shortcuts_api(monkeypatch, tmp_path):
    monkeypatch.setenv("FHC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test-session-only")
    monkeypatch.setenv("FHC_OPTIONS_PATH", str(tmp_path / "options.json"))
    headers = {"Authorization": "Bearer test-session-only", "X-FHC-Request": "1"}
    with TestClient(app) as client:
        # GET /api/config
        cfg_resp = client.get("/api/config", headers={"Authorization": "Bearer test-session-only"})
        assert cfg_resp.status_code == 200
        cfg = cfg_resp.json()
        assert "openrouter_configured" in cfg
        assert "openrouter_model" in cfg

        # POST /api/config
        update_resp = client.post(
            "/api/config",
            json={"openrouter_model": "microsoft/microsoft-decision-1", "provider": "auto"},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["openrouter_model"] == "microsoft/microsoft-decision-1"

        # GET /api/shortcuts
        sc_resp = client.get(
            "/api/shortcuts", headers={"Authorization": "Bearer test-session-only"}
        )
        assert sc_resp.status_code == 200
        assert isinstance(sc_resp.json(), list)

        # GET /api/domains
        dom_resp = client.get("/api/domains", headers={"Authorization": "Bearer test-session-only"})
        assert dom_resp.status_code == 200
        domains = dom_resp.json()
        assert any(d["domain"] == "light" for d in domains)

        # PUT /api/policy for entity exclusion
        pol_resp = client.put(
            "/api/policy",
            json={"entity_id": "light.living", "entity_enabled": False},
            headers=headers,
        )
        assert pol_resp.status_code == 200
        assert pol_resp.json()["ok"] is True
