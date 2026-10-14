# FIX_05_REPORT — FIX_05 보정 구현 및 실기동 검증 보고서

작성일: 2026-10-14 · 역할: Executor · 판정: **보정 구현 완료, 실기동 계약 검증 완료, 모델 라우팅 튜닝은 남은 리스크로 기록**

기준: `FIX_05.md`(Reviewer, dev `5bc123f` 이후 작업 트리). 기존 문서와 이전 보고서는 변경하지 않고 이 파일만 새로 작성했다.

---

## 1. 실행 요약

- `uv run pytest -q`: **101 passed**(기존 86 → FIX_05 회귀 15개 추가), Starlette deprecation warning 1개(기존과 동일).
- `uv run ruff check addon/app tests scripts`: 통과. `uv run ruff format --check`: 20 files 통과.
- `node --check addon/app/fhc/static/app.js`: 통과. `git diff --check`: 통과.
- **실기동**: 프로젝트 전용 QEMU HAOS(Core 2026.10.1 / Asia·UTC 테스트 VM)을 `test-resources.json`의 유지 argv로 기동 → 저장 HA 토큰이 401이라 기존 refresh_token으로 재발급(키·토큰 미출력) → `scripts/verify_fix05_live.py`로 실제 Engine + 실제 Microsoft Decision-1 / TypeSafe Jev 1.13 비교 실행 → **backend 계약 8/8 통과(양쪽 모델)**, 모델 왕복 roundtrip은 Microsoft 4/8, Jev 1/8. 종료 후 ACPI 정상 종료(VM stopped, 디스크·baseline 보존, 운영 VM/호스트 방화벽 미변경).
- 버전: **0.2.0-dev.8**로 `__init__.py`/`addon/config.yaml`/`Dockerfile`/`pyproject.toml`/UI footer/CHANGELOG 통일. dev.7보다 높음.

## 2. 항목별 보정

### R1 [P1] password 상태 노출
- **계약**: password 모드 `input_text`는 이번 범위에서 조회/제어/모델 입력/내보내기 **전부 제외**. `catalog.py`가 features의 실제 `mode` 속성으로 판정해 엔티티를 Catalog에서 구성하지 않는다 → scope/action 질문·`details` 원문 상태·조건 대상·plan·preflight·export에 구조적으로 등장 불가.
- 방어층: `make_actions` query 조기 경로에서 mode 재확인(`sensitive_input_protected`), `validate_fresh`가 **fresh state의 attributes.mode**로 디스패치 직전까지 차단(query/response 포함). ID 문자열 substring 검사(`password/pin/token/secret`)는 export에서 제거하고 기록 시점 분류(`query_results[].sensitive`)+현재 엔티티 mode 판정으로 대체.
- 과거 이력: 분류가 없거나 엔티티가 삭제된 레거시는 raw(include_text) 다운로드에서도 `[UNCLASSIFIED_STATE_EXCLUDED]`로 보수 제외. 알려진 API 키/환경 토큰 원문 치환은 추가 방어로 유지.
- 회귀 테스트: `test_fix05_r1_password_never_reaches_model_or_query`(모델 입력 JSON 전 구간 marker 부재 + 조작 액션 backend 차단), `test_fix05_r1_export_legacy_unclassified_history_conservative`(mode 기반 redact·삭제 엔티티 보수 제외), `test_fix05_r1_read_denied_query_blocked_candidate_and_backend`, `test_fix05_r1_password…` 모드 fixture 일반 이름/renamed ID 시나리오 포함, 기존 `test_r5` password部分是 "카탈로그 완전 제외"로 갱신.

