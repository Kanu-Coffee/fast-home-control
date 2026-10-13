from dataclasses import dataclass

from .actions import BRIGHTNESS_MODES, COLOR_MODES, capabilities

SUPPORTED = {
    "light": "조명 · 전등 · 불",
    "switch": "스위치 · 플러그 · 전원",
    "climate": "에어컨 · 냉난방기 · 공조",
}


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
    features: dict

    def compact(self):
        result = {
            "id": self.ref,
            "name": self.name,
            "aliases": self.aliases,
            "device": self.device,
        }
        if self.domain == "climate":
            hvac_modes = self.features.get("hvac_modes")
            if hvac_modes:
                result["hvac_modes"] = hvac_modes
            if "min_temp" in self.features and "max_temp" in self.features:
                result["temp_range"] = [self.features["min_temp"], self.features["max_temp"]]
                result["temperature_unit"] = self.features.get("temperature_unit")
                result["step"] = self.features.get("target_temp_step")
        elif self.domain == "light":
            color_modes = self.features.get("supported_color_modes")
            if color_modes:
                result["color_modes"] = color_modes
                result["supports"] = ["on", "off"]
                if set(color_modes) & BRIGHTNESS_MODES:
                    result["supports"].extend(["brightness_pct", "brightness_step_pct"])
                if set(color_modes) & COLOR_MODES:
                    result["supports"].append("rgb_color")
                if "color_temp" in color_modes:
                    result["supports"].append("color_temp_kelvin")
        return {
            key: value
            for key, value in result.items()
            if value is not None and value != () and value != ""
        }


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
            if domain not in SUPPORTED:
                continue

            # Check policy
            if hasattr(policy, "is_allowed"):
                if not policy.is_allowed(domain, entity_id, registry.get(entity_id, {}).get("id")):
                    continue
            elif isinstance(policy, dict):
                dom_pol = policy.get("domains", policy)
                if not dom_pol.get(domain, False):
                    continue
                ent_pol = policy.get("entities", {})
                if entity_id in ent_pol and not ent_pol[entity_id].get("enabled", True):
                    continue

            reg = registry.get(entity_id, {})
            device = devices.get(reg.get("device_id"), {})
            if (
                reg.get("disabled_by")
                or reg.get("hidden_by")
                or reg.get("entity_category")
                or device.get("disabled_by")
            ):
                continue

            domain_services = ha.services.get(domain, {})
            if domain in {"light", "switch"}:
                if not {"turn_on", "turn_off"}.intersection(domain_services):
                    continue
            elif domain == "climate":
                if not (
                    {"set_hvac_mode", "turn_on", "turn_off", "set_temperature"}
                    & set(domain_services)
                ):
                    continue

            attrs = state.get("attributes", {})
            # Known HA groups are represented by policy-checked leaves, never direct targets.
            if "entity_id" in attrs or reg.get("platform") == "group":
                continue
            features = capabilities(
                domain, state, ha.services, getattr(ha, "temperature_unit", None)
            )

            area_id = reg.get("area_id") or device.get("area_id")
            area = areas.get(area_id, {})
            ref = f"e{len(self.entities)}"
            self.entities[ref] = Entity(
                ref,
                entity_id,
                attrs.get("friendly_name")
                or reg.get("name")
                or reg.get("original_name")
                or entity_id,
                tuple(x for x in reg.get("aliases", []) if isinstance(x, str)),
                domain,
                area.get("name", "영역 미지정"),
                tuple(x for x in area.get("aliases", []) if isinstance(x, str)),
                device.get("name_by_user") or device.get("name") or "",
                state.get("state", "unknown"),
                features,
            )

        # Preserve group semantics as aliases on allowed leaves. Fail closed on cycles/missing membership.
        def leaves(eid, seen):
            if eid in seen or eid not in ha.states:
                return None
            if hasattr(policy, "is_allowed") and not policy.is_allowed(
                eid.split(".")[0], eid, registry.get(eid, {}).get("id")
            ):
                return []
            attrs = ha.states[eid].get("attributes", {})
            if "entity_id" not in attrs:
                return None if registry.get(eid, {}).get("platform") == "group" else [eid]
            members = attrs["entity_id"]
            if (
                not isinstance(members, list)
                or not members
                or not all(isinstance(x, str) for x in members)
            ):
                return None
            result = []
            for member in members:
                found = leaves(member, seen | {eid})
                if found is None:
                    return None
                result.extend(found)
            return result

        from dataclasses import replace

        for eid, state in ha.states.items():
            if "entity_id" not in state.get("attributes", {}):
                continue
            members = leaves(eid, set())
            if members is None:
                continue
            name = state.get("attributes", {}).get("friendly_name", eid)
            for ref, entity in list(self.entities.items()):
                if entity.entity_id in members:
                    self.entities[ref] = replace(
                        entity, aliases=tuple(dict.fromkeys((*entity.aliases, name)))
                    )
        self.groups = {}
        for entity in self.entities.values():
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
