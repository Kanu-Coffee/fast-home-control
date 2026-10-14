"""Capability-derived choices and validated literal binding; never filters by phrasing."""

import math
import re
from datetime import datetime, timedelta

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

QUERY_DOMAINS = {
    "sensor",
    "binary_sensor",
    "weather",
    "calendar",
    "todo",
    "person",
    "device_tracker",
    "zone",
    "sun",
    "event",
    "camera",
    "image",
    "update",
    "input_datetime",
}

# Domains whose initial "unknown" state is normal and must not block execution.
UNKNOWN_OK_DOMAINS = {"button", "tts", *QUERY_DOMAINS}

CONTROL_DOMAINS = {
    "light",
    "switch",
    "climate",
    "vacuum",
    "button",
    "fan",
    "cover",
    "humidifier",
    "media_player",
    "input_boolean",
    "number",
    "input_number",
    "select",
    "input_select",
    "counter",
    "script",
    "automation",
    "scene",
    "input_text",
    "input_datetime",
    "notify",
    "tts",
    "calendar",
    "todo",
    "weather",
    "camera",
}


def literals(text):
    return [
        dict(
            id=f"v{i}",
            value=float(m[1].replace("−", "-")),
            unit=(m[2] or "").replace(" ", ""),
            span=[m.start(), m.end()],
            text=m[0],
            kind="number",
        )
        for i, m in enumerate(NUMBER.finditer(text))
    ]


TIME_RE = re.compile(
    r"(?<![\d:.])(오전|오후|아침|저녁|점심|새벽|밤)?\s*([01]?\d|2[0-3]):([0-5]\d)(?![:\d])"
)
CLOCK_RE = re.compile(
    r"(?<![\d:])(오전|오후|아침|저녁|점심|새벽|밤)?\s*([01]?\d|2[0-3])\s*시(?!간)"
)
# A trailing 분 is consumed with the same span; an invalid minute invalidates the
# whole token instead of silently truncating to the hour (FIX_07 R3).
MINUTE_TAIL_RE = re.compile(r"^\s*(\d{1,2})\s*분")
MONTH_DAY_RE = re.compile(r"(?<![\d])(?:(\d{4})\s*년\s*)?([1-9]|1[0-2])\s*월\s*(\d{1,2})\s*일")
DAY_WORDS = {"모레": 2, "내일": 1, "오늘": 0}
DAY_RE = re.compile("모레|내일|오늘")
AM_WORDS = {"오전", "아침", "새벽"}
PM_WORDS = {"오후", "저녁", "점심"}
QUERY_OPTIONS = {
    "none": "조회 요청 없음 / 대상 아님",
    "query_state": "현재 상태 및 속성 조회",
}


def _clock(hour_text, meridian, minute=0):
    h = int(hour_text)
    if meridian in AM_WORDS and h == 12:
        h = 0
    if meridian in PM_WORDS and h < 12:
        h += 12
    ambiguous = meridian == "밤" and h < 12
    if h > 23:
        return None
    return {
        "hour": h,
        "minute": minute,
        "clock": f"{h:02d}:{minute:02d}",
        "meridian": meridian or "none",
        "ambiguous_period": bool(ambiguous),
    }


def temporal_tokens(text, now=None):
    """Date/time spans as typed tokens; the model selects, the backend binds values.

    A partial span that would silently drop meaning (invalid minute, unsupported
    meridian combination) produces NO truncated candidate token (FIX_07 R3).
    """
    tokens = []
    consumed = []
    for m in TIME_RE.finditer(text):
        parsed = _clock(m[2], m[1], int(m[3]))
        if parsed is None:
            continue
        tokens.append(
            {
                "id": f"t{len(tokens)}",
                "kind": "time",
                **parsed,
                "span": [m.start(), m.end()],
                "text": m[0],
            }
        )
        consumed.append([m.start(), m.end()])
    for m in CLOCK_RE.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        meridian = m.group(1)
        minute = 0
        end = m.end()
        mm = MINUTE_TAIL_RE.match(text[end:])
        if mm:
            if int(mm.group(1)) > 59:
                # "오후 8시 75분": refuse rather than saving 20:00.
                consumed.append([m.start(), end + mm.end()])
                continue
            minute = int(mm.group(1))
            end += mm.end()
        parsed = _clock(m.group(2), meridian, minute)
        if parsed is None:
            continue
        tokens.append(
            {
                "id": f"t{len(tokens)}",
                "kind": "time",
                **parsed,
                "span": [m.start(), end],
                "text": text[m.start() : end],
            }
        )
        consumed.append([m.start(), end])
    d = 0
    for m in DAY_RE.finditer(text):
        word = m.group(0)
        entry = {
            "id": f"d{d}",
            "kind": "day",
            "offset": DAY_WORDS[word],
            "span": [m.start(), m.end()],
            "text": word,
        }
        if now is not None:
            entry["date"] = (now + timedelta(days=DAY_WORDS[word])).date().isoformat()
        tokens.append(entry)
        consumed.append([m.start(), m.end()])
        d += 1
    n = 0
    for m in MONTH_DAY_RE.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        year, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        entry = {
            "id": f"n{n}",
            "kind": "month_day",
            "span": [m.start(), m.end()],
            "text": m.group(0),
        }
        try:
            if year:
                # Explicit year is honoured verbatim; out-of-range fails closed.
                resolved = datetime(int(year), month, day).date()
                entry["date"] = resolved.isoformat()
            elif now is not None:
                date = datetime(now.year, month, day, tzinfo=now.tzinfo)
                if date.date() < now.date():
                    date = datetime(now.year + 1, month, day, tzinfo=now.tzinfo)
                entry["date"] = date.date().isoformat()
        except ValueError:
            consumed.append([m.start(), m.end()])
            continue
        if now is None and year:
            tokens.append(entry)
            consumed.append([m.start(), m.end()])
            n += 1
        elif now is not None and "date" in entry:
            tokens.append(entry)
            consumed.append([m.start(), m.end()])
            n += 1
    return tokens


