from dataclasses import dataclass

SUPPORTED = {"light": "조명 · 전등 · 불", "switch": "스위치 · 플러그 · 전원"}


@dataclass(frozen=True)
class Entity:
    ref: str
    entity_id: str
    name: str
    aliases: tuple[str, ...]
    domain: str
    area: str
    area_aliases: tuple[str, ...]
    device: str
    state: str

    def compact(self):
        result = {"id": self.ref, "name": self.name, "aliases": self.aliases, "device": self.device}
        return {key: value for key, value in result.items() if value}


class Catalog:
    def __init__(self, ha, policy):
        self.ha, self.policy = ha, policy
        self.version = ha.version
        self.entities = {}
        devices = {x["id"]: x for x in ha.devices}
        areas = {x["area_id"]: x for x in ha.areas}
        registry = {x["entity_id"]: x for x in ha.registry}
        for entity_id, state in sorted(ha.states.items()):
            domain = entity_id.split(".", 1)[0]
            reg = registry.get(entity_id, {})
            device = devices.get(reg.get("device_id"), {})
            if domain not in SUPPORTED or not policy.get(domain, False):
                continue
            if (
                reg.get("disabled_by")
                or reg.get("hidden_by")
                or reg.get("entity_category")
                or device.get("disabled_by")
            ):
                continue
            if not {"turn_on", "turn_off"}.issubset(ha.services.get(domain, {})):
                continue
            area_id = reg.get("area_id") or device.get("area_id")
            area = areas.get(area_id, {})
            ref = f"e{len(self.entities)}"
            self.entities[ref] = Entity(
                ref,
                entity_id,
                state.get("attributes", {}).get("friendly_name")
                or reg.get("name")
                or reg.get("original_name")
                or entity_id,
                tuple(x for x in reg.get("aliases", []) if isinstance(x, str)),
                domain,
                area.get("name", "영역 미지정"),
                tuple(x for x in area.get("aliases", []) if isinstance(x, str)),
                device.get("name_by_user") or device.get("name") or "",
                state.get("state", "unknown"),
            )
        self.groups = {}
        for entity in self.entities.values():
            # Area names are descriptions, never keys: duplicate names remain distinguishable.
            reg = registry.get(entity.entity_id, {})
            device = devices.get(reg.get("device_id"), {})
            key = (reg.get("area_id") or device.get("area_id"), entity.domain)
            self.groups.setdefault(key, []).append(entity)
        self.groups = {f"g{i}": members for i, members in enumerate(self.groups.values())}

    def compact(self):
        return [
            {
                "id": key,
                "area": items[0].area,
                "area_aliases": items[0].area_aliases,
                "domain": items[0].domain,
                "description": SUPPORTED[items[0].domain],
                "entities": [x.compact() for x in items],
            }
            for key, items in self.groups.items()
        ]
