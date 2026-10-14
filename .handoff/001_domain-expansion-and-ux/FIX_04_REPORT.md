# FIX_04_REPORT — FIX_04 보정 구현 및 검증 보고서

작성일: 2026-10-13 · 역할: Executor · 판정: **보정 완료 및 검증 통과**

---

## 1. 개요 및 실행 요약

Reviewer의 `FIX_04.md` 지적 사항(R1~R5)에 대해 백엔드 안전 검증 계약 강화, 제어 도메인 상태 조회 및 읽기/쓰기 정책 분리, 복수 속성 및 단위/step/멱등성 보정, 메시지 추출 및 진단 내역 민감 데이터 보호, B/C 도메인 완료 및 테스트 하네스 검증을 완료했다.

- **테스트 결과**: `uv run pytest -q` 기준 **86 passed, 1 warning** (Starlette deprecation warning).
- **정적 분석**: `uv run ruff check addon/app tests scripts` 통과 (All checks passed).
- **코드 포맷팅**: `uv run ruff format --check addon/app tests scripts` 통과 (19 files already formatted).
- **프론트엔드 구문 검사**: `node --check addon/app/fhc/static/app.js` 통과.
- **Git diff 무결성**: `git diff --check` 통과.

---

## 2. 항목별 보정 상세