def calendar_window(rng, now):
    """Resolve a model-selected range token to HA-required start/end boundaries."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if rng == "today":
        return midnight.isoformat(), (midnight + timedelta(days=1)).isoformat()
    if rng == "tomorrow":
        start = midnight + timedelta(days=1)
        return start.isoformat(), (start + timedelta(days=1)).isoformat()
    if rng == "seven_days":
        return midnight.isoformat(), (midnight + timedelta(days=7)).isoformat()
    raise DecisionError("calendar_range_required")


def capabilities(domain, state, services, temperature_unit=None):
    a = state.get("attributes", {})
    s = services.get(domain, {})
    f = {
        "services": sorted(s),
        "supported_features": a.get("supported_features", 0),
        "device_class": a.get("device_class"),
        "unit_of_measurement": a.get("unit_of_measurement"),
    }
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
    elif domain == "climate":
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
        if not f.get("temperature_unit"):
            f["temperature_unit"] = temperature_unit
    elif domain == "fan":
        f.update({k: a.get(k) for k in ("percentage_step", "preset_modes", "speed_count")})
    elif domain == "cover":
        f.update({k: a.get(k) for k in ("current_position", "current_tilt_position")})
    elif domain == "humidifier":
        f.update({k: a.get(k) for k in ("min_humidity", "max_humidity", "available_modes")})
    elif domain == "media_player":
        f.update(
            {
                k: a.get(k)
                for k in ("source_list", "sound_mode_list", "volume_level", "is_volume_muted")
            }
        )
    elif domain in {"number", "input_number", "counter"}:
        f.update({k: a.get(k) for k in ("min", "max", "step")})
    elif domain in {"select", "input_select"}:
        f["options"] = a.get("options") or []
    elif domain == "vacuum":
        f["fan_speed_list"] = a.get("fan_speed_list") or []
    elif domain == "input_text":
        f.update({k: a.get(k) for k in ("min", "max", "mode")})
    elif domain == "weather":
        forecast_flags = a.get("supported_features", 0) or 0
        forecasts = []
        if forecast_flags & 1:
            forecasts.append("daily")
        if forecast_flags & 2:
            forecasts.append("hourly")
        if forecast_flags & 4:
            forecasts.append("twice_daily")
        f["forecast_types"] = forecasts
    elif domain == "input_datetime":
        f.update({k: bool(a.get(k)) for k in ("has_date", "has_time")})
    return f


FORECAST_LABELS = {"hourly": "시간별", "daily": "일별", "twice_daily": "오전/오후"}
# Response-read domains express state query and response query inside ONE mutually
# exclusive choice, so one request cannot produce query+get_events conflicts (R1).
RESPONSE_QUERY_PROPS = {
    "calendar": "calendar_action",
    "todo": "todo_action",
    "weather": "weather_action",
    "input_datetime": "datetime_action",
}


def response_read_options(entity, services, read_allowed=True):
    """Response-query services are gated by READ access, never by write permission."""
    props = {}
    f = entity.features
    if entity.domain == "calendar" and "get_events" in services:
        cal = {"none": "일정 요청 없음"}
        if read_allowed:
            cal["query_state"] = "현재 상태 및 속성 조회"
        cal["get_events"] = "일정 조회"
        props["calendar_action"] = cal
        props["calendar_range"] = {
            "none": "조회 기간 미지정",
            "today": "오늘",
            "tomorrow": "내일",
            "seven_days": "오늘부터 7일",
        }
    if entity.domain == "todo" and "get_items" in services:
        td = {"none": "할 일 요청 없음"}
        if read_allowed:
            td["query_state"] = "현재 상태 및 속성 조회"
        td["get_items"] = "할 일 목록 조회"
        props["todo_action"] = td
    if entity.domain == "weather" and "get_forecasts" in services and f.get("forecast_types"):
        wx = {"none": "날씨 요청 없음"}
        if read_allowed:
            wx["query_state"] = "현재 상태 및 속성 조회"
        wx.update(
            {
                f"get_forecasts_{t}": f"{FORECAST_LABELS[t]} 예보 조회"
                for t in f["forecast_types"]
                if t in FORECAST_LABELS
            }
        )
        props["weather_action"] = wx
    return props


def options_for(entity, values, text="", scope=None, temporal=None):
    f = entity.features
    services = set(f.get("services", []))
    props = {}
    flags = f.get("supported_features", 0)
    read_allowed = getattr(entity, "read_allowed", True)
    write_allowed = getattr(entity, "write_allowed", True)
    temporal = temporal or []
    time_tokens = [x for x in temporal if x["kind"] == "time" and not x.get("ambiguous_period")]
    day_tokens = [x for x in temporal if x["kind"] in {"day", "month_day"}]

    if not write_allowed:
        # Read-only entities: query plus genuine read-only response services only.
        if not read_allowed:
            return {}
        ro = response_read_options(entity, services, read_allowed)
        props.update(ro)
        unified = RESPONSE_QUERY_PROPS.get(entity.domain)
        if not unified or unified not in props:
            props["query"] = dict(QUERY_OPTIONS)
        return {key: criteria for key, criteria in props.items() if len(criteria) > 1}

    # 1. Power (on/off)
    power = {
        "none": "대상이 아님/전원 요청 없음/대상 모호. 이미 같은 상태라는 이유로 none을 선택하지 않음"
    }
    for service, flag in [("turn_on", 128), ("turn_off", 256)]:
        if service in services and (entity.domain != "climate" or flags & flag):
            power[service] = (
                "이 대상을 켜라는 명령 (현재 on이어도 선택)"
                if service == "turn_on"
                else "이 대상을 끄라는 명령 (현재 off여도 선택)"
            )
    if len(power) > 1 and entity.domain in {
        "light",
        "switch",
        "climate",
        "fan",
        "humidifier",
        "media_player",
        "input_boolean",
    }:
        props["power"] = power

    # 2. Climate
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
        if "set_fan_mode" in services and f.get("fan_modes"):
            props["climate_fan"] = {
                "none": "팬 모드 요청 없음",
                **{m: f"공조 팬 모드 '{m}'" for m in f["fan_modes"]},
            }
        if "set_preset_mode" in services and f.get("preset_modes"):
            props["climate_preset"] = {
                "none": "프리셋 모드 요청 없음",
                **{m: f"공조 프리셋 '{m}'" for m in f["preset_modes"]},
            }
        if "set_swing_mode" in services and f.get("swing_modes"):
            props["climate_swing"] = {
                "none": "스윙/바람방향 요청 없음",
                **{m: f"공조 스윙 모드 '{m}'" for m in f["swing_modes"]},
            }

    # 3. Light
    elif entity.domain == "light" and "turn_on" in services:
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
        if f.get("effect_list"):
            props["effect"] = {
                "none": "효과 요청 없음",
                **{e: f"조명 효과 '{e}'" for e in f["effect_list"]},
            }

    # 4. Vacuum
    elif entity.domain == "vacuum":
        vac = {"none": "대상이 아님/요청 없음"}
        for s, desc in [
            ("start", "청소 시작"),
            ("pause", "청소 일시 정지"),
            ("stop", "청소 정지"),
            ("return_to_base", "충전대/도크 복귀"),
        ]:
            if s in services:
                vac[s] = desc
        if len(vac) > 1:
            props["vacuum_action"] = vac
        if "set_fan_speed" in services and f.get("fan_speed_list"):
            props["fan_speed"] = {
                "none": "흡입력/팬속도 요청 없음",
                **{s: f"청소기 흡입 강도 '{s}'" for s in f["fan_speed_list"]},
            }

    # 5. Button
    elif entity.domain == "button":
        if "press" in services:
            props["button_action"] = {
                "none": "대상이 아님/누름 요청 없음",
                "press": "버튼 누름",
            }

    # 6. Fan
    elif entity.domain == "fan":
        if "set_percentage" in services and (flags & 1) and values:
            props["percentage"] = {
                "none": "풍속/비율 요청 없음",
                **{
                    v["id"]: f"풍속 {v['text']}% 설정"
                    for v in values
                    if v["unit"] in {"", "%", "프로", "퍼센트"} and 0 <= v["value"] <= 100
                },
            }
        if "oscillate" in services and (flags & 2):
            props["oscillate"] = {
                "none": "회전 요청 없음",
                "oscillate_on": "회전 켜기",
                "oscillate_off": "회전 끄기",
            }
        if "set_direction" in services and (flags & 4):
            props["direction"] = {
                "none": "방향 요청 없음",
                "forward": "정방향(forward)",
                "reverse": "역방향(reverse)",
            }
        if "set_preset_mode" in services and (flags & 8) and f.get("preset_modes"):
            props["preset_mode"] = {
                "none": "모드 요청 없음",
                **{m: f"팬 모드 '{m}'" for m in f["preset_modes"]},
            }

    # 7. Cover
    elif entity.domain == "cover":
        cov = {"none": "대상이 아님/요청 없음"}
        for s, desc, flag in [
            ("open_cover", "열기", 1),
            ("close_cover", "닫기", 2),
            ("stop_cover", "정지", 8),
        ]:
            if s in services and (flags & flag):
                cov[s] = desc
        if len(cov) > 1:
            props["cover_action"] = cov
        if "set_cover_position" in services and (flags & 4) and values:
            props["position"] = {
                "none": "위치(%) 요청 없음",
                **{
                    v["id"]: f"위치 {v['text']}%로 열림/조절"
                    for v in values
                    if v["unit"] in {"", "%", "프로", "퍼센트"} and 0 <= v["value"] <= 100
                },
            }
        if (
            ("set_cover_tilt_position" in services or "open_cover_tilt" in services)
            and (flags & 128)
            and values
        ):
            props["tilt_position"] = {
                "none": "틸트/기울기 요청 없음",
                **{
                    v["id"]: f"틸트 {v['text']}% 설정"
                    for v in values
                    if v["unit"] in {"", "%", "프로", "퍼센트"} and 0 <= v["value"] <= 100
                },
            }

    # 8. Humidifier
    elif entity.domain == "humidifier":
        min_h = f.get("min_humidity", 0)
        max_h = f.get("max_humidity", 100)
        if "set_humidity" in services and values:
            props["humidity"] = {
                "none": "습도 요청 없음",
                **{
                    v["id"]: f"목표 습도 {v['text']}%"
                    for v in values
                    if v["unit"] in {"", "%", "프로", "퍼센트"} and min_h <= v["value"] <= max_h
                },
            }
        if "set_mode" in services and f.get("available_modes"):
            props["mode"] = {
                "none": "모드 요청 없음",
                **{m: f"가습 모드 {m}" for m in f["available_modes"]},
            }

    # 9. Media Player
    elif entity.domain == "media_player":
        media = {"none": "재생 제어 요청 없음"}
        for s, desc, flag in [
            ("media_play", "재생", 16384),
            ("media_pause", "일시정지", 1),
            ("media_stop", "정지", 4096),
            ("media_next_track", "다음 곡", 32),
            ("media_previous_track", "이전 곡", 16),
        ]:
            if s in services and (flags & flag):
                media[s] = desc
        if len(media) > 1:
            props["media_control"] = media
        if "volume_mute" in services and (flags & 8):
            props["mute"] = {
                "none": "음소거 요청 없음",
                "mute": "음소거 켜기",
                "unmute": "음소거 해제",
            }
        if "volume_set" in services and (flags & 4) and values:
            props["volume"] = {
                "none": "볼륨 크기 요청 없음",
                **{
                    v["id"]: f"볼륨 {v['text']}%"
                    for v in values
                    if v["unit"] in {"", "%", "프로", "퍼센트"} and 0 <= v["value"] <= 100
                },
            }
        if "select_source" in services and (flags & 2048) and f.get("source_list"):
            props["source"] = {
                "none": "외부입력/소스 요청 없음",
                **{s: f"소스 '{s}'" for s in f["source_list"]},
            }
        if "select_sound_mode" in services and (flags & 65536) and f.get("sound_mode_list"):
            props["sound_mode"] = {
                "none": "사운드 모드 요청 없음",
                **{m: f"사운드 모드 '{m}'" for m in f["sound_mode_list"]},
            }
        # FIX_07 R1: broadcast output is one ordinary per-target yes/no decision.
        # The engine binds the chosen speaker to the tts speak action.
        if scope and any(e.domain == "tts" for e in scope.values()):
            props["broadcast_output"] = {
                "none": "이 스피커로 방송하지 않음",
                "output": f"원문의 방송을 이 스피커({entity.name}, {entity.area})로 출력",
            }

    # 10. Number / Input Number
    elif entity.domain in {"number", "input_number"}:
        lo, hi = f.get("min", -1e9), f.get("max", 1e9)
        step = f.get("step")
        if "set_value" in services and values:
            valid_vals = {}
            for v in values:
                val = v["value"]
                if lo <= val <= hi:
                    if step and step > 0:
                        rem = abs((val - lo) % step)
                        if not (
                            math.isclose(rem, 0, abs_tol=1e-4)
                            or math.isclose(rem, step, abs_tol=1e-4)
                        ):
                            continue
                    valid_vals[v["id"]] = f"값 {v['text']} 설정"
            if valid_vals:
                props["number_value"] = {
                    "none": "수치 설정 요청 없음",
                    **valid_vals,
                }
        if entity.domain == "input_number":
            inc_dec = {"none": "증감 요청 없음"}
            if "increment" in services:
                inc_dec["increment"] = "+1단계(step) 증가"
            if "decrement" in services:
                inc_dec["decrement"] = "-1단계(step) 감소"
            if len(inc_dec) > 1:
                props["step_action"] = inc_dec

    # 11. Select / Input Select
    elif entity.domain in {"select", "input_select"}:
        if "select_option" in services and f.get("options"):
            props["select_option"] = {
                "none": "옵션 선택 요청 없음",
                **{opt: f"옵션 '{opt}' 선택" for opt in f["options"]},
            }
        props["select_step"] = {
            "none": "이동 요청 없음",
            "next": "다음 옵션",
            "previous": "이전 옵션",
            "first": "첫 번째 옵션",
            "last": "마지막 옵션",
        }

    # 12. Counter
    elif entity.domain == "counter":
        cnt = {"none": "카운터 요청 없음"}
        for s, desc in [
            ("increment", "+1 증가"),
            ("decrement", "-1 감소"),
            ("reset", "리셋"),
        ]:
            if s in services:
                cnt[s] = desc
        if len(cnt) > 1:
            props["counter_action"] = cnt
        if "set_value" in services and values:
            props["counter_value"] = {
                "none": "값 설정 요청 없음",
                **{v["id"]: f"카운터 값 {v['text']} 설정" for v in values},
            }

    # 13. Script / Automation / Scene
    elif entity.domain == "script":
        props["script_action"] = {
            "none": "스크립트 요청 없음",
            "turn_on": "스크립트 실행",
            "turn_off": "스크립트 중단",
        }
    elif entity.domain == "automation":
        props["automation_action"] = {
            "none": "자동화 요청 없음",
            "trigger": "자동화 즉시 실행",
            "turn_on": "자동화 활성화",
            "turn_off": "자동화 비활성화",
        }
    elif entity.domain == "scene":
        props["scene_action"] = {
            "none": "장면 요청 없음",
            "turn_on": "장면 활성화",
        }

    # 14. Text / Notify / TTS. TTS engine and output speaker are separate ordinary
    # targets (one yes/no decision per entity), wired together by the engine.
    elif entity.domain in {"input_text", "notify", "tts"}:
        if entity.domain != "input_text" or f.get("mode") != "password":
            props["text_action"] = {
                "none": "메시지/텍스트 요청 없음",
                "apply": "원문 문구 전송/설정",
            }

    # 15. Calendar / Todo / Weather / Input datetime / Camera (only real, discovered services)
    elif entity.domain == "calendar":
        cal = {"none": "일정 요청 없음"}
        if read_allowed:
            cal["query_state"] = "현재 상태 및 속성 조회"
        if "get_events" in services:
            cal["get_events"] = "일정 조회(기간 선택 필요)"
        if "create_event" in services:
            cal["create_event"] = "새 일정 생성"
        if len(cal) > 1:
            props["calendar_action"] = cal
        if "get_events" in services:
            props["calendar_range"] = {
                "none": "조회 기간 미지정",
                "today": "오늘",
                "tomorrow": "내일",
                "seven_days": "오늘부터 7일",
            }
        if "create_event" in services:
            props["calendar_day"] = {
                "none": "일정 날짜 미지정",
                "today": "오늘",
                "tomorrow": "내일",
                "day_after": "모레",
            }
            if time_tokens:
                props["calendar_time"] = {
                    "none": "시작 시간 미지정(하루 종일 일정)",
                    **{
                        t["id"]: f"시작 시간 {t['clock']} 원문 {t['text']} (위치 {t['span']})"
                        for t in time_tokens
                    },
                }
                props["calendar_end_time"] = {
                    "none": "종료 시간 없음 — 시간 일정에는 종료 필수",
                    **{
                        t["id"]: f"종료 시간 {t['clock']} 원문 {t['text']} (위치 {t['span']})"
                        for t in time_tokens
                    },
                }
    elif entity.domain == "todo":
        td = {"none": "할 일 요청 없음"}
        if read_allowed:
            td["query_state"] = "현재 상태 및 속성 조회"
        for svc, desc in [
            ("get_items", "할 일 목록 조회"),
            ("add_item", "할 일 추가"),
            ("update_item", "할 일 완료/수정"),
            ("remove_item", "할 일 삭제"),
        ]:
            if svc in services:
                td[svc] = desc
        if len(td) > 1:
            props["todo_action"] = td
        if "update_item" in services:
            props["todo_status"] = {
                "none": "변경할 상태 미지정",
                "completed": "완료로 표시",
                "needs_action": "미완료로 되돌림",
            }
    elif entity.domain == "weather":
        read_props = response_read_options(entity, services, read_allowed)
        if "weather_action" in read_props:
            props["weather_action"] = read_props["weather_action"]
    elif entity.domain == "input_datetime":
        if "set_datetime" in services:
            dt = {"none": "설정 없음"}
            if read_allowed:
                dt["query_state"] = "현재 상태 및 속성 조회"
            dt["set_datetime"] = "날짜/시간 설정"
            props["datetime_action"] = dt
            if f.get("has_time") and time_tokens:
                props["datetime_time_value"] = {
                    "none": "시간 값 없음",
                    **{
                        t["id"]: f"시간 {t['clock']} 원문 {t['text']} (위치 {t['span']})"
                        for t in time_tokens
                    },
                }
            if f.get("has_date") and day_tokens:
                props["datetime_day_value"] = {
                    "none": "날짜 값 없음",
                    **{
                        d["id"]: f"날짜 {d.get('date', '')} 원문 {d['text']} (위치 {d['span']})"
                        for d in day_tokens
                    },
                }
    elif entity.domain == "camera":
        cam = {"none": "카메라 요청 없음"}
        for svc, desc in [
            ("turn_on", "카메라 켜기"),
            ("turn_off", "카메라 끄기"),
            ("enable_motion_detection", "모션 감지 켜기"),
            ("disable_motion_detection", "모션 감지 끄기"),
        ]:
            if svc in services:
                cam[svc] = desc
        if len(cam) > 1:
            props["camera_action"] = cam

    # 16. Query / Status Inspection (only when read access is allowed by policy).
    # Response-read domains carry query_state inside their single action choice;
    # if that choice is absent (no supported response service), fall back to the
    # plain query property so state queries never disappear.
    unified = RESPONSE_QUERY_PROPS.get(entity.domain)
    if read_allowed and (not unified or unified not in props):
        props["query"] = dict(QUERY_OPTIONS)

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


def extract_message(text):
    # 1. Quoted text
    qm = re.search(r"[\"']([^\"']+)[\"']", text)
    if qm:
        val = qm.group(1).strip()
        if val:
            return val

    # 2. Pattern: [대상에/로] ~라고 [말해|입력|보내|전송|방송|써|출력|기록|남겨]
    # e.g. "입력란에 오늘 저녁 7시 회의라고 입력해줘" -> "오늘 저녁 7시 회의"
    m1 = re.search(
        r".+?(?:란에|란|에|으로|로|은|는)\s+(.+?)(?:이?라고|이라\s*고)\s*(?:입력|보내|전송|말해|방송|써|출력|기록|남겨)",
        text,
    )
    if m1:
        val = m1.group(1).strip()
        if val:
            return val

    m1_direct = re.search(
        r"^(.+?)(?:이?라고|이라\s*고)\s*(?:입력|보내|전송|말해|방송|써|출력|기록|남겨)",
        text,
    )
    if m1_direct:
        val = m1_direct.group(1).strip()
        if val:
            return val

    # 3. Pattern: ~에 ~ [보내|전송|입력|말해|방송|출력|써]
    # e.g. "거실 알림에 안녕 보내줘" -> "안녕"
    m2 = re.search(r"(?:.+?[에으로]\s+)(.+?)\s+(?:보내|전송|입력|말해|방송|출력|써)", text)
    if m2:
        val = m2.group(1).strip()
        val = re.sub(r"(?:이?라고)$", "", val).strip()
        if val:
            return val

    # 4. Pattern: [내용|메시지|텍스트]는? ~ [보내|입력]
    m3 = re.search(
        r"(?:내용|메시지|텍스트)(?:은|는)?\s*([^\n]+?)\s*(?:보내|전송|입력|말해|써)", text
    )
    if m3:
        val = m3.group(1).strip()
        if val:
            return val

    raise DecisionError("invalid_message_span")


def make_actions(entity, selected, values=None, text="", scope=None, temporal=None, now=None):
    values = values or []
    temporal = temporal or []
    by_id = {v["id"]: v for v in values}
    p = {k: v for k, v in selected.items() if v != "none"}
    if not p:
        return []
    if entity.domain == "media_player" and set(p) == {"broadcast_output"}:
        # Pure output-speaker nomination: consumed by the engine's speak wiring.
        return []

    def create_action(service, data=None, is_query=False, return_response=False):
        data = data or {}
        if service not in entity.features.get("services", []) and not is_query:
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
            is_query=is_query,
            return_response=return_response,
            access="read" if is_query or return_response else "write",
        )

    # Check query conflict (unified: response-read domains select query_state
    # inside their action choice, so it is structurally exclusive with others)
    if (
        p.get("query") == "query_state"
        or p.get(RESPONSE_QUERY_PROPS.get(entity.domain, ""), "") == "query_state"
    ):
        if len(p) > 1:
            raise DecisionError("conflicting_actions")
        if entity.domain == "input_text" and entity.features.get("mode") == "password":
            raise DecisionError("sensitive_input_protected")
        if not getattr(entity, "read_allowed", True):
            raise DecisionError("read_policy_denied")
        return [create_action("query_state", is_query=True)]

    # Light
    if entity.domain == "light":
        if p.get("power") == "turn_off" and len(p) > 1:
            raise DecisionError("conflicting_actions")
        data = {}
        service = p.get("power")
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
        if eff := p.get("effect"):
            data["effect"] = eff
        if data:
            service = "turn_on"
        if not service:
            raise DecisionError("no_unambiguous_action")
        return [create_action(service, data)]

    # Climate
    if entity.domain == "climate":
        mode = p.get("hvac")
        power = p.get("power")
        if mode and power:
            if (power == "turn_off") != (mode == "off"):
                raise DecisionError("conflicting_actions")
        if power == "turn_off" and (
            p.get("temperature")
            or p.get("climate_fan")
            or p.get("climate_preset")
            or p.get("climate_swing")
        ):
            raise DecisionError("conflicting_actions")
        actions = []
        if t := p.get("temperature"):
            if mode == "off" or power == "turn_off" or (mode or entity.state) == "heat_cool":
                raise DecisionError("temperature_mode_unsupported")
            t_data = {"temperature": temperature(by_id[t], entity.features)}
            if mode:
                t_data["hvac_mode"] = mode
            elif power == "turn_on":
                raise DecisionError("explicit_hvac_mode_required")
            actions.append(create_action("set_temperature", t_data))
        elif mode:
            actions.append(create_action("set_hvac_mode", {"hvac_mode": mode}))
        elif power:
            actions.append(create_action(power, {}))

        if fan := p.get("climate_fan"):
            actions.append(create_action("set_fan_mode", {"fan_mode": fan}))
        if preset := p.get("climate_preset"):
            actions.append(create_action("set_preset_mode", {"preset_mode": preset}))
        if swing := p.get("climate_swing"):
            actions.append(create_action("set_swing_mode", {"swing_mode": swing}))

        if not actions:
            raise DecisionError("no_unambiguous_action")
        return actions

    # Vacuum
    if entity.domain == "vacuum":
        actions = []
        if action_name := p.get("vacuum_action"):
            actions.append(create_action(action_name, {}))
        if spd := p.get("fan_speed"):
            actions.append(create_action("set_fan_speed", {"fan_speed": spd}))
        if not actions:
            raise DecisionError("no_unambiguous_action")
        return actions

    # Button
    if entity.domain == "button":
        if p.get("button_action") == "press":
            return [create_action("press", {})]
        raise DecisionError("no_unambiguous_action")

    # Fan
    if entity.domain == "fan":
        if p.get("power") == "turn_off" and (
            p.get("percentage") or p.get("oscillate") or p.get("preset_mode") or p.get("direction")
        ):
            raise DecisionError("conflicting_actions")
        attrs = []
        if pct := p.get("percentage"):
            attrs.append(create_action("set_percentage", {"percentage": int(by_id[pct]["value"])}))
        if osc := p.get("oscillate"):
            attrs.append(create_action("oscillate", {"oscillating": osc == "oscillate_on"}))
        if preset := p.get("preset_mode"):
            attrs.append(create_action("set_preset_mode", {"preset_mode": preset}))
        if direction := p.get("direction"):
            attrs.append(create_action("set_direction", {"direction": direction}))
        # Explicit power is a separate requested effect: keep turn_on before attrs.
        power = p.get("power")
        actions = ([create_action(power, {})] if power else []) + attrs
        if not actions:
            raise DecisionError("no_unambiguous_action")
        return actions

    # Cover
    if entity.domain == "cover":
        if (p.get("power") or p.get("cover_action")) and (
            p.get("position") or p.get("tilt_position")
        ):
            raise DecisionError("conflicting_actions")
        actions = []
        if cov := p.get("cover_action"):
            actions.append(create_action(cov, {}))
        elif pos := p.get("position"):
            actions.append(
                create_action("set_cover_position", {"position": int(by_id[pos]["value"])})
            )
        elif tilt := p.get("tilt_position"):
            actions.append(
                create_action(
                    "set_cover_tilt_position", {"tilt_position": int(by_id[tilt]["value"])}
                )
            )
        elif power := p.get("power"):
            actions.append(create_action("open_cover" if power == "turn_on" else "close_cover", {}))
        if not actions:
            raise DecisionError("no_unambiguous_action")
        return actions

    # Humidifier
    if entity.domain == "humidifier":
        if p.get("power") == "turn_off" and (p.get("humidity") or p.get("mode")):
            raise DecisionError("conflicting_actions")
        attrs = []
        if hum := p.get("humidity"):
            attrs.append(create_action("set_humidity", {"humidity": int(by_id[hum]["value"])}))
        if m := p.get("mode"):
            attrs.append(create_action("set_mode", {"mode": m}))
        power = p.get("power")
        actions = ([create_action(power, {})] if power else []) + attrs
        if not actions:
            raise DecisionError("no_unambiguous_action")
        return actions

    # Media Player
    if entity.domain == "media_player":
        if p.get("power") == "turn_off" and (
            p.get("media_control")
            or p.get("volume")
            or p.get("mute")
            or p.get("source")
            or p.get("sound_mode")
        ):
            raise DecisionError("conflicting_actions")
        if p.get("mute") and p.get("volume"):
            raise DecisionError("conflicting_actions")
        attrs = []
        if mc := p.get("media_control"):
            attrs.append(create_action(mc, {}))
        if mute := p.get("mute"):
            attrs.append(create_action("volume_mute", {"is_volume_muted": mute == "mute"}))
        if vol := p.get("volume"):
            attrs.append(
                create_action("volume_set", {"volume_level": round(by_id[vol]["value"] / 100, 2)})
            )
        if src := p.get("source"):
            attrs.append(create_action("select_source", {"source": src}))
        if sm := p.get("sound_mode"):
            attrs.append(create_action("select_sound_mode", {"sound_mode": sm}))
        power = p.get("power")
        actions = ([create_action(power, {})] if power else []) + attrs
        if not actions:
            raise DecisionError("no_unambiguous_action")
        return actions

    # Number / Input Number
    if entity.domain in {"number", "input_number"}:
        if nv := p.get("number_value"):
            val = by_id[nv]["value"]
            lo, hi = entity.features.get("min", -1e9), entity.features.get("max", 1e9)
            step = entity.features.get("step")
            if not (lo <= val <= hi):
                raise DecisionError("number_out_of_range")
            if step and step > 0:
                rem = abs((val - lo) % step)
                if not (
                    math.isclose(rem, 0, abs_tol=1e-4) or math.isclose(rem, step, abs_tol=1e-4)
                ):
                    raise DecisionError("number_step_invalid")
            return [create_action("set_value", {"value": val})]
        elif step_act := p.get("step_action"):
            return [create_action(step_act, {})]

    # Select / Input Select
    if entity.domain in {"select", "input_select"}:
        if opt := p.get("select_option"):
            return [create_action("select_option", {"option": opt})]
        elif step_opt := p.get("select_step"):
            return [create_action(f"select_{step_opt}", {})]

    # Counter
    if entity.domain == "counter":
        if ca := p.get("counter_action"):
            return [create_action(ca, {})]
        elif cv := p.get("counter_value"):
            return [create_action("set_value", {"value": int(by_id[cv]["value"])})]

    # Script / Automation / Scene
    if entity.domain == "script":
        if svc := p.get("script_action"):
            return [create_action(svc, {})]
    elif entity.domain == "automation":
        if svc := p.get("automation_action"):
            if svc == "trigger":
                return [create_action("trigger", {"skip_condition": False})]
            elif svc == "turn_off":
                return [create_action("turn_off", {"stop_actions": True})]
            elif svc == "turn_on":
                return [create_action("turn_on", {})]
    elif entity.domain == "scene":
        if svc := p.get("scene_action"):
            return [create_action(svc, {})]

    # Input Text / Notify / TTS
    if entity.domain == "input_text":
        if entity.features.get("mode") == "password":
            raise DecisionError("sensitive_input_protected")
        clean = extract_message(text)
        min_len = entity.features.get("min", 0) or 0
        max_len = entity.features.get("max", 255) or 255
        if not (min_len <= len(clean) <= max_len):
            raise DecisionError("text_length_invalid")
        return [create_action("set_value", {"value": clean})]
    elif entity.domain == "notify":
        return [create_action("send_message", {"message": extract_message(text)})]
    elif entity.domain == "tts":
        out_ref = p.get("tts_output")
        if not out_ref:
            raise DecisionError("tts_output_target_required")
        target = (scope or {}).get(out_ref)
        if target is None or target.domain != "media_player":
            raise DecisionError("tts_output_target_required")
        if not getattr(target, "write_allowed", True):
            raise DecisionError("output_policy_denied")
        action = create_action(
            "speak",
            {"message": extract_message(text), "media_player_entity_id": target.entity_id},
        )
        action["secondary"] = {
            "ref": out_ref,
            "entity_id": target.entity_id,
            "name": target.name,
            "domain": "media_player",
        }
        return [action]

    # Calendar / Todo / Weather / Input Datetime / Camera
    if entity.domain == "calendar":
        act = p.get("calendar_action")
        if act == "get_events":
            if now is None or now.tzinfo is None:
                raise DecisionError("timezone_unknown")
            start, end = calendar_window(p.get("calendar_range"), now)
            return [
                create_action(
                    "get_events",
                    {"start_date_time": start, "end_date_time": end},
                    return_response=True,
                )
            ]
        elif act == "create_event":
            day = p.get("calendar_day")
            if day not in {"today", "tomorrow", "day_after"}:
                raise DecisionError("calendar_start_required")
            if now is None or now.tzinfo is None:
                raise DecisionError("timezone_unknown")
            base = now + timedelta(days={"today": 0, "tomorrow": 1, "day_after": 2}[day])
            data = {"summary": extract_message(text)}
            tid = p.get("calendar_time")
            if tid:
                tok = next(
                    (x for x in temporal if x["id"] == tid and x["kind"] == "time"),
                    None,
                )
                if tok is None or tok.get("ambiguous_period"):
                    raise DecisionError("calendar_time_invalid")
                eid = p.get("calendar_end_time")
                if not eid:
                    # No invented duration: a timed event requires an explicit end.
                    raise DecisionError("calendar_end_required")
                etok = next(
                    (x for x in temporal if x["id"] == eid and x["kind"] == "time"),
                    None,
                )
                if etok is None or etok.get("ambiguous_period"):
                    raise DecisionError("calendar_time_invalid")
                start_dt = base.replace(
                    hour=tok["hour"], minute=tok["minute"], second=0, microsecond=0
                )
                end_dt = base.replace(
                    hour=etok["hour"], minute=etok["minute"], second=0, microsecond=0
                )
                if end_dt <= start_dt:
                    raise DecisionError("calendar_time_invalid")
                data["start_date_time"] = start_dt.isoformat()
                data["end_date_time"] = end_dt.isoformat()
            else:
                if p.get("calendar_end_time"):
                    raise DecisionError("calendar_time_invalid")
                data["start_date"] = base.date().isoformat()
                data["end_date"] = (base + timedelta(days=1)).date().isoformat()
            return [create_action("create_event", data)]
    elif entity.domain == "todo":
        act = p.get("todo_action")
        if act == "get_items":
            return [
                create_action(
                    "get_items",
                    {"status": ["needs_action", "completed"]},
                    return_response=True,
                )
            ]
        elif act == "add_item":
            return [create_action("add_item", {"item": extract_message(text)})]
        elif act == "update_item":
            status = p.get("todo_status")
            if status not in {"completed", "needs_action"}:
                raise DecisionError("todo_status_required")
            return [create_action("update_item", {"item": extract_message(text), "status": status})]
        elif act == "remove_item":
            return [create_action("remove_item", {"item": extract_message(text)})]
    elif entity.domain == "weather":
        act = p.get("weather_action")
        if isinstance(act, str) and act.startswith("get_forecasts_"):
            ftype = act.removeprefix("get_forecasts_")
            if ftype not in (entity.features.get("forecast_types") or []):
                raise DecisionError("forecast_type_unsupported")
            return [create_action("get_forecasts", {"type": ftype}, return_response=True)]
    elif entity.domain == "input_datetime":
        if p.get("datetime_action") == "set_datetime":
            features = entity.features
            time_tok = day_tok = None
            if tid := p.get("datetime_time_value"):
                time_tok = next((x for x in temporal if x["id"] == tid), None)
                if time_tok is None:
                    raise DecisionError("datetime_value_invalid")
            if did := p.get("datetime_day_value"):
                day_tok = next((x for x in temporal if x["id"] == did), None)
                if day_tok is None:
                    raise DecisionError("datetime_value_invalid")
            if time_tok is None and day_tok is None:
                raise DecisionError("datetime_value_required")
            data = {}
            if time_tok is not None:
                if not features.get("has_time"):
                    raise DecisionError("datetime_value_invalid")
                if time_tok["kind"] != "time" or time_tok.get("ambiguous_period"):
                    raise DecisionError("datetime_value_invalid")
                data["time"] = f"{time_tok['hour']:02d}:{time_tok['minute']:02d}:00"
            if day_tok is not None:
                if not features.get("has_date"):
                    raise DecisionError("datetime_value_invalid")
                if day_tok["kind"] not in {"day", "month_day"} or not day_tok.get("date"):
                    raise DecisionError("datetime_value_invalid")
                data["date"] = day_tok["date"]
            if "date" in data and "time" in data:
                # A has_date+has_time helper receives one combined datetime value.
                data = {"datetime": f"{data['date']} {data['time']}"}
            return [create_action("set_datetime", data)]
    elif entity.domain == "camera":
        if cam := p.get("camera_action"):
            return [create_action(cam, {})]

    # Input Boolean / Switch
    if entity.domain in {"input_boolean", "switch"}:
        if power := p.get("power"):
            return [create_action(power, {})]

    raise DecisionError("no_unambiguous_action")


def make_action(entity, selected, values, text="", scope=None, temporal=None, now=None):
    actions = make_actions(
        entity, selected, values, text=text, scope=scope, temporal=temporal, now=now
    )
    return actions[0] if actions else None


def validate_fresh(entity, action, state, services, policy=None, identity=None):
    raw_st = state.get("state")
    if raw_st in {"unavailable", None}:
        raise DecisionError("entity_unavailable")
    # Button and query states may be unknown initially, which is valid
    if raw_st == "unknown" and action.get("domain") not in UNKNOWN_OK_DOMAINS:
        raise DecisionError("entity_unavailable")

    attrs = state.get("attributes", {})
    # Sensitive state is decided by the entity's actual mode, never by ID substrings.
    if action["domain"] == "input_text" and attrs.get("mode") == "password":
        raise DecisionError("sensitive_input_protected")

    if policy is not None:
        access = action.get("access", "write")
        if not policy.is_allowed(action["domain"], action["entity_id"], identity, access=access):
            raise DecisionError(
                "read_policy_denied" if access == "read" else "control_policy_denied"
            )

    # Sensitive cover classes check (e.g., garage door / gate)
    if action["domain"] == "cover":
        dev_class = entity.features.get("device_class")
        if dev_class in {"garage", "gate"}:
            raise DecisionError("sensitive_cover_protected")

    if action.get("is_query"):
        return

    domain_services = services.get(action["domain"], {})
    if action["service"] not in domain_services:
        raise DecisionError("environment_changed")
    if action.get("return_response"):
        # Response queries are still availability-, policy- and service-validated above.
        return

    fresh = capabilities(entity.domain, state, services, entity.features.get("temperature_unit"))
    if fresh != entity.features:
        raise DecisionError("environment_changed")
    if action["domain"] in {"light", "switch", "input_boolean"} and state["state"] not in {
        "on",
        "off",
    }:
        raise DecisionError("entity_unavailable")
    if (
        action["service"] == "set_temperature"
        and state["state"] == "heat_cool"
        and "hvac_mode" not in action["service_data"]
    ):
        raise DecisionError("temperature_mode_unsupported")


def is_already_in_state(action, state):
    if action.get("is_query") or action.get("return_response"):
        return False
    service, data = action["service"], action.get("service_data") or {}
    current, attrs = state.get("state"), state.get("attributes", {})

    # Non-idempotent, pulse actions, automation stop_actions, or script turn_on are never already in state
    if (
        service
        in {
            "press",
            "increment",
            "decrement",
            "reset",
            "trigger",
            "send_message",
            "speak",
        }
        or (service == "turn_off" and action.get("domain") == "automation")
        or (service == "turn_on" and action.get("domain") == "script")
    ):
        return False

    if service in {"turn_off", "close_cover"}:
        return current in {"off", "closed"}
    if service in {"turn_on", "open_cover"}:
        if service == "open_cover":
            return current == "open"
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
        return current == data.get("hvac_mode")
    if service == "set_temperature":
        return attrs.get("temperature") == data.get("temperature") and (
            "hvac_mode" not in data or current == data["hvac_mode"]
        )
    if service == "return_to_base":
        return current in {"docked", "returning"}
    if service == "start":
        return current == "cleaning"
    if service == "set_cover_position":
        return attrs.get("current_position") == data.get("position")
    if service == "set_percentage":
        return attrs.get("percentage") == data.get("percentage")
    if service == "set_humidity":
        return attrs.get("humidity") == data.get("humidity")
    if service == "volume_set":
        return attrs.get("volume_level") is not None and round(
            attrs["volume_level"], 2
        ) == data.get("volume_level")
    if service == "set_value":
        return current == str(data.get("value"))
    if service == "select_option":
        return current == data.get("option")
    return False


def describe_action(action):
    """Explain validated HA service semantics without model-generated execution values."""
    if action.get("is_query"):
        return "현재 상태 및 속성 조회"
    service = action["service"]
    data = action.get("service_data") or {}
    effects = []
    if service == "turn_off":
        if action.get("domain") == "automation":
            effects.append("자동화 비활성화 및 실행 중 동작 중단")
        else:
            effects.append("전원 끄기")
    elif service == "turn_on":
        effects.append("전원 켜기")
    elif service == "press":
        effects.append("버튼 누름")
    elif service == "return_to_base":
        effects.append("충전대로 복귀")
    elif service == "start":
        effects.append("청소 시작")
    elif service == "pause":
        effects.append("일시 정지")
    elif service == "stop":
        effects.append("동작 정지")
    elif service == "set_fan_speed":
        effects.append(f"흡입력 '{data.get('fan_speed')}'")
    elif service == "open_cover":
        effects.append("열기")
    elif service == "close_cover":
        effects.append("닫기")
    elif service == "set_cover_position":
        effects.append(f"위치 {data.get('position')}%")
    elif service == "set_cover_tilt_position":
        effects.append(f"틸트 {data.get('tilt_position')}%")
    elif service == "set_percentage":
        effects.append(f"풍속 {data.get('percentage')}%")
    elif service == "set_preset_mode":
        effects.append(f"모드 '{data.get('preset_mode')}'")
    elif service == "set_humidity":
        effects.append(f"습도 {data.get('humidity')}%")
    elif service == "volume_set":
        effects.append(f"볼륨 {int(data.get('volume_level', 0) * 100)}%")
    elif service == "volume_mute":
        effects.append("음소거" if data.get("is_volume_muted") else "음소거 해제")
    elif service == "select_source":
        effects.append(f"입력 소스 '{data.get('source')}'")
    elif service == "select_sound_mode":
        effects.append(f"사운드 모드 '{data.get('sound_mode')}'")
    elif service == "trigger":
        effects.append("자동화 실행(조건 검사 포함)")
    elif service == "increment":
        effects.append("+1 증가")
    elif service == "decrement":
        effects.append("-1 감소")
    elif service == "reset":
        effects.append("초기화(리셋)")
    elif service == "set_value":
        effects.append(f"수치/값 '{data.get('value')}' 설정")
    elif service == "select_option":
        effects.append(f"옵션 '{data.get('option')}' 선택")
    elif service in {"send_message", "speak"}:
        if action.get("secondary"):
            effects.append(
                f"안내 메시지 '{data.get('message')}' → 출력 '{action['secondary'].get('name')}'"
            )
        else:
            effects.append(f"안내 메시지 '{data.get('message')}'")

    elif service == "set_direction":
        effects.append(f"회전 방향 '{data.get('direction')}'")
    elif service.startswith("select_") and service in {
        "select_first",
        "select_next",
        "select_previous",
        "select_last",
    }:
        step_names = {
            "select_first": "첫 번째",
            "select_next": "다음",
            "select_previous": "이전",
            "select_last": "마지막",
        }
        effects.append(f"{step_names.get(service, '')} 옵션 선택")
    elif service == "get_events":
        rng = " / ".join(
            x[:16] for x in (data.get("start_date_time"), data.get("end_date_time")) if x
        )
        effects.append(f"일정 목록 조회 ({rng})" if rng else "일정 목록 조회")
    elif service == "create_event":
        start = data.get("start_date_time") or data.get("start_date") or ""
        end = data.get("end_date") or (f"+{data.get('duration')}" if data.get("duration") else "")
        when = str(start)[:16] if start else ""
        effects.append(f"일정 생성 '{data.get('summary')}' ({when}{end and ' ~' + str(end)})")
    elif service == "get_items":
        effects.append("할 일 목록 조회")
    elif service == "add_item":
        effects.append(f"할 일 추가 '{data.get('item')}'")
    elif service == "update_item":
        status_name = {"completed": "완료", "needs_action": "미완료"}.get(str(data.get("status")))
        label = f"할 일 {status_name} 처리 '{data.get('item')}'" if status_name else "할 일 수정"
        effects.append(label)
    elif service == "remove_item":
        effects.append(f"할 일 삭제 '{data.get('item')}'")
    elif service == "get_forecasts":
        ftype = FORECAST_LABELS.get(str(data.get("type")), "기상")
        effects.append(f"{ftype} 예보 조회")
    elif service == "set_datetime":
        value = data.get("datetime") or data.get("date") or data.get("time")
        effects.append(f"날짜/시간 '{value}' 설정" if value else "날짜/시간 설정")
    elif service in {"enable_motion_detection", "disable_motion_detection"}:
        effects.append(
            "모션 감지 켜기" if service == "enable_motion_detection" else "모션 감지 끄기"
        )

    if "effect" in data:
        effects.append(f"효과 '{data['effect']}'")
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
    return "; ".join(effects) or service
