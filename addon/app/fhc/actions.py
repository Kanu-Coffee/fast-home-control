"""Capability-derived choices and validated literal binding; never filters by phrasing."""

import math
import re

from .provider import DecisionError

BRIGHTNESS_MODES = {"brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"}
COLOR_MODES = {"hs", "xy", "rgb", "rgbw", "rgbww"}
COLORS = {
    "red": ("빨강 / red", [255, 0, 0]),
    "green": ("초록 / green", [0, 255, 0]),
    "blue": ("파랑 / blue", [0, 0, 255]),
    "yellow": ("노랑 / yellow", [255, 255, 0]),
    "orange": ("주황 / orange", [255, 165, 0]),
    "purple": ("보라 / purple", [128, 0, 128]),
    "white": ("흰색 / white", [255, 255, 255]),
    "pink": ("분홍 / pink", [255, 192, 203]),
    "cyan": ("청록 / cyan", [0, 255, 255]),
    "magenta": ("자홍 / magenta", [255, 0, 255]),
    "lime": ("연두 / lime", [128, 255, 0]),
    "navy": ("남색 / navy", [0, 0, 128]),
}
NUMBER = re.compile(
    r"(?<![\d.])([+−-]?\d+(?:\.\d+)?)\s*(℃|°\s*[cCfF]|℉|도|%|퍼센트|프로|[kK]|켈빈)?"
)


def literals(text):
    return [
        dict(
            id=f"v{i}",
            value=float(m[1].replace("−", "-")),
            unit=(m[2] or "").replace(" ", ""),
            span=[m.start(), m.end()],
            text=m[0],
        )
        for i, m in enumerate(NUMBER.finditer(text))
    ]


def capabilities(domain, state, services, temperature_unit=None):
    a = state.get("attributes", {})
    s = services.get(domain, {})
    f = {"services": sorted(s), "supported_features": a.get("supported_features", 0)}
    if domain == "light":
        f.update(
            {
                k: a.get(k)
                for k in (
                    "supported_color_modes",
                    "min_color_temp_kelvin",
                    "max_color_temp_kelvin",
                    "effect_list",
                )
            }
        )
    if domain == "climate":
        f.update(
            {
                k: a.get(k)
                for k in (
                    "hvac_modes",
                    "min_temp",
                    "max_temp",
                    "target_temp_step",
                    "temperature_unit",
                )
            }
        )
    if domain == "climate" and not f.get("temperature_unit"):
        f["temperature_unit"] = temperature_unit
    return f


def options_for(entity, values):
    f = entity.features
    services = set(f.get("services", []))
    props = {}
    power = {
        "none": "대상이 아님/전원 요청 없음/대상 모호. 이미 같은 상태라는 이유로 none을 선택하지 않음"
    }
    flags = f.get("supported_features", 0)
    for service, flag in [("turn_on", 128), ("turn_off", 256)]:
        if service in services and (entity.domain != "climate" or flags & flag):
            power[service] = (
                "이 대상을 켜라는 명령 (현재 on이어도 선택)"
                if service == "turn_on"
                else "이 대상을 끄라는 명령 (현재 off여도 선택)"
            )
    if len(power) > 1:
        props["power"] = power
    if entity.domain == "climate":
        if "set_hvac_mode" in services:
            props["hvac"] = {
                "none": "모드 변경 요청 없음 / 대상 아님",
                **{
                    m: f"HVAC 모드를 {m}로 설정 (fan_only=송풍/바람만, dry=제습)"
                    for m in f.get("hvac_modes") or []
                },
            }
        if "set_temperature" in services and flags & 1:
            props["temperature"] = {
                "none": "온도 설정 요청 없음 / 대상 아님",
                **{
                    v["id"]: f"이 대상의 목표 온도로 원문 값 {v['text']} (위치 {v['span']}) 선택"
                    for v in values
                    if v["unit"] not in {"%", "프로", "퍼센트", "k", "K", "켈빈"}
                },
            }
    if entity.domain == "light" and "turn_on" in services:
        modes = set(f.get("supported_color_modes") or [])
        if modes & BRIGHTNESS_MODES:
            props["brightness"] = {
                "none": "밝기 변경 요청 없음 / 대상 아님",
                "dim_down": "조금 어둡게: 밝기 10%p 낮춤",
                "dim_up": "조금 밝게: 밝기 10%p 높임",
                **{
                    v["id"]: f"이 대상 밝기를 {v['text']}%로 지정 (위치 {v['span']})"
                    for v in values
                    if v["unit"] in {"", "%", "프로", "퍼센트"}
                },
            }
        if modes & COLOR_MODES:
            props["color"] = {
                "none": "색 변경 요청 없음 / 대상 아님",
                **{key: f"{name} RGB={rgb}" for key, (name, rgb) in COLORS.items()},
            }
        if (
            "color_temp" in modes
            and f.get("min_color_temp_kelvin")
            and f.get("max_color_temp_kelvin")
        ):
            props["color_temp"] = {
                "none": "색온도 변경 요청 없음 / 대상 아님",
                **{
                    v["id"]: f"색온도 Kelvin 원문 {v['text']} (위치 {v['span']})"
                    for v in values
                    if v["unit"] in {"", "K", "k", "켈빈"}
                },
            }
    return {key: criteria for key, criteria in props.items() if len(criteria) > 1}


