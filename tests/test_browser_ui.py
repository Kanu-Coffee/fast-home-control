import os
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid

import pytest
import uvicorn
from conftest import FakeHA
from fhc.main import app
from playwright.sync_api import sync_playwright


def get_free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def ui_server(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("fhc_ui_data")
    options_path = data_dir / "options.json"
    options_path.write_text(
        '{"openrouter_model": "microsoft/microsoft-decision-1", "provider": "openrouter"}'
    )

    token = "test-ui-token-" + str(uuid.uuid4())
    old_env = {
        "FHC_DATA_DIR": os.environ.get("FHC_DATA_DIR"),
        "FHC_OPTIONS_PATH": os.environ.get("FHC_OPTIONS_PATH"),
        "FHC_STANDALONE_TOKEN": os.environ.get("FHC_STANDALONE_TOKEN"),
    }
    old_ha = getattr(app.state, "ha", None)
    old_store = getattr(app.state, "store", None)

    os.environ["FHC_DATA_DIR"] = str(data_dir)
    os.environ["FHC_OPTIONS_PATH"] = str(options_path)
    os.environ["FHC_STANDALONE_TOKEN"] = token

    port = get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Active polling for readiness on /healthz (R2: no fixed 0.6s sleep)
    deadline = time.time() + 10.0
    ready = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.2) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.05)

    if not ready:
        server.should_exit = True
        t.join(timeout=3.0)
        raise RuntimeError("ui_server failed to become ready within 10s")

    # Setup FakeHA after lifespan has started
    fake_ha = FakeHA()
    fake_ha.error = None
    fake_ha.last_sync = time.time()
    fake_ha.periodic_wakeup = threading.Event()
    # Add a third entity to test long text
    fake_ha.registry.append({"entity_id": "light.long_name", "area_id": "living", "aliases": []})
    fake_ha.states["light.long_name"] = {
        "entity_id": "light.long_name",
        "state": "on",
        "attributes": {"friendly_name": "아주 긴 이름을 가진 복도 보조 조명 무드등 테스트 기기"},
    }
    # Add a fourth entity with quotes and brackets to test stable key focus restoration
    fake_ha.registry.append(
        {"entity_id": "light.special_quote", "area_id": "living", "aliases": []}
    )
    fake_ha.states["light.special_quote"] = {
        "entity_id": "light.special_quote",
        "state": "off",
        "attributes": {"friendly_name": '특수기기 "따옴표" [대괄호] 조명'},
    }
    fake_ha.is_admin = lambda _: True
    app.state.ha = fake_ha

    # Seed mock history with 50 items (R3: 50 items test requirement)
    store = app.state.store
    for i in range(50):
        rid = f"req-test-{i:03d}"
        txt = f"거실 조명 {i} 켜줘" if i % 2 == 0 else f"거실 온도 {i} 알려줘"
        store.insert(rid, txt)
        rec = {
            "id": rid,
            "created": time.time() - i * 60,
            "text": txt,
            "status": "succeeded" if i % 3 != 0 else "rejected",
            "phase": "completed",
            "reason": "success" if i % 3 != 0 else "low_confidence",
            "model": "microsoft/microsoft-decision-1",
            "providers": ["openrouter"],
            "timings_ms": {"total": 1200 + i * 10, "model": 900},
            "actions": [
                {"domain": "light", "service": "turn_on", "name": "거실 천장등", "status": "sent"}
            ]
            if i % 3 != 0
            else [],
            "scope_scores": {"light.living": 0.95},
            "decisions": {"action": "turn_on"},
            "verification_score": 0.98,
            "proposed_plan": {"plan_type": "standard"},
            "model_trace": {"raw_response": '{"choice": "turn_on"}' + ("\nline " * (i * 10))},
        }
        store.save(rid, rec)

    try:
        yield {
            "port": port,
            "token": token,
            "base_url": f"http://127.0.0.1:{port}",
            "options_path": options_path,
        }
    finally:
        server.should_exit = True
        t.join(timeout=5.0)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        app.state.ha = old_ha
        app.state.store = old_store


