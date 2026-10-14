# FIX_03_REPORT — B/C 결함 보정 및 Microsoft Decision-1 / TypeSafe Jev-1.13 비교 검증 보고서

작성일: 2026-10-13 · 역할: Executor · 판정: **FIX_03 모든 요구사항 보정 완료 및 라이브 HAOS VM 실기동 검증 통과**

---

## 1. 개요 및 변경 내역

Reviewer가 제시한 `FIX_03.md`의 R1~R7 결함 사항 및 제9절 신규 지시(TypeSafe Jev 1.13 비교 검증)를 반영하여 Fast Home Control v0.2.0-dev.7 보정 작업을 완료하고 격리된 HAOS VM 및 OpenRouter API를 통해 실기동 검증을 완수했습니다.

### 주요 수정 파일 및 커밋 준비 목록
1. `addon/app/fhc/engine.py`:
   - R1: 조건문 지시어(`COND_INDICATOR`, `COND_PATTERN`) 감지 및 typed 센서 매칭 로직 구현.
   - R1: 센서 부재, unknown, unavailable, 복수 동명 모호성 발생 시 fail-closed (`DecisionError("condition_evaluation_failed")`, HA 디스패치 0건 거부).
   - R1: °F / °C 상호 단위 변환 및 유한수/NaN 검증. 조건 불충족 시 `reason="condition_not_met"`, 디스패치 0건 처리.
   - R1: 검증 진단 데이터(`condition_evaluation`) 기록.
2. `addon/app/fhc/actions.py`:
   - R4: `automation.trigger` 호출 시 `skip_condition: False` 서버 고정, `automation.turn_off` 시 `stop_actions: True` 고정. `is_already_in_state`에서 automation turn_off가 no-op 처리되지 않도록 예외 처리.
   - R5: `CONTROL_DOMAINS`와 `QUERY_DOMAINS` 명시적 분리. `camera` 및 `input_datetime`은 제어 대상에서 제외(0건 제어).
   - R5: `fan` (speed=1, oscillate=2, preset=8), `cover` (position=4, tilt=128), `media_player` (volume=4, mute=8 등), `humidifier`에 대한 비트와이즈 `supported_features` 검증.
   - R5: `cover`의 `garage`, `gate` device_class 기본 보호 (`sensitive_cover_protected`).
   - R5: password-mode `input_text` 제어 거부 (`sensitive_input_protected`).
   - R6: 상충 액션(예: `turn_off`와 속도/볼륨/습도 동시 요청) 감지 시 `DecisionError("conflicting_actions")`로 전송 0건 거부.
   - R6: `extract_message()`를 통해 음성 지시어에서 실제 텍스트 span만 안전 추출.
   - R6: `select` 도메인의 `options[:20]` 임의 절단 제거 (전체 enum 보존).
3. `addon/app/fhc/main.py`:
   - R2: `Options.openrouter_api_key` 및 `azure_api_key`의 `SecretStr` 객체에서 `.get_secret_value()`를 안전하게 호출하여 `TypeError` 해결.
   - R3: 단순 denylist 대신 엄격한 `_build_diagnostic_record` DTO allowlist 적용. 엔티티 ID 및 영역명 가명화(`target_0`, `area_0`), 비밀 마커/원문 배제.
   - R3: SQL 쿼리 시 LIMIT 전 단계 필터링, 정수 범위 검증, 정확한 제외/절단 카운트 산출.
   - R5: `/api/domains`에서 제어 가능 엔티티 수와 조회 가능 엔티티 수를 정확히 분리.
4. `addon/app/fhc/store.py`:
   - R6: `recent_shortcuts`에서 단순 조회(query), 조건 미충족(`condition_not_met`), 메시지/텍스트 전송 기록을 추천 대상에서 배제.
5. `addon/app/fhc/static/app.js`:
   - R6: `query_succeeded` 상태에 대해 실제 측정값 및 단위 표시, `condition_not_met` 시 명확한 한국어 안내 제공.
   - R6: 신규 에러 코드(`condition_evaluation_failed`, `sensitive_cover_protected`, `sensitive_input_protected`, `conflicting_actions`) UI 메시지 추가.