### R2 [P1] read 정책 우회/유실
- `PolicyDict`에 `PERSONAL_READ_DOMAINS`(person/device_tracker/zone/calendar/todo)를 Separate opt-in으로 강등 — 기본 read True 집합에서 제거, 업데이트로 기존 설치 허용 범위를 자동 확장하지 않음. `as_policy_dict`으로 Catalog의 dict/PolicyDict 이중 경로를 폐지하고 read/write를 한 계약으로 검사.
- 후보: `options_for`는 `read_allowed`일 때만 query 제공. read-only(쓰기 거부) 엔티티도 calendar `get_events`/todo `get_items`/weather `get_forecasts` **실제 응답 조회는 read 권한으로 제공**(write_allowed=False에서 query_state만 주던 결함 제거). 응답성 조회는 action에 `access="read"`로 분류.
- backend: `validate_fresh(entity, action, state, services, policy, identity)`가 access 종류별 정책을 preflight에서 재검증 → `read_policy_denied`/`control_policy_denied`. engine preflight가 registry identity로 전 액션 검사.
- 저장/보존: `set_policy` 생략 섹션 자동 보존(read_domains), `_validate_policy`가 read_domains 타입·entities 알 수 없는 키·enabled/read_enabled/revision 타입을 거부(`invalid_policy`). `set_entity_policy`는 read_enabled/identity 보존, `reconcile_registry` rename/swap/cycle에서 read_enabled 보존 및 병합 시 AND(보수). API `Policy`에 `read_domains`/`EntityOverride.read_enabled` 추가, `extra="forbid"` + 부분 병합으로 무관 저장 시 소실 방지. 관리자 UI에 도메인/엔티티별 **제어/조회 독립 토글** 추가(app.js, style).
- `/api/domains`: read/write 가능·허용 수 독립 집계(queryable_count는 제어 가능 여부와 무관한 capability 수, allowed_query_count는 read 허용 수, entity.queryable과 모순 제거), 도메인별 `read_enabled` 노출.
- 회귀/신규: `test_fix05_r2_read_denied_engine_never_executes_query`(scen.1), `test_fix05_r2_partial_policy_writes_preserve_read_settings`(scen.2/3), `test_fix05_r2_personal_domains_require_explicit_optin`(scen.4), `test_fix05_r2_policy_api_roundtrip`(API 부분 저장·잘못 타입 422), `test_fix05_r2_readonly_calendar_get_events_end_to_end`, f3 counts 갱신.

### R3 [P1] TTS 출력 대상 추측
- `media_player_entity_id or "media_player.living_room"` 고정 fallback **삭제**. tts target의 `tts_output` 질문은 명령 스코프에서 발견·write 허용된 media_player ref만 후보로 제시하고, 백엔드가 선택 ref의 정책·존재·availability(unknown 허용)를 preflight에서 검증 후 출력 이름을 효과/진단(secondary)에 기록. 누락/모호/제외/사용 불가면 전송 0건(`tts_output_target_required`/`output_policy_denied`/`output_entity_unavailable`).
- 테스트: `test_fix05_r3_tts_requires_discovered_output_target` — 별칭 다른 거실/침실 ID에서 정확한 출력 선택 payload, 모호 시 0건, write 제외 출력 옵션 비노출+조작 선택 거부, unavailable 출력 preflight 차단, `media_player.living_room` 문자열 부재 단정. 실기동: `R3_tts_target`/`R3_tts_ambiguous` 계약 통과(영어 friendly name 스피커에서 Decision-1이 ref 선택까지 가지 못한 것은 아래 잔여 리스크로 기록; 기본 fallback 전송은 어떤 모델에서도 0건 관찰).

### R4 [P2] C 단계 실제 매개변수
- `temporal_tokens()`가 원문에서 시각(`HH:MM`, `N시`)와 날짜 어휘(오늘/내일/모레)를 span付き typed 토큰으로 분리하고 HA `time_zone`(ha.py에서 보존) 기준 absolute 날짜로 결합.
- `input_datetime.set_datetime`: has_date/has_time flags와 토큰 교차 검증 → `{"time": "HH:MM:00"}` / `{"date": "YYYY-MM-DD"}`. 빈 payload 금지(`datetime_value_required`/`datetime_value_invalid`).
- `calendar.get_events`: `calendar_range`(오늘/내일/7일) 모델 선택으로 `start_date_time`/`end_date_time` 생성(미지정 시 `calendar_range_required`). `create_event`: 날짜 필수(+시작 시각 토큰이면 `start_date_time`+`duration`, 아니면 start_date/end_date).
- `weather.get_forecasts`: supported_features에서 발견한 forecast 유형만 후보 제시, 미지원 유형 거부(`forecast_type_unsupported`), 고정 daily 폐지(`forecast_type_required`).
- `todo.update_item`: `todo_status`(completed/needs_action) 명시 필수 — 수정=완료 강제 치환 폐지. 디스패치 전 백엔드가 `get_items` 실목록 조회 → summary/UID 정확 일치 단일 후보만 UID로 치환(`todo_item_resolution` 기록), 0건이면 `todo_item_not_found`, 동명/다UID면 `todo_item_ambiguous`로 전송 0건. `remove_item`도 동일.
- 응답성 조회도 validate_fresh(가용성·서비스 존속·read 정책) 대상. 사용자 결과 한 줄은 raw JSON 대신 `format_response()`의 요청 범위 요약(일정 N개/예보 요약 등). calendar/todo/weather/camera choices는 실제 발견 서비스 집합으로 제한.
- **실기동에서 추가 결함 발견·수정**: Supervisor WS 응답이 `{"response": {entity_id: payload}}`로 중첩되는 실제 스키마를 engine이 entity-id 키까지 내려가 unwrap하도록 수정(`_unwrap_response`) — 중첩 미처리 시 todo가 항상 not_found 되는 결함을 단위(FakeHA를 실제 중첩 형태로 갱신)와 실기동에서 동시 회귀 처리.
- 테스트: `test_fix05_r4_calendar_create_and_weather_forecast_typed`, `test_fix05_r4_todo_uid_resolution_and_explicit_status`(고유/동명/부재), `test_fix05_r4_response_query_not_exempt_from_validation`, `test_fix05_r2_readonly_calendar_get_events_end_to_end`(start/end·가독 응답 표시), `test_fix04_r5` datetime 부분 실제 payload 단정으로 강화.

