from dataclasses import dataclass

from .actions import BRIGHTNESS_MODES, COLOR_MODES, capabilities
from .store import as_policy_dict

SUPPORTED = {
    "light": "조명 · 전등 · 불",
    "switch": "스위치 · 플러그 · 전원",
    "climate": "에어컨 · 냉난방기 · 공조",
    "vacuum": "로봇청소기 · 청소기",
    "button": "버튼 · 누름 스위치",
    "fan": "선풍기 · 환풍기 · 서큘레이터",
    "cover": "커튼 · 블라인드 · 차고문",
    "humidifier": "가습기 · 제습기",
    "media_player": "미디어 플레이어 · 스피커 · TV",
    "input_boolean": "가상 스위치 · 불리언",
    "number": "수치 조절기",
    "input_number": "가상 수치 조절기",
    "select": "선택 목록",
    "input_select": "가상 선택 목록",
    "counter": "카운터 · 계수기",
    "script": "스크립트",
    "automation": "자동화",
    "scene": "장면 · 씬",
    "sensor": "센서 · 측정값 조회",
    "binary_sensor": "이진 센서 · 상태 감지",
    "weather": "날씨 · 기상 예보",
    "calendar": "캘린더 · 일정",
    "todo": "할 일 목록",
    "input_text": "텍스트 입력",
    "input_datetime": "날짜/시간 입력",
    "notify": "알림 전송",
    "tts": "음성 안내(TTS)",
    "person": "사용자 재실 상태",
    "device_tracker": "기기 위치/재실",
    "zone": "구역 상태",
    "sun": "일출/일몰 상태",
    "event": "이벤트 감지",
    "camera": "카메라 상태",
    "image": "이미지 상태",
    "update": "업데이트 상태",
}

DEFERRED = {
    "ai_task": "AI 태스크 도메인은 직접 가전 제어가 아니므로 보류",
    "conversation": "HA 음성 대화 에이전트 도메인은 직접 가전 제어가 아니므로 보류",
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
    write_allowed: bool = True
    read_allowed: bool = True

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
        elif self.domain == "cover":
            if "current_position" in self.features:
                result["current_position"] = self.features["current_position"]
        elif self.domain == "fan":
            if "speed_count" in self.features:
                result["speed_count"] = self.features["speed_count"]
        elif self.domain == "humidifier":
            if "min_humidity" in self.features and "max_humidity" in self.features:
                result["humidity_range"] = [
                    self.features["min_humidity"],
                    self.features["max_humidity"],
                ]
        elif self.domain in {"number", "input_number"}:
            if "min" in self.features and "max" in self.features:
                result["range"] = [self.features["min"], self.features["max"]]
            if "step" in self.features:
                result["step"] = self.features["step"]
        elif self.domain in {"select", "input_select"}:
            if "options" in self.features:
                result["options"] = self.features["options"]
        elif self.domain in {"sensor", "binary_sensor"}:
            if self.features.get("device_class"):
                result["device_class"] = self.features["device_class"]
            if self.features.get("unit_of_measurement"):
                result["unit"] = self.features["unit_of_measurement"]
        return {
            key: value
            for key, value in result.items()
            if value is not None and value != () and value != ""
        }


class Catalog:
    def __init__(self, ha, policy):
        policy = as_policy_dict(policy)
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

            # One access-classified policy path: read and write are independent.
            reg_id = registry.get(entity_id, {}).get("id")
            read_ok = policy.is_allowed(domain, entity_id, reg_id, access="read")
            write_ok = policy.is_allowed(domain, entity_id, reg_id, access="write")
            if not (read_ok or write_ok):
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
            if domain in {"light", "switch"} and domain_services:
                if not {"turn_on", "turn_off"}.intersection(domain_services):
                    continue
            elif domain == "climate" and domain_services:
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
            # Password-mode helpers are fully out of scope: no query, plan, model input or export.
            if domain == "input_text" and features.get("mode") == "password":
                continue

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
                write_ok,
                read_ok,
            )

        # Preserve group semantics as aliases on allowed leaves. Fail closed on cycles/missing membership.
        def leaves(eid, seen):
            if eid in seen or eid not in ha.states:
                return None
            if not policy.is_allowed(eid.split(".")[0], eid, registry.get(eid, {}).get("id")):
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