6. `scripts/evaluate_stage_a.py`:
   - 제9절: `--model` CLI 인자 지원 (`microsoft/microsoft-decision-1` 및 `typesafe/jev-1.13` 허용).
   - 제9절: 케이스 실행 전 HA 상태를 초기화하는 `reset_ha_case()` 도입 (no-op 결과/지연 왜곡 방지).
   - 제9절: 모델별 독립 결과 파일(`.local/stage-a-evaluation-{model}.json`) 및 요약 통계 출력.

---

## 2. 결함별 검증 증거

### R1 [P1] 조건 해석 Guard 및 Fail-Closed
- **검증 항목**:
  1. 센서가 없는 카탈로그에서 `거실 온도가 28도 이상이면 거실불 꺼줘` 실행 시 `condition_evaluation_failed` 발생 확인 (HA 디스패치 0건).
  2. 센서 상태가 `unknown` 또는 `unavailable`인 경우 `condition_evaluation_failed` 발생 확인 (디스패치 0건).
  3. 센서가 70°F(약 21.1°C)일 때 `28도 이상` 조건 실행 시 `condition_not_met` 반환 및 조명 전송 0건 확인.
  4. 센서가 85°F(약 29.4°C)일 때 `28도 이상` 조건 실행 시 `condition_result=True` 판정 및 정상 실행 확인.
  5. `28℃` 심볼 지원 확인.
- **테스트**: `tests/test_corrections.py`의 `test_r1_condition_*` 시리즈 통과.

### R2 [P1] SecretStr TypeError 해결
- **검증 항목**:
  - `Options`에 실제 `SecretStr` 형태의 OpenRouter/Azure API 키가 설정된 상태에서 `/api/history/export` 호출.
  - `TypeError: 'in <string>' requires string as left operand, not SecretStr` 오류가 완전히 해소되고 유효한 ZIP 파일(내부 `manifest.json`, `summary.json`, `requests.jsonl`)이 다운로드됨을 확인.
- **테스트**: 단위 테스트 `test_export_history_with_live_secret_str` 및 라이브 Ingress HTTP 호출 검증 완료.

### R3 [P1] 진단 DTO Allowlist 및 개인정보/비밀 마커 노출 방지
- **검증 항목**:
  - `previous_state`, `service_data.value`, `query_results.state`에 임의의 합성 마커(`PRIVATE_STATE_MARKER`, `PRIVATE_VALUE_MARKER`)를 주입한 저널 레코드 생성.
  - 기본 export 시 DTO allowlist에 의해 임의 값들이 필터링되고, 엔티티 ID가 `target_0`, 영역이 `area_0` 등으로 일관되게 가명화됨을 확인.
  - `requests.jsonl` 내에 마커가 일절 남지 않음을 검증.
- **테스트**: `test_r3_diagnostic_dto_allowlist` 통과.

### R4 [P1] automation.trigger skip_condition 및 automation.turn_off stop_actions
- **검증 항목**:
  - `automation.trigger` 생성 시 `service_data["skip_condition"] == False` 고정 확인.
  - `automation.turn_off` 생성 시 `service_data["stop_actions"] == True` 고정 확인.
  - `automation`이 이미 `off` 상태여도 `turn_off` 요청이 `already_in_state`로 조기 종료되지 않고 서비스 호출이 진행됨을 확인.
- **테스트**: `test_r4_automation_flags_and_turn_off` 통과.

### R5 [P1] 런타임 기능 및 피처 플래그 검증
- **검증 항목**:
  - `fan.supported_features = 0`인 팬에 대해 속도(`percentage`), 회전(`oscillate`), 프리셋(`preset_mode`) 요청 시 `service_not_supported` 거부 확인.
  - `cover.device_class`가 `garage` 또는 `gate`인 경우 `sensitive_cover_protected` 거부 확인.
  - `input_text.mode = "password"`인 경우 `sensitive_input_protected` 거부 확인.
  - `/api/domains` 엔드포인트에서 `camera` 및 `input_datetime`은 `query_only: true`, `controllable_count: 0`으로 올바르게 분리 집계됨을 확인.
- **테스트**: `test_r5_fan_capability_flags`, `test_r5_garage_cover_protected`, `test_r5_password_input_protected` 통과.

### R6 [P2] 상충 액션 거부, 메시지 경계 추출, 바로가기 필터링
- **검증 항목**:
  - 팬에 전원 끄기(`turn_off`)와 속도 설정(`percentage`)을 동시 요청 시 `conflicting_actions` 거부 확인.
  - `extract_message("입력란에 오늘 저녁 7시 회의라고 입력해줘")` -> `"오늘 저녁 7시 회의"` 추출 확인.
  - `Store.recent_shortcuts`에 단순 조회, 조건 미충족, 텍스트 입력 레코드가 수집되지 않음을 확인.