### R5 [P1] 조건 = 모델 선택 typed 계약
- `COND_INDICATOR/COND_PATTERN` 로컬 의미 판정 **전면 제거**(regex는 literal/span 추출에만 유지). scope 라운드에 `conditional` noul 추가(≥0.7), 조건부 명령은 action 라운드에서 `condition_source`(read 허용 sensor/binary_sensor ref 중 선택)/`condition_operator`(gt·gte·lt·lte)/`condition_value`(literal ID)/`condition_unit`을 모델이 선택하고 백엔드가 계산. typed condition은 최종 `exact` 검증 상태에도 포함.
- 경계: `gt`는 strict `(>`), `gte`만 `>=` — `28도를 넘으면`을 >=로 처리하던 결함 및 parse 실패 해소. 부정(`아니면/말고`)·복합(`이고/거나`)·기준 없음은 선택 자체가 none → `condition_evaluation_failed` 전송 0건(임의 센서 대체 없음). 센서 단위 매핑 불가(K/lux)·unknown/unavailable 상태도 fail-closed. 조건 false는 dispatch 0건 유지.
- `장면/벽면/화면` 포함 정상 이름은 conditional noul이 낮으면 조건 라운드 자체가 없어 정상 실행.
- 테스트: `test_fix04_r1`을 typed 계약으로 재작성(gt/gte 경계, `28도를 넘으면` strict, qualitative/negation/compound/untranslatable-unit, `거실 장면 실행해줘`·`벽면 조명 꺼줘` 정상 실행), `test_c_domain_query_and_condition_evaluation`·`test_r1_condition_guard_and_unit_conversion`(°F↔°C 유지)도 model_typed 경로를 `selection: "model_typed"`로 단정. **실기동**: 밖에 온도 15.6°C에서 `밖에 온도가 20도 이상이면 거실 불 꺼줘` → model_typed/False/condition_not_met/**전송 0건**(Decision-1 왕복 성공, Jev는 unsupported 거부로 0건).

### R6 [P2] 진단 익명화·검증 범위
- export `decisions.choice`: 공식 enum/action ID 화이트리스트(`SAFE_CHOICES`)와 literal ID(`^[vtd]\d+$`)만 통과, 사용자 생성 option/이름 문자열은 기본 익명화에서 `anon_choice_N`(가역 매핑)으로 치환, raw(include_text)는 관리자 명시 모드. 합성 `PRIVATE_ENUM_NAME`이 기본 다운로드에 남던 결함 차단.
- provider trace: 실패/성공 전부 `elapsed_ms`·`questions` 수 추가(원문 prompt/body는 저장하지 않음), 단계 timings·model_calls 유지.
- 하네스(`scripts/evaluate_stage_a.py`): reset 예외 `pass` 제거 → 실패는 `setup_failed`로 분리 기록하고 fresh read-back으로 seed 확인, 상대 밝기는 `expected={}` 대신 시드 200/255 기준 `174±13` 실변화량 assert(tuple tolerance), A 코퍼스에 조건/기상 예보/일정/todo/TTS 왕복·거부 B/C 코퍼스와 fixture 엔티티 부재 시 skip(조작 pass 금지) 추가.
- 실기동 증거 구분: `.local/fix05-bc-live.json`(Microsoft)·`.local/fix05-bc-live-jev.json`(Jev) — contract/roundtrip 2단계 기록, 키·토큰 미포함.

## 3. 실기동 결과 (프로젝트 전용 VM, 단위 테스트와 구분)

| 케이스 | Decision-1 계약/왕복 | Jev 계약/왕복 |
| --- | --- | --- |
| R5 조건 false(0 전송) | PASS / PASS | PASS / FAIL(unsupported 거부, 0 전송) |
| R3 TTS 출력 지정 | PASS / FAIL(low_confidence) | PASS / FAIL |
| R3 TTS 모호 → 0건 | PASS / PASS | PASS / PASS |
| R4 기상 예보 | PASS / FAIL(low_confidence, south/north 모호) | PASS / FAIL |
| R4 내일 일정 | PASS / FAIL(low_confidence, calendar_1/2 모호) | PASS / FAIL |
| R4 todo 추가(값 실전송) | PASS / PASS | PASS / FAIL |
| R4 todo 완료(UID 조회) | PASS / PASS | PASS / FAIL |
| B climate 값(회귀) | PASS / FAIL(plan_not_verified) | PASS / FAIL |

- 어느 모델에서도 password 노출·고정 스피커 fallback·조건부 오실행·빈 payload 전송은 관찰되지 않음(계약 8/8). 실패 사유는 모두 안전 측 거부(low_confidence/plan_not_verified/unsupported)로, 임의 대실행 0건.
- VM은 UTC/time_zone 노출, demo south/north 2중 엔티티 등 **중복 대상 모호성**이 왕복 실패의 주원인. threshold 완화로 통과를 조작하지 않고 그대로 기록(Reviewer 지시: 잘못된 실행·거부·성공 분리).

## 4. FIX_02 B/C 표 대비 상태

- B(제어): vacuum/button/fan/cover/humidifier/media_player/input_boolean/number/select/counter/script/automation/scene 및 light/climate 회귀 — 전 항목 구현·단위 유지(FIX_03/04 이어). camera는 발견 서비스만 노출.
- C(조회/응답): sensor/binary_sensor 조회, weather 상태+지원 예보, calendar get_events/명시 생성(시간대·구간·start/end), todo 목록/추가/실제 UID 대상 상태 변경·삭제, 조건 model_typed — 구현 및 계약 실기동 확인. input_datetime set은 live fixture에 helper가 없어 **단위 검증까지만**(value payload·flag 차단 확인), live 값 변경 증거는 helper 추가 시 재수행 필요.
- 제외 유지: notify 그룹·임의 URL·script 생성·scene apply 등(기존 범위), tts engine별 수동 매핑 없음(없으면 거부).

## 5. 남은 리스크 / blocker

1. **모델 라우팅·검증 튜닝**(R3 TTS ref 선택, R4 south/north·calendar_1/2 저신뢰, R5 조건부 verify 거부): backend 계약은 실기동 검증됐고 실패는 전부 0전송 거부. 왕복률 개선은 프로ンプ트/후보 제시(tts_output별 alias, 조건 verify 문구) 튜닝 라운드로 분리 권장. 운영 기본 모델 교체는 하지 않았다.
2. VM demo fixture에 `input_datetime` helper 부재 → 해당 live 항목은 미검증(단위로만 확인). fixture는 다음 재기동 시 helper 추가 권장(사용자 설치와 무관).
3. HA가 `time_zone`을 노출하는 way 변경 대비: 현재 `get_config.time_zone` 없으면 UTC로 보수 동작.
4. dev.8 미설치 상태: 이번 live 검증은 호스트 Engine→VM HA 경로(addon 재빌드 아님). addon 실제 설치/dev.8 승격 검증은 릴리스 절차(docs/releases.md)에서 별도로 수행 필요.

## 6. 최종 상태

- 변경 파일: `addon/app/fhc/{actions,catalog,engine,ha,main,provider,store}.py`, `addon/app/fhc/static/{app.js,index.html,style.css}`, `addon/{config.yaml,CHANGELOG.md,Dockerfile}`, `addon/app/fhc/__init__.py`, `pyproject.toml`, `uv.lock`, `tests/{conftest,test_corrections}.py`, `scripts/evaluate_stage_a.py`, 신규 `scripts/verify_fix05_live.py`. 커밋하지 않았다(작업 트리 유지).
- `.local/` 증거(`fix05-bc-live.json`, `fix05-bc-live-jev.json`)와 갱신된 토큰은 Git 제외 디렉터리에만 존재하며 원문을 이 문서에 포함하지 않았다.
- 리소스: 프로젝트 전용 테스트 VM ACPI 정상 종료(stopped), baseline 디스크·OVMF_VARS 보존, 임시 스토어는 tempfile로 자동 정리, 운영 VM·방화벽·타 컨테이너 미변경.