def temperature(value, f):
    unit = value["unit"]
    native = f.get("temperature_unit")
    if native not in {"°C", "°F"}:
        raise DecisionError("temperature_unit_unknown")
    v = value["value"]
    source = "°F" if unit in {"℉", "°F", "°f"} else "°C" if unit in {"℃", "°C", "°c"} else native
    if source != native:
        v = (v - 32) * 5 / 9 if native == "°C" else v * 9 / 5 + 32
    lo, hi, step = f.get("min_temp"), f.get("max_temp"), f.get("target_temp_step")
    if lo is None or hi is None or not lo <= v <= hi:
        raise DecisionError("temperature_out_of_range")
    if step is not None and (
        step <= 0 or not math.isclose((v - lo) / step, round((v - lo) / step), abs_tol=1e-7)
    ):
        raise DecisionError("temperature_step_invalid")
    return round(v, 8)


def make_action(entity, selected, values):
    by_id = {v["id"]: v for v in values}
    p = {k: v for k, v in selected.items() if v != "none"}
    if not p:
        return None
    data = {}
    service = p.get("power")
    if entity.domain == "light":
        if p.get("power") == "turn_off" and len(p) > 1:
            raise DecisionError("conflicting_actions")
        if b := p.get("brightness"):
            if b in {"dim_down", "dim_up"}:
                data["brightness_step_pct"] = -10 if b == "dim_down" else 10
            else:
                value = by_id[b]["value"]
                if not 1 <= value <= 100:
                    raise DecisionError("brightness_out_of_range")
                data["brightness_pct"] = value
        if c := p.get("color"):
            data["rgb_color"] = COLORS[c][1]
        if ct := p.get("color_temp"):
            if "rgb_color" in data:
                raise DecisionError("conflicting_actions")
            k = by_id[ct]["value"]
            if (
                k != int(k)
                or not entity.features["min_color_temp_kelvin"]
                <= k
                <= entity.features["max_color_temp_kelvin"]
            ):
                raise DecisionError("color_temperature_out_of_range")
            data["color_temp_kelvin"] = int(k)
        if data:
            service = "turn_on"
    elif entity.domain == "climate":
        mode = p.get("hvac")
        if mode and p.get("power"):
            if (p["power"] == "turn_off") != (mode == "off"):
                raise DecisionError("conflicting_actions")
        if t := p.get("temperature"):
            if (
                mode == "off"
                or p.get("power") == "turn_off"
                or (mode or entity.state) == "heat_cool"
            ):
                raise DecisionError("temperature_mode_unsupported")
            data["temperature"] = temperature(by_id[t], entity.features)
            if mode:
                data["hvac_mode"] = mode
            elif p.get("power") == "turn_on":
                # Turning on is a separate physical effect; require explicit supported mode.
                raise DecisionError("explicit_hvac_mode_required")
            service = "set_temperature"
        elif mode:
            service, data = "set_hvac_mode", {"hvac_mode": mode}
    if not service or service not in entity.features["services"]:
        raise DecisionError("service_not_supported")
    return dict(
        entity_id=entity.entity_id,
        name=entity.name,
        domain=entity.domain,
        service=service,
        service_data=data,
        ref=entity.ref,
        status="pending",
        selected=p,
        temperature_unit=entity.features.get("temperature_unit"),
    )


def validate_fresh(entity, action, state, services):
    if state.get("state") in {"unknown", "unavailable", None}:
        raise DecisionError("entity_unavailable")
    fresh = capabilities(entity.domain, state, services, entity.features.get("temperature_unit"))
    if fresh != entity.features:
        raise DecisionError("environment_changed")
    if action["domain"] in {"light", "switch"} and state["state"] not in {"on", "off"}:
        raise DecisionError("entity_unavailable")
    if (
        action["service"] == "set_temperature"
        and state["state"] == "heat_cool"
        and "hvac_mode" not in action["service_data"]
    ):
        raise DecisionError("temperature_mode_unsupported")


def is_already_in_state(action, state):
    service, data = action["service"], action.get("service_data") or {}
    current, attrs = state.get("state"), state.get("attributes", {})
    if service == "turn_off":
        return current == "off"
    if service == "turn_on":
        if current != "on" or "brightness_step_pct" in data:
            return False
        for key, value in data.items():
            if key == "brightness_pct":
                if (
                    attrs.get("brightness") is None
                    or round(attrs["brightness"] / 255 * 100) != value
                ):
                    return False
            elif attrs.get(key) != value:
                return False
        return True
    if service == "set_hvac_mode":
        return current == data["hvac_mode"]
    if service == "set_temperature":
        return attrs.get("temperature") == data["temperature"] and (
            "hvac_mode" not in data or current == data["hvac_mode"]
        )
    return False


def describe_action(action):
    """Explain validated HA service semantics without model-generated execution values."""
    data = action.get("service_data") or {}
    effects = []
    if action["service"] == "turn_off":
        effects.append("전원 끄기")
    elif action["service"] == "turn_on":
        effects.append("전원 켜짐(속성 변경의 HA 부수효과 포함)")
    if "brightness_pct" in data:
        effects.append(f"밝기 {data['brightness_pct']}%")
    if "brightness_step_pct" in data:
        effects.append(f"현재 밝기에서 {data['brightness_step_pct']:+}%p 변경")
    if "rgb_color" in data:
        effects.append(f"색상 RGB {data['rgb_color']}")
    if "color_temp_kelvin" in data:
        effects.append(f"조명 색온도 {data['color_temp_kelvin']} Kelvin")
    if "hvac_mode" in data:
        effects.append(f"HVAC 모드 {data['hvac_mode']}")
    if "temperature" in data:
        effects.append(f"목표 온도 {data['temperature']}{action.get('temperature_unit') or ''}")
    return "; ".join(effects)