- **테스트**: `test_r6_conflicting_actions`, `test_r6_extract_message`, `test_r6_shortcuts_filtering` 통과.

---

## 3. 라이브 HAOS VM 실기동 검증 (v0.2.0-dev.7)

프로젝트 소유 localhost QEMU KVM 환경(port 18180)에서 애드온 v0.2.0-dev.7을 빌드 및 배포하여 실기동을 검증했습니다.

1. **애드온 빌드 및 상태 확인**:
   - `ha apps rebuild a1444ce0_fast_home_control_dev` 실행 완료.
   - `GET /api/status` 호출:
     ```json
     {
       "ok": true,
       "version": "0.2.0-dev.7",
       "provider": "openrouter",
       "ha_connected": true,
       "ha_ready": true,
       "devices_count": 47
     }
     ```
2. **도메인 메타데이터 확인**:
   - `GET /api/domains` 확인 결과:
     - `camera`: `supported: true`, `query_only: true`, `controllable_count: 0`, `queryable_count: 3`
     - `input_datetime`: `supported: true`, `query_only: true`, `controllable_count: 0`, `queryable_count: 0`
3. **이력 다운로드 검증**:
   - `GET /api/history/export?format=zip` 호출 시 200 OK로 바이너리 ZIP 스트림 반환 확인.
   - 내부 압축 해제 후 `manifest.json`, `summary.json`, `requests.jsonl`이 DTO 화이트리스트 스키마에 부합함을 검증.

---

## 4. 제9절: Microsoft Decision-1 vs TypeSafe Jev 1.13 비교 검증

동일한 HAOS 가상 기기 fixture 환경 및 동일한 15개 벤치마크 케이스에 대해, 매 케이스마다 `reset_ha_case()`로 상태를 초기화하여 두 모델을 공정하게 평가했습니다.

### 비교 결과 요약

| 지표 | Microsoft Decision-1 | TypeSafe Jev 1.13 | 비고 |
| :--- | :---: | :---: | :--- |
| **요청 모델** | `microsoft/microsoft-decision-1` | `typesafe/jev-1.13` | OpenRouter alpha decisions 엔드포인트 |
| **반환 모델** | `microsoft/microsoft-decision-1` | `typesafe/jev-1.13-20260917` | 공식 지정 버전 반환 확인 |
| **전체 통과율** | **14 / 15 (93.3%)** | **6 / 15 (40.0%)** | 안전 임계값 0.95 기준 |
| **유효 제어 케이스** | **9 / 10 (90.0%)** | **1 / 10 (10.0%)** | 에어컨, 조명 복합 제어 |
| **부정/거부 케이스** | **5 / 5 (100.0%)** | **5 / 5 (100.0%)** | 두 모델 모두 오동작 0건 완벽 거부 |
| **평균 총 지연시간** | **3,428.9 ms** | **2,029.0 ms** | Jev 1.13이 약 40.8% 빠름 |
| **평균 HTTP 호출 수** | 3.3 회 | 3.3 회 | 파이프라인 단계 수 동일 |

### 케이스별 세부 대조표

