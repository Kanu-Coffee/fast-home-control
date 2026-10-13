import asyncio
import contextlib
import json

from fhc.ha import HA
from websockets.asyncio.server import serve


async def wait_until(predicate):
    for _ in range(400):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("HA did not reach expected state")


async def test_websocket_snapshot_event_race_and_reconnect(monkeypatch):
    connections, messages = [], []

    async def server(ws):
        connections.append(ws)
        await ws.send(json.dumps({"type": "auth_required"}))
        auth = json.loads(await ws.recv())
        assert auth == {"type": "auth", "access_token": "test-only"}
        await ws.send(json.dumps({"type": "auth_ok"}))
        async for raw in ws:
            request = json.loads(raw)
            kind = request["type"]
            messages.append(kind)
            result = None
            if kind == "get_states":
                result = [{"entity_id": "light.test", "state": "off", "last_updated": "1"}]
                # State event arrives while initial get_states response is still outstanding.
                await ws.send(
                    json.dumps(
                        {
                            "type": "event",
                            "event": {
                                "event_type": "state_changed",
                                "data": {
                                    "entity_id": "light.test",
                                    "new_state": {
                                        "entity_id": "light.test",
                                        "state": "on",
                                        "last_updated": "2",
                                    },
                                },
                            },
                        }
                    )
                )
            elif kind == "get_services":
                result = {"light": {"turn_on": {}, "turn_off": {}}}
            elif kind.startswith("config/"):
                result = []
            await ws.send(
                json.dumps(
                    {"id": request["id"], "type": "result", "success": True, "result": result}
                )
            )

    async with serve(server, "127.0.0.1", 0) as listener:
        port = listener.sockets[0].getsockname()[1]
        monkeypatch.setenv("FHC_STANDALONE_TOKEN", "test")
        monkeypatch.setenv("FHC_HA_TOKEN", "test-only")
        monkeypatch.setenv("FHC_HA_WS", f"ws://127.0.0.1:{port}")
        ha = HA()
        task = asyncio.create_task(ha.run())
        try:
            await wait_until(lambda: ha.ready)
            assert messages[:6] == ["subscribe_events"] * 6
            assert ha.states["light.test"]["state"] == "on"
            await connections[0].close()
            await wait_until(lambda: len(connections) == 2 and ha.ready)
            assert ha.states["light.test"]["state"] == "on"
            await connections[1].send(
                json.dumps(
                    {
                        "type": "event",
                        "event": {
                            "event_type": "state_changed",
                            "data": {
                                "entity_id": "light.added",
                                "new_state": {"entity_id": "light.added", "state": "off"},
                            },
                        },
                    }
                )
            )
            await wait_until(lambda: "light.added" in ha.states)
            await connections[1].send(
                json.dumps(
                    {
                        "type": "event",
                        "event": {
                            "event_type": "state_changed",
                            "data": {"entity_id": "light.added", "new_state": None},
                        },
                    }
                )
            )
            await wait_until(lambda: "light.added" not in ha.states)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await ha.close()


async def test_state_attribute_changes_do_not_invalidate_catalog_except_metadata():
    ha = HA()
    try:
        ha.states["light.test"] = {"attributes": {"friendly_name": "Test", "brightness": 100}}

        def event(attributes):
            ha.event(
                {
                    "event_type": "state_changed",
                    "data": {"entity_id": "light.test", "new_state": {"attributes": attributes}},
                }
            )

        event({"friendly_name": "Test", "brightness": 120})
        assert ha.version == 0
        event({"friendly_name": "Changed", "brightness": 120})
        assert ha.version == 1
    finally:
        await ha.close()
