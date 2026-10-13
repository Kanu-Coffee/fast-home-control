import asyncio
import contextlib
import json
import os
import random
import time

import httpx
from websockets.asyncio.client import connect


class HAError(Exception):
    pass


class HA:
    def __init__(self, rescan_hours=12):
        self.token = os.environ.get("SUPERVISOR_TOKEN", "")
        self.ws_url = "ws://supervisor/core/websocket"
        self.rest_url = "http://supervisor/core/api"
        # Overrides are only for the isolated development/test runner, never addon options.
        if os.environ.get("FHC_STANDALONE_TOKEN"):
            self.token = os.environ.get("FHC_HA_TOKEN", self.token)
            self.ws_url = os.environ.get("FHC_HA_WS", self.ws_url)
            self.rest_url = os.environ.get("FHC_HA_REST", self.rest_url)
        self.states, self.services = {}, {}
        self.registry, self.devices, self.areas = [], [], []
        self.renames = {}
        self.periodic_wakeup = asyncio.Event()
        self.version = 0
        self.temperature_unit = None
        self.ready = False
        self.error = "not_connected"
        self.last_sync = None
        self.rescan_hours = rescan_hours
        self.pending = {}
        self.sequence = 0
        self.ws = None
        self.sync_lock = asyncio.Lock()
        self.events_during_sync = None
        self.refresh_task = None
        self.http = httpx.AsyncClient(timeout=10, trust_env=False)

    async def request(self, message):
        if self.ws is None:
            raise HAError("ha_disconnected")
        self.sequence += 1
        message = dict(message, id=self.sequence)
        future = asyncio.get_running_loop().create_future()
        self.pending[self.sequence] = future
        try:
            await self.ws.send(json.dumps(message))
            async with asyncio.timeout(15):
                return await future
        finally:
            self.pending.pop(message["id"], None)

    async def reader(self):
        async for raw in self.ws:
            message = json.loads(raw)
            if message.get("type") == "result":
                future = self.pending.get(message["id"])
                if future and not future.done():
                    if message.get("success"):
                        future.set_result(message.get("result"))
                    else:
                        future.set_exception(HAError("ha_request_rejected"))
            elif message.get("type") == "event":
                event = message["event"]
                if self.events_during_sync is not None:
                    self.events_during_sync.append(event)
                self.event(event)

    def event(self, event):
        kind, data = event["event_type"], event.get("data", {})
        if kind == "state_changed":
            new = data.get("new_state")
            entity_id = data["entity_id"]
            if new:
                previous = self.states.get(entity_id)
                domain = entity_id.split(".")[0]
                metadata = (
                    "friendly_name",
                    "supported_features",
                    "hvac_modes",
                    "min_temp",
                    "max_temp",
                    "target_temp_step",
                    "supported_color_modes",
                    "entity_id",
                    "temperature_unit",
                    "effect_list",
                    "min_color_temp_kelvin",
                    "max_color_temp_kelvin",
                )
                if domain in {"light", "switch", "climate"} and (
                    not previous
                    or any(
                        previous.get("attributes", {}).get(key)
                        != new.get("attributes", {}).get(key)
                        for key in metadata
                    )
                ):
                    self.version += 1
                self.states[entity_id] = new
            else:
                domain = entity_id.split(".")[0]
                self.states.pop(entity_id, None)
                if domain in {"light", "switch", "climate"}:
                    self.version += 1
        elif kind in {
            "entity_registry_updated",
            "device_registry_updated",
            "area_registry_updated",
            "service_registered",
            "service_removed",
            "core_config_updated",
        }:
            if kind == "entity_registry_updated" and data.get("changes", {}).get("entity_id"):
                self.renames[data["changes"]["entity_id"]] = data["entity_id"]
            self.ready = False
            self.version += 1
            if self.refresh_task is None or self.refresh_task.done():
                self.refresh_task = asyncio.create_task(self.delayed_sync())

    async def delayed_sync(self):
        await asyncio.sleep(0.3)
        try:
            await self.rescan()
        except (HAError, TimeoutError):
            self.ready = False
            self.error = "sync_failed"
            if self.ws:
                await self.ws.close()

    async def rescan(self):
        async with self.sync_lock:
            self.ready = False
            self.events_during_sync = []
            try:
                states, services, registry, devices, areas, config = await asyncio.gather(
                    self.request({"type": "get_states"}),
                    self.request({"type": "get_services"}),
                    self.request({"type": "config/entity_registry/list"}),
                    self.request({"type": "config/device_registry/list"}),
                    self.request({"type": "config/area_registry/list"}),
                    self.request({"type": "get_config"}),
                )
                buffered = self.events_during_sync
                self.states = {x["entity_id"]: x for x in states}
                self.services, self.registry = services, registry
                self.temperature_unit = (config or {}).get("unit_system", {}).get("temperature")
                self.devices, self.areas = devices, areas
                metadata_changed = False
                for event in buffered:
                    if event["event_type"] == "state_changed":
                        data = event["data"]
                        new = data.get("new_state")
                        current = self.states.get(data["entity_id"])
                        if new and (
                            not current
                            or new.get("last_updated", "") >= current.get("last_updated", "")
                        ):
                            self.states[data["entity_id"]] = new
                        elif not new:
                            self.states.pop(data["entity_id"], None)
                    else:
                        metadata_changed = True
                self.version += 1
                self.last_sync = time.time()
                self.error = None
                self.ready = not metadata_changed
            finally:
                self.events_during_sync = None
            if not self.ready and self.ws:
                # Reconnect to obtain a consistent fresh registry if it changed during snapshot.
                await self.ws.close()

    async def periodic(self):
        while True:
            try:
                await asyncio.wait_for(self.periodic_wakeup.wait(), self.rescan_hours * 3600)
                self.periodic_wakeup.clear()
            except TimeoutError:
                await self.rescan()

    async def run(self):
        delay = 1
        while True:
            reader = periodic = None
            try:
                if not self.token:
                    self.error = "supervisor_token_missing"
                    await asyncio.sleep(10)
                    continue
                async with connect(
                    self.ws_url, proxy=None, max_size=32 * 1024 * 1024, open_timeout=10
                ) as ws:
                    self.ws = ws
                    async with asyncio.timeout(15):
                        await ws.recv()
                        await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
                        if json.loads(await ws.recv()).get("type") != "auth_ok":
                            raise HAError("ha_authentication_failed")
                    reader = asyncio.create_task(self.reader())
                    for event in [
                        "state_changed",
                        "entity_registry_updated",
                        "device_registry_updated",
                        "area_registry_updated",
                        "service_registered",
                        "service_removed",
                        "core_config_updated",
                    ]:
                        await self.request({"type": "subscribe_events", "event_type": event})
                    await self.rescan()
                    delay = 1
                    periodic = asyncio.create_task(self.periodic())
                    done, _ = await asyncio.wait(
                        [reader, periodic], return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never log payloads, URLs, raw auth failures or credentials.
                self.error = "ha_connection_failed"
            finally:
                self.ready = False
                self.ws = None
                self.version += 1
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(HAError("ha_disconnected"))
                for task in [reader, periodic, self.refresh_task]:
                    if task:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task
            await asyncio.sleep(delay + random.random())
            delay = min(delay * 2, 30)

    async def is_admin(self, user_id):
        if not user_id or not self.ready:
            return False
        try:
            users = await self.request({"type": "config/auth/list"})
            return any(
                u.get("id") == user_id
                and u.get("is_active") is True
                and not u.get("system_generated")
                and (u.get("is_owner") or "system-admin" in u.get("group_ids", []))
                for u in users
            )
        except (HAError, TimeoutError, TypeError):
            return False

    async def fresh_state(self, entity_id):
        try:
            response = await self.http.get(
                f"{self.rest_url}/states/{entity_id}",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HAError("state_refresh_failed") from exc

    async def call(self, domain, service, entity_id, service_data=None, return_response=False):
        # Domain and service are supplied exclusively by the validated adapter.
        payload = {
            "type": "call_service",
            "domain": domain,
            "service": service,
            "target": {"entity_id": entity_id},
        }
        if service_data:
            payload["service_data"] = service_data
        if return_response:
            payload["return_response"] = True
        return await self.request(payload)

    async def close(self):
        await self.http.aclose()