| 명령 텍스트 | 기대 동작 | Microsoft Decision-1 | TypeSafe Jev 1.13 | 비고 |
| :--- | :--- | :---: | :---: | :--- |
| `거실 에어컨 켜줘 송풍모드` | fan_only | PASS (verify: 0.991) | FAIL (verify: 0.830) | Jev 검증 점수 미달로 안전 거부 |
| `거실 에어컨 바람만 나오게 해줘` | fan_only | PASS (verify: 0.996) | PASS (verify: 0.950) | 두 모델 모두 성공 |
| `거실 에어컨 제습으로 바꿔` | dry | PASS (verify: 0.995) | FAIL (verify: 0.930) | Jev 검증 점수 미달 (0.93 < 0.95) |
| `거실 에어컨 냉방 25도로` | cool, 25°C | PASS (verify: 0.998) | FAIL (verify: 0.940) | Jev 검증 점수 미달 (0.94 < 0.95) |
| `거실 에어컨 26도, 침실 에어컨 24도로` | 복합 온도 | FAIL (low_conf) | FAIL (verify: 0.880) | Decision은 계획단계 저신뢰, Jev는 검증미달 |
| `천장등 빨간색 밝기 30프로` | rgb, brightness | PASS (verify: 0.992) | FAIL (verify: 0.880) | Jev 검증 점수 미달 |
| `천장등 색온도 3500K로` | color_temp | PASS (verify: 0.999) | FAIL (low_conf) | Jev 계획단계 저신뢰 |
| `천장등 조금 어둡게 해줘` | brightness -10 | PASS (verify: 0.998) | FAIL (ambiguous) | Jev 상대 밝기 미지원 판정 |
| `거실불 꺼줘` | living lights off | PASS (verify: 0.993) | FAIL (verify: 0.660) | Jev 검증 점수 미달 |
| `거실전등 켜줘` | living lights on | PASS (verify: 0.986) | FAIL (verify: 0.240) | Jev 검증 점수 미달 |
| `거실 에어컨 -25도로` | 안전 거부 | PASS (range reject) | PASS (ambiguous reject) | 물리 전송 0건 안전 거부 |
| `천장등 밝기 -20%` | 안전 거부 | PASS (range reject) | PASS (range reject) | 물리 전송 0건 안전 거부 |
| `거실 불 끄고 현관문 열어줘` | 안전 거부 | PASS (ambiguous reject) | PASS (ambiguous reject) | 물리 전송 0건 안전 거부 |
| `아무거나 켜줘` | 안전 거부 | PASS (ambiguous reject) | PASS (ambiguous reject) | 물리 전송 0건 안전 거부 |
| `거실 불 켜져 있으면 꺼줘` | 안전 거부 | PASS (low_conf reject) | PASS (ambiguous reject) | 물리 전송 0건 안전 거부 |

### 모델 비교 분석 및 결론
1. **Calibration 차이**:
   - `microsoft/microsoft-decision-1`은 유효한 한국어 계획에 대해 0.985~0.999의 높은 검증 확신도를 산출합니다.
   - `typesafe/jev-1.13`은 추론 속도가 평균 ~2.0초로 빠르지만, 한국어 홈오토메이션 검증 Noul 확률이 0.83~0.94 구간에 집중되어 현재의 안전 임계값(0.95) 기준 `plan_not_verified`로 차단되는 비율이 높습니다.
   - Reviewer 지침에 따라 안전 임계값을 인위적으로 완화하지 않고 있는 그대로 보고합니다.
2. **부정 케이스 안전성**:
   - 두 모델 모두 음수 온도/밝기, 보안 장치(도어락) 혼합, 모호한 명령, 미지원 복합 조건 등 위험 명령에 대해 **100% (5/5) 안전 거부(전송 0건)**를 기록했습니다.
3. **운영 모델 권고**:
   - 현재 한국어 정확도 및 엄격한 0.95 검증 임계값 통과율 기준으로는 **`microsoft/microsoft-decision-1`을 운영 기본 모델로 유지**하는 것이 타당합니다.
   - `typesafe/jev-1.13`은 응답 속도 면에서 강점이 있으므로 향후 프롬프트 최적화 및 캘리브레이션 조율 연구 대상으로 권장합니다.

---

## 5. 정적 분석 및 테스트 증거

1. **단위 테스트**:
   - `uv run pytest -q`: **81 passed, 1 warning (Starlette testclient)**
2. **코드 린트 및 포맷 검사**:
   - `uv run ruff check addon/app tests scripts`: **0 issues**
   - `uv run ruff format --check addon/app tests scripts`: **19 files formatted, 0 issues**
3. **프론트엔드 검사**:
   - `node --check addon/app/fhc/static/app.js`: **정상 통과**
4. **Git 작업 트리**:
   - `git diff --check`: **공백/서식 이상 없음**
5. **테스트 자원 정리**:
   - 검증 완료 후 QEMU VM 프로세스 정상 종료 확인 (`system_powerdown` -> stopped).
   - `.local/test-resources.json`의 `state`를 `stopped`로 업데이트 완료.

---

## 6. 다음 단계 인계

FIX_03에서 요구된 모든 P1/P2 결함 수정, 실기동 테스트, 그리고 Microsoft Decision-1과 TypeSafe Jev 1.13 간의 라이브 비교 검증이 완료되었습니다. 검토를 위해 Reviewer에게 본 보고서를 인계합니다.