### R1 [P1] 정규식 조건 감지 및 미지원 조건 안전 거부 (Fail-closed)
- **위치**: [`addon/app/fhc/engine.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/engine.py#L33-L176)
- **보정 내용**:
  1. **조건 식별자 및 일상 표현 구분**: `COND_INDICATOR`에서 단순 `때`를 `(?:[을ㄹ]\s*때|[은는한]\s*때)`로 정밀화하여 `청소기 상태 어때` 등 비조건 상태 질문이 조건 파서에 오작동하지 않도록 분리했다.
  2. **미지원 복합/부정/정성 조건 Fail-closed**:
     - 부정 표현(`아니면`, `않으면`, `않다면`, `아니라면`, `말고`, `대신`) 포함 시 `condition_evaluation_failed`로 즉시 거부(`status: "rejected"`, HA 전송 0건).
     - 복합 조건(`이고`, `면서`, `및`, `그리고 ...면`, `이거나`, `거나`, `또는`) 포함 시 `condition_evaluation_failed`로 즉시 거부 (HA 전송 0건).
     - 수치 기준이 없는 정성적 조건(예: `만약 거실 온도가 높다면`)은 조건 파싱 실패로 간주하여 HA 전송 0건으로 안전 거부.
  3. **비교 연산자 확충**: `보다 높다면` / `보다 높으면` (`>`), `보다 낮다면` / `보다 낮으면` (`<`) 연산자를 추가하여 단순 `이상/이하` 외의 비교 구문을 지원.
  4. **단위 검증 강화**: 지원 가능한 단위(`°C`, `°F`, `%`) 외에 지원하지 않는 단위(`K` 등)는 변환/가정을 배제하고 `condition_evaluation_failed`로 거부.
  5. **Fresh HA State 실행 직전 재확인**: 실행 직전에 `ha.fresh_state(entity_id)`를 호출하여 신선한 센서 상태 값을 기준으로 비교하고 진단 DTO에 `raw_value`, `observed_value`, `observed_unit`, `target_value`, `target_unit`, `operator`, `result`를 보존.

### R2 [P2] 제어 도메인 상태 조회 및 읽기/쓰기 허용 정책 분리
- **위치**: [`addon/app/fhc/actions.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L535-L539), [`addon/app/fhc/catalog.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/catalog.py#L135-L188), [`addon/app/fhc/store.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/store.py#L20-L46), [`addon/app/fhc/main.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/main.py#L260-L275)
- **보정 내용**:
  1. **무조건적 Query 선택지 제공**: `options_for`에서 텍스트 정규식 조건 검사 없이, 권한이 있는 모든 엔티티에 대해 `props["query"] = {"none": "...", "query_state": "..."}`를 기본 제공하여 모델이 상황에 맞게 조회/제어를 선택하도록 보장.
  2. **읽기(read/query) 및 쓰기(write/control) 정책 분리**:
     - `PolicyDict.is_domain_allowed` 및 `is_allowed`에서 `access="read"`와 `access="write"`를 분리 평가.
     - 도메인/엔티티 마스터 정책이 비활성화된 경우, 별도 `read_domains` 명시가 없는 한 읽기 권한도 차단(마스터 우회 방지).
     - `read_domains: {"vacuum": True}`, `domains: {"vacuum": False}`와 같은 읽기 전용 정책 환경에서:
       - `Catalog`의 `Entity`에 `write_allowed=False`, `read_allowed=True` 플래그 설정.
       - `options_for`에서 쓰기 제어 선택지를 제거하고 오직 `query` 선택지만 제공하여 조회 성공 / 물리 제어 원천 차단.
  3. **API 카운트 정확도 개선**: `/api/domains`에서 `controllable_count`는 실제 제어 서비스와 `write_allowed` 권한이 있는 엔티티로 계산하고, `queryable_count`는 비제어/순수 조회 또는 읽기 전용 엔티티로 구분하여 정확히 집계.

### R3 [P1] 기능 플래그, 수치 step 검증, 복수 속성 및 멱등성 처리
- **위치**: [`addon/app/fhc/actions.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L220-L390), [`:600-960`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L600-L960), [`:1000-1030`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L1000-L1030)
- **보정 내용**:
  1. **비트마스크 엄격 적용**: `cover` 및 `media_player`에서 `or flags == 0` 폴백을 제거하고 공식 비트마스크 플래그를 충족해야 해당 동작 choices를 제공.
  2. **수치 Step 사전/사후 검증**: `number` / `input_number` 제어 시 `(val - lo) % step` 정합성을 검증하여 허용 step과 불일치할 경우 조용히 절삭하지 않고 `DecisionError("number_step_invalid")`로 거부.
  3. **복수 속성 복합 액션 구성**:
     - `make_actions`를 도입하여 단일 엔티티에 복수 제어가 들어오는 경우(선풍기 풍속+회전, 가습기 습도+모드, 미디어 재생+볼륨 등) 단일 elif 절삭을 제거하고 검증된 복수 action 리스트를 반환하여 누락 없이 HA에 순차 디스패치.
  4. **비멱등 효과 No-op 예외**: `script.turn_on`은 현재 스크립트 상태가 `"on"`이어도 restart/queued 모드 등 재실행 시맨틱을 보장하기 위해 `is_already_in_state`에서 no-op 스킵되지 않도록 수정.

### R4 [P2] 메시지 본문 추출 정밀화, TTS 타겟 바인딩, 진단 내역 민감 데이터 보호
- **위치**: [`addon/app/fhc/actions.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L560-L600), [`:885-895`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L885-L895), [`addon/app/fhc/main.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/main.py#L570-L665), [`addon/app/fhc/provider.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/provider.py#L130-L155)
- **보정 내용**:
  1. **메시지 본문 클린 추출**:
     - `extract_message`에서 엔티티/조사 프리픽스(`입력란에`, `거실 알림에`, `거실 스피커로`)를 정확히 분리하여 본문만 추출.
     - 본문 span이 없거나 해석 불가한 명령은 전체 문장 fallback을 금지하고 `DecisionError("invalid_message_span")`로 거부.
  2. **TTS 타겟 바인딩**: `tts.speak` 호출 시 `media_player_entity_id`를 필수 인자로 바인딩.
  3. **진단 내역 안전 DTO 및 비밀 보호**:
     - `/api/history/export`에서 `condition_evaluation`, `decisions`, `model_trace` DTO를 안전한 타입 구조로 포함.
     - `include_text=True`로 요청하더라도 PIN/password 모드 `input_text`의 상태값은 `[REDACTED_SENSITIVE]`로 마스킹.
     - `Provider.trace`에 실패한 호출의 `error`, `http_code`를 보존.

### R5 [P2] B/C 도메인 완료 및 서비스 보강
- **위치**: [`addon/app/fhc/actions.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L270-L535), [`:710-955`](file:///home/lee/projects/fast-home-control/addon/app/fhc/actions.py#L710-L955), [`addon/app/fhc/engine.py`](file:///home/lee/projects/fast-home-control/addon/app/fhc/engine.py#L440-L460)
- **보정 내용**:
  1. **누락 서비스 choices 및 액션 연결**:
     - `vacuum`: `fan_speed` (`set_fan_speed`)
     - `fan`: `direction` (`set_direction`)
     - `select`: `select_step` (`next`, `previous`, `first`, `last`)
     - `counter`: `counter_value` (`set_value`)
     - `light`: `effect`
     - `climate`: `fan_mode`, `preset_mode`, `swing_mode`
     - `input_datetime`: `set_datetime`
     - `camera`: `turn_on`, `turn_off`, `enable_motion_detection`, `disable_motion_detection`
  2. **응답 데이터 반환 서비스 연결**:
     - `calendar.get_events`, `todo.get_items`, `weather.get_forecasts` 호출 시 `return_response=True`를 전달하고, HA 응답 데이터를 읽어 `query_results`에 반환.

---

## 3. 검증 증거

### 단위 및 회귀 테스트 (`tests/test_corrections.py`)
총 86개 테스트 전체 통과:
```
tests/test_corrections.py:
  test_fix04_r1_condition_guard_and_rejections ............ PASSED
    - '거실 온도가 28도보다 높다면 거실불 꺼줘' (29°C > 28°C) -> 성공 (turn_off 1건)
    - '거실 온도가 28도보다 높다면 거실불 꺼줘' (27°C) -> condition_not_met (0건)
    - '만약 거실 온도가 높다면 거실불 꺼줘' (기준치 미제시) -> rejected (0건)
    - '거실 온도가 28도 이상이 아니면 거실불 꺼줘' (부정 조건) -> rejected (0건)
    - '거실 온도가 28도 이상이고 습도가 70% 이상이면 거실불 꺼줘' (복합 조건) -> rejected (0건)
    - 센서 unit='K' -> rejected (0건)
  test_fix04_r2_controllable_domain_query_and_policy_separation .... PASSED
    - '청소기 상태 어때' -> vacuum query_state 성공, 물리 서비스 0건
    - 읽기 전용 정책 (vacuum write=False, read=True) -> query_state 성공, 제어 옵션 제거
  test_fix04_r3_multi_attributes_and_step_and_script_restart ....... PASSED
    - 선풍기 50% + 회전 -> set_percentage + oscillate 2건 액션 생성
    - input_number step=2에서 값 3 -> number_step_invalid 거부, 값 4 -> 4.0 전송
    - 스크립트 on 상태에서 script.turn_on -> no-op 스킵 방지 (정상 실행)
  test_fix04_r4_message_extraction_and_diagnostics_export .......... PASSED
    - '입력란에 오늘 저녁 7시 회의라고 입력해줘' -> '오늘 저녁 7시 회의'
    - '거실 알림에 안녕 보내줘' -> '안녕'
    - '그냥 켜줘' -> invalid_message_span 예외 발생
    - /api/history/export -> condition_evaluation, decisions, model_trace 포함 및 PIN 마스킹
  test_fix04_r5_bc_services_and_domain_counts ...................... PASSED
    - vacuum fan_speed 옵션 및 set_fan_speed 전송
    - select select_step 옵션 및 select_next 전송
    - input_datetime datetime_action 옵션 및 set_datetime 전송
```

### 정적 분석 및 린트
```bash
$ uv run ruff check addon/app tests scripts
All checks passed!

$ uv run ruff format --check addon/app tests scripts
19 files already formatted

$ node --check addon/app/fhc/static/app.js
(정상 종료 - exit code 0)

$ git diff --check
(정상 종료 - whitespace/conflict marker 없음)
```

---

## 4. 작업 트리 및 자원 상태

- **Git 상태**: `dev` 브랜치, 작업 트리 내 파일 정상 수정 및 포맷팅 완료.
- **HAOS VM**: `.local/test-resources.json`에 기록된 대로 `stopped` 상태 유지 (임의 기동이나 잔여 프로세스 없음).
- **보고서 보존**: 기존 `PLAN.md`, `REPORT.md`, `FIX_01~03` 및 `FIX_01_REPORT~FIX_03_REPORT` 덮어쓰지 않고 보존.