def test_browser_ui_comprehensive(ui_server):
    base_url = ui_server["base_url"]
    token = ui_server["token"]
    options_path = ui_server["options_path"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # -------------------------------------------------------------
        # 1. Desktop Test (1280x800)
        # -------------------------------------------------------------
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # Authenticate via bootstrap
        res = page.request.post(
            f"{base_url}/api/dev-session",
            headers={"Authorization": f"Bearer {token}", "X-FHC-Request": "1"},
        )
        assert res.status == 200

        # Navigate to root
        response = page.goto(base_url)
        assert response.status == 200
        page.wait_for_selector("#command-form")

        # 1-A. Branding & Header verification
        logo_icon = page.locator(".logo-icon")
        assert logo_icon.is_visible()
        icon_src = logo_icon.get_attribute("src")
        assert "icon-32.png" in icon_src
        icon_res = page.request.get(f"{base_url}/{icon_src}")
        assert icon_res.status == 200
        assert icon_res.headers.get("content-type") == "image/png"

        favicons = page.locator('link[rel="icon"]').all()
        assert len(favicons) >= 2
        apple_icon = page.locator('link[rel="apple-touch-icon"]').first
        assert "apple-touch-icon.png" in apple_icon.get_attribute("href")

        # 1-B. User Mode Layout
        assert page.locator("#user-view").is_visible()
        assert not page.locator("#admin-view").is_visible()
        assert "빠른 AI 홈 리모컨" in page.locator(".intro h1").inner_text()
        assert (
            "자연어로 집 안의 가전과 조명을 즉시 제어하세요"
            in page.locator(".intro p").inner_text()
        )

        # 1-C. Admin Mode Switch
        mode_btn = page.locator("#mode-toggle")
        mode_btn.click()
        page.wait_for_selector("#admin-view:not([hidden])")
        assert page.locator("#admin-view").is_visible()
        assert not page.locator("#user-view").is_visible()
        assert mode_btn.get_attribute("aria-pressed") == "true"

        # 1-D. OpenRouter Model Select & Custom Input Draft Preservation (R4)
        model_select = page.locator("#cfg-openrouter-model-select")
        custom_group = page.locator("#cfg-openrouter-custom-group")
        model_input = page.locator("#cfg-openrouter-model")

        assert model_select.is_visible()
        assert model_select.input_value() == "microsoft/microsoft-decision-1"
        assert not custom_group.is_visible()

        # Switch to custom and type a custom draft
        model_select.select_option("custom")
        assert custom_group.is_visible()
        model_input.fill("my-org/my-draft-decision-model")

        # Switch to Jev 1.13 preset
        model_select.select_option("typesafe/jev-1.13")
        assert not custom_group.is_visible()

        # Switch back to custom: draft must be PRESERVED! (R4)
        model_select.select_option("custom")
        assert custom_group.is_visible()
        assert model_input.input_value() == "my-org/my-draft-decision-model"

        # Save config with custom model
        with page.expect_response("**/api/config") as config_resp_info:
            page.locator("#config-form").dispatch_event("submit")
        config_resp = config_resp_info.value
        assert config_resp.status == 200
        page.wait_for_selector("#config-feedback:has-text('설정이 성공적으로 저장되었습니다.')")
        assert "my-org/my-draft-decision-model" in options_path.read_text()

        # Switch to preset and save
        model_select.select_option("microsoft/microsoft-decision-1")
        with page.expect_response("**/api/config") as config_resp_info2:
            page.locator("#config-form").dispatch_event("submit")
        assert config_resp_info2.value.status == 200
        assert "microsoft/microsoft-decision-1" in options_path.read_text()

        # 1-E. Domain & Entity Control/Query Alignment and Hitbox (R6)
        page.wait_for_selector(".domain-item")
        light_domain = page.locator(".domain-item").filter(has_text="조명").first
        assert light_domain.is_visible()

        # Expand light domain
        light_expand_btn = light_domain.locator(".toggle-entities-btn")
        assert light_expand_btn.get_attribute("aria-expanded") == "false"
        light_expand_btn.click()
        assert light_expand_btn.get_attribute("aria-expanded") == "true"

        # Check entity rows
        entity_rows = light_domain.locator(".entity-row").all()
        assert len(entity_rows) >= 3

        # Alignment & Hitbox Check (R6)
        ctrl_x_coords = []
        query_x_coords = []
        for row in entity_rows:
            ctrl_btn = row.locator(".entity-actions-col .toggle-group").nth(0).locator(".toggle")
            query_btn = row.locator(".entity-actions-col .toggle-group").nth(1).locator(".toggle")
            ctrl_box = ctrl_btn.bounding_box()
            query_box = query_btn.bounding_box()

            # R6: Hitbox height and width must be >= 44px
            assert ctrl_box["width"] >= 44, f"Control toggle width {ctrl_box['width']} < 44"
            assert ctrl_box["height"] >= 44, f"Control toggle height {ctrl_box['height']} < 44"
            assert query_box["width"] >= 44, f"Query toggle width {query_box['width']} < 44"
            assert query_box["height"] >= 44, f"Query toggle height {query_box['height']} < 44"

            ctrl_x_coords.append(round(ctrl_box["x"]))
            query_x_coords.append(round(query_box["x"]))

        assert len(set(ctrl_x_coords)) == 1, f"Control toggles not aligned: {ctrl_x_coords}"
        assert len(set(query_x_coords)) == 1, f"Query toggles not aligned: {query_x_coords}"
        assert ctrl_x_coords[0] < query_x_coords[0], "Control column should precede Query column"

        # 1-F. Policy Save Toggle Unlock Lifecycle (R1)
        # First save: click control toggle on first entity
        first_ctrl_toggle = (
            entity_rows[0].locator(".entity-actions-col .toggle-group").nth(0).locator(".toggle")
        )
        with page.expect_response("**/api/domains") as get_domains_info:
            first_ctrl_toggle.click()
        assert get_domains_info.value.status == 200

        # R1: Verify toggle is NOT disabled after first policy save!
        assert not first_ctrl_toggle.is_disabled(), "Toggle remained disabled after policy save!"

        # Immediate consecutive save: click query toggle on same row
        first_query_toggle = (
            entity_rows[0].locator(".entity-actions-col .toggle-group").nth(1).locator(".toggle")
        )
        assert not first_query_toggle.is_disabled(), "Query toggle was disabled after first save!"
        with page.expect_response("**/api/domains") as get_domains_info2:
            first_query_toggle.click()
        assert get_domains_info2.value.status == 200
        assert not first_query_toggle.is_disabled(), (
            "Query toggle remained disabled after consecutive save!"
        )

        # Test consecutive save on entity with special quotes/brackets in name
        special_row = light_domain.locator('.entity-row[data-entity-id="light.special_quote"]')
        assert special_row.is_visible()
        special_ctrl_toggle = (
            special_row.locator(".entity-actions-col .toggle-group").nth(0).locator(".toggle")
        )
        with page.expect_response("**/api/domains") as get_domains_info3:
            special_ctrl_toggle.click()
        assert get_domains_info3.value.status == 200
        assert not special_ctrl_toggle.is_disabled()

        # Test PUT failure recovery: toggles must re-enable for retry
        def fail_policy_put(route):
            if route.request.method == "PUT" and "/api/policy" in route.request.url:
                route.fulfill(status=500, body='{"detail": "database_disk_full"}')
            else:
                route.continue_()

        page.route("**/api/policy", fail_policy_put)
        special_ctrl_toggle.click()
        page.wait_for_selector("#policy-feedback:has-text('정책 저장 실패')")
        assert not special_ctrl_toggle.is_disabled(), "Toggle remained locked after PUT failure!"
        page.unroute("**/api/policy", fail_policy_put)

        # R2: Stale domain GET response race condition guard
        intercept_domains = True
        delayed_responses = []

        def handle_domains_get(route):
            nonlocal intercept_domains
            if (
                intercept_domains
                and route.request.method == "GET"
                and "/api/domains" in route.request.url
            ):
                intercept_domains = False
                delayed_responses.append(route)
            else:
                route.continue_()

        page.route("**/api/domains", handle_domains_get)
        # 1. Trigger older GET (request A) without awaiting the intercepted promise
        page.evaluate("() => { setTimeout(() => { void loadDomains(true); }, 0); }")
        page.wait_for_timeout(100)
        assert len(delayed_responses) == 1

        # 2. Trigger newer GET (request B) that continues to real backend
        # Perform real PUT which calls loadDomains(true) (request B)
        with page.expect_response("**/api/domains") as fast_get_info:
            first_ctrl_toggle.click()
        assert fast_get_info.value.status == 200

        # Now fulfill old request A with stale data
        old_route = delayed_responses.pop(0)
        old_route.fulfill(
            status=200,
            content_type="application/json",
            body='[{"domain": "stale_test", "label": "오래된응답", "supported": true, "enabled": false, "read_enabled": false, "discovered_count": 1, "entities": []}]',
        )
        page.wait_for_timeout(100)
        page.unroute("**/api/domains", handle_domains_get)

        # Verify cachedDomains was NOT overwritten by the old stale GET response!
        assert page.locator(".domain-name:has-text('오래된응답')").count() == 0, (
            "Stale domains GET response overwrote fresh domains data!"
        )

        # 1-G. Search and Expand State (R5)
        search_input = page.locator("#entity-search")
        search_input.fill("보조 조명")
        visible_rows = page.locator(".entity-row:visible").all()
        assert len(visible_rows) == 1
        assert "보조 조명" in visible_rows[0].inner_text()

        # R5: Clicking '목록 닫기' during search must collapse the accordion!
        search_toggle_btn = light_domain.locator("#toggle-btn-light")
        assert search_toggle_btn.get_attribute("aria-expanded") == "true"
        search_toggle_btn.click()

        # Verify accordion is collapsed during search
        assert search_toggle_btn.get_attribute("aria-expanded") == "false"
        assert not light_domain.locator(".entities-accordion").is_visible()

        # Verify focus is preserved on the toggle button
        focused_id = page.evaluate("document.activeElement ? document.activeElement.id : null")
        assert focused_id == "toggle-btn-light"

        # Reopen via keyboard Space
        page.keyboard.press("Space")
        assert search_toggle_btn.get_attribute("aria-expanded") == "true"
        assert light_domain.locator(".entities-accordion").is_visible()
        focused_id_after = page.evaluate(
            "document.activeElement ? document.activeElement.id : null"
        )
        assert focused_id_after == "toggle-btn-light"

        # Clear search: light domain should still be expanded because user manually expanded it initially
        search_input.fill("")
        assert light_domain.locator(".entities-accordion").is_visible()

        # 1-H. History internal scrolling, diagnostic change detection and anchor preservation (R1, R3)
        history_list = page.locator("#history")
        assert history_list.is_visible()
        history_rows = page.locator(".history-row").all()
        assert len(history_rows) >= 50  # 50 items rendered

        # Open the first details element
        first_row = page.locator(".history-row").first
        first_details = first_row.locator("details")
        first_details.locator("summary").click()
        assert first_details.get_attribute("open") is not None

        # Scroll pre down to 120px
        first_pre = first_details.locator(".diagnostic-json")
        page.evaluate("(pre) => { pre.scrollTop = 120; }", first_pre.element_handle())
        initial_scroll = page.evaluate("(pre) => pre.scrollTop", first_pre.element_handle())
        assert initial_scroll > 0

        # Change phase in store from 'completed' to 'phase-test-modified'
        first_req_id = first_row.get_attribute("data-request-id")
        _, rec = app.state.store.get(first_req_id)
        rec["phase"] = "phase-test-modified"
        rec["model_trace"] = {"raw_response": "updated-trace-data" + ("\nline " * 80)}
        app.state.store.save(first_req_id, rec)

        # Trigger history refresh via loadHistory()
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)

        # R3: Verify phase updated, details still open, and pre.scrollTop preserved!
        refreshed_first_row = page.locator(f'.history-row[data-request-id="{first_req_id}"]')
        refreshed_details = refreshed_first_row.locator("details")
        assert refreshed_details.get_attribute("open") is not None
        refreshed_pre = refreshed_details.locator(".diagnostic-json")
        assert "phase-test-modified" in refreshed_pre.inner_text()
        preserved_scroll = page.evaluate("(pre) => pre.scrollTop", refreshed_pre.element_handle())
        assert preserved_scroll == initial_scroll

        # R3: Test providers change detection
        rec["providers"] = ["openrouter", "changed-test-provider"]
        app.state.store.save(first_req_id, rec)
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)
        refreshed_pre_providers = page.locator(
            f'.history-row[data-request-id="{first_req_id}"] .diagnostic-json'
        )
        assert "changed-test-provider" in refreshed_pre_providers.inner_text()

        # R1: Test reading anchor preservation when preceding row height changes
        # Scroll #history down so row 7 is near the top
        page.evaluate("() => { document.getElementById('history').scrollTop = 700; }")
        page.wait_for_timeout(50)
        row7 = page.locator(".history-row").nth(7)
        row7_id = row7.get_attribute("data-request-id")
        row7_init_top = page.evaluate(
            "(r) => r.getBoundingClientRect().top - document.getElementById('history').getBoundingClientRect().top",
            row7.element_handle(),
        )

        # Expand an earlier row (row 2) with 30 actions to significantly change preceding height
        row2 = page.locator(".history-row").nth(2)
        row2_id = row2.get_attribute("data-request-id")
        _, rec2 = app.state.store.get(row2_id)
        rec2["actions"] = [
            {"domain": "light", "service": "turn_on", "name": f"추가 기기 {k}", "status": "sent"}
            for k in range(30)
        ]
        app.state.store.save(row2_id, rec2)

        # Refresh history
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)

        # Verify row 7 relative top position in history container is preserved!
        row7_new = page.locator(f'.history-row[data-request-id="{row7_id}"]')
        row7_new_top = page.evaluate(
            "(r) => r.getBoundingClientRect().top - document.getElementById('history').getBoundingClientRect().top",
            row7_new.element_handle(),
        )
        assert abs(row7_new_top - row7_init_top) < 2, (
            f"Anchor position changed: {row7_new_top} vs {row7_init_top}"
        )

        # Test inserting a new item at the top of history: anchor must still be preserved
        new_top_id = f"req-test-top-{uuid.uuid4()}"
        app.state.store.insert(new_top_id, "새로운 최상단 명령")
        app.state.store.save(
            new_top_id,
            {
                "id": new_top_id,
                "created": time.time(),
                "text": "새로운 최상단 명령",
                "status": "succeeded",
                "reason": "success",
                "timings_ms": {"total": 500},
            },
        )
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)

        row7_after_insert_top = page.evaluate(
            "(r) => r.getBoundingClientRect().top - document.getElementById('history').getBoundingClientRect().top",
            row7_new.element_handle(),
        )
        assert abs(row7_after_insert_top - row7_init_top) < 2, (
            f"Anchor position changed after insert: {row7_after_insert_top} vs {row7_init_top}"
        )

        # -------------------------------------------------------------
        # 2. Mobile Responsive Tests (320px, 360px, 390px, 430px)
        # -------------------------------------------------------------
        for width in [320, 360, 390, 430]:
            page.set_viewport_size({"width": width, "height": 700})
            page.wait_for_timeout(100)

            # Check horizontal overflow
            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            client_width = page.evaluate("window.innerWidth")
            assert scroll_width <= client_width, (
                f"Horizontal overflow at {width}px: scrollWidth={scroll_width} > clientWidth={client_width}"
            )

            # Switch back to user view and verify 2-column shortcuts
            page.locator("#mode-toggle").click()
            page.wait_for_selector("#user-view:not([hidden])")

            # Check shortcuts grid columns on mobile
            grid_columns = page.evaluate(
                "getComputedStyle(document.getElementById('shortcuts')).gridTemplateColumns"
            )
            col_list = grid_columns.split()
            if page.locator(".shortcut-card").count() > 0:
                assert len(col_list) == 2, f"Expected 2 columns on {width}px, got: {grid_columns}"

            # Switch back to admin for next width test
            page.locator("#mode-toggle").click()
            page.wait_for_selector("#admin-view:not([hidden])")

        # -------------------------------------------------------------
        # 3. Real Command Form Submit & Input Text Restoration (Section 3)
        # -------------------------------------------------------------
        page.locator("#mode-toggle").click()
        page.wait_for_selector("#user-view:not([hidden])")

        command_box = page.locator("#command")
        test_fail_cmd = "전혀 알 수 없는 미지원 명령 4829"
        command_box.fill(test_fail_cmd)

        # Submit via form submit
        with page.expect_response("**/api/commands") as cmd_resp_info:
            page.locator("#command-form").dispatch_event("submit")
        assert cmd_resp_info.value.status == 503

        # Wait for feedback box to show rejection/failure
        page.wait_for_selector("#user-feedback.feedback-box.error")
        assert "OpenRouter 또는 Azure" in page.locator("#user-feedback").inner_text()

        # Verify command text was restored by real executeCommand error handler!
        assert command_box.input_value() == test_fail_cmd

        # Test: typing a new command while in-flight pending does not get overwritten!
        # Intercept commands POST to hold it while user types a new sentence
        delayed_cmd_routes = []

        def hold_command_post(route):
            if route.request.method == "POST" and "/api/commands" in route.request.url:
                delayed_cmd_routes.append(route)
            else:
                route.continue_()

        page.route("**/api/commands", hold_command_post)
        command_box.fill("첫 번째 실행 요청 명령")
        page.locator("#command-form").dispatch_event("submit")
        page.wait_for_timeout(100)
        assert len(delayed_cmd_routes) == 1

        # While request is in-flight, user types a new sentence
        command_box.fill("사용자가 새로 입력한 두 번째 명령")

        # Fulfill the in-flight request with error
        held_route = delayed_cmd_routes.pop(0)
        held_route.fulfill(
            status=503,
            content_type="application/json",
            body='{"error": "provider_not_configured"}',
        )
        page.unroute("**/api/commands", hold_command_post)
        page.wait_for_timeout(100)

        # Verify the newly typed sentence is PRESERVED and not overwritten!
        assert command_box.input_value() == "사용자가 새로 입력한 두 번째 명령"

        # 4. Zero unhandled script or page errors
        script_errors = [e for e in console_errors if not e.startswith("Failed to load resource:")]
        assert len(script_errors) == 0, f"Script errors detected: {script_errors}"

        context.close()
        browser.close()
