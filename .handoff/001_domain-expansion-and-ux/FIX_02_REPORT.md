# FIX_02_REPORT — A단계 결함 보정 및 B/C 도메인 확장 실행 보고서

- 작성일: 2026-10-13
- 역할: Executor
- 참조 문서: `PLAN.md`, `REPORT.md`, `FIX_01.md`, `FIX_01_REPORT.md`, `FIX_02.md`
- 대상 브랜치: `dev`, 앱 버전 `0.2.0-dev.7` (pyproject.toml `0.2.0.dev7`, addon/config.yaml `0.2.0-dev.7`, Dockerfile `0.2.0-dev.7`)

---

## 1. 개요 및 실행 요약

Reviewer의 `FIX_02.md` 지침에 따라 다음 작업을 단일 개발 주기로 완결했습니다:
1. **F1 [P1] 원자적 레지스트리 reconcile**: 다중 이름 변경, 이름 교환(swap), 순환 rename(cycle) 발생 시 단일 snapshot에서 대상 매핑을 원자적으로 일괄 계산 및 적용하여 기존 비활성화(제외) 정책이 조용히 유실되는 결함을 해결했습니다.
2. **F2 [P2] 이력 삭제 시 계획 및 개인정보 완전 제거**: `clear_history()` 시 `ALLOWED_FIELDS` 화이트리스트(`id`, `created`, `status`, `reason`, `hidden`, `timings_ms`, `providers`, `model_calls`)만 보존하고 `proposed_plan`, `query_results`, `text`, `actions` 등 모든 명령 본문과 기기 정보를 영구 제거했습니다.
3. **F3 [P2] 발견/제어/조회/허용 엔티티 수 분리**: `/api/domains` DTO에 `discovered_count`, `controllable_count`, `queryable_count`, `allowed_control_count`, `allowed_query_count`, `status`, `note`를 추가하고, 관리자 UI에서 각 도메인별 상태와 개수를 정직하게 표시하도록 개선했습니다.
4. **F4 [신규 필수] 관리자 진단 로그 다운로드 구현**: `GET /api/history/export` 엔드포인트를 구현하여 표준 ZIP 아카이브(`manifest.json`, `summary.json`, `requests.jsonl`)를 제공하고, HA 관리자 권한 검증, 재귀적 민감정보 redaction, 명령 원문 포함 토글(기본 OFF), 삭제된 이력의 완전 배제를 적용했습니다.
5. **B 도메인 확장 (일반 가전 및 명시 실행)**: vacuum, button, fan, cover, humidifier, media_player, input_boolean, number/input_number, select/input_select, counter, script, automation, scene을 지원하도록 capabilities, options_for, make_action, preflight, no-op 판정, HA 서비스 디스패치를 확장했습니다.
6. **C 도메인 확장 (상태 조회, 단순 명시 조건, 제한 쓰기)**: sensor, binary_sensor, weather, calendar, todo, person, device_tracker, zone, sun, event, camera, image, update 상태 조회를 구현(HA 물리 서비스 미호출, query_result 기록)하고, "거실 온도가 28도 이상이면 에어컨 냉방 25도로"와 같은 단순 명시 조건을 사전 평가하여 조건 불만족 시 서비스 호출 0건으로 정상 종료하도록 구현했습니다.

---

## 2. 세부 구현 내용

### 2.1 F1: 원자적 레지스트리 reconcile (`addon/app/fhc/store.py`)
- 기존 순회 중 in-place 삭제로 인해 발생하던 교환/순환 rename 시의 override 유실을 방지하기 위해, `by_identity` 및 `ha.renames`를 바탕으로 전체 목적지 매핑 `new_entities`를 새로 빌드한 후 한 번에 저장합니다.
- 동일 대상 ID로 복수의 override가 수렴할 경우, 둘 중 하나라도 제외(`enabled=False`) 정책이 존재하면 최종 정책도 `enabled=False`로 보수적으로 유지합니다.

### 2.2 F2: 이력 내용 완전 제거 화이트리스트 (`addon/app/fhc/store.py`)
- `clear_history()` 호출 시 SQLite의 전체 요청 레코드에 대해 허용된 메타데이터 키(`ALLOWED_FIELDS`)만 남기고 `text=""`, `actions=[]`, `hidden=True`로 갱신합니다.
- `proposed_plan`, `query_results`, `decisions`, `model_trace` 등 원문 및 기기 정보가 포함된 키는 완전히 드롭되어 디스크 DB에 남지 않으며, 다운로드/바로가기 API에서도 노출되지 않습니다.

### 2.3 F3: 엔티티 집계 및 미지원/보류 사유 명시 (`addon/app/fhc/main.py`, `catalog.py`, `app.js`)
- `all_known_eids = registry_eids | state_eids`를 통해 실제 HA 환경에서 발견된 전체 엔티티 수를 산출합니다.
- 도메인별 특성에 따라 상태를 구분:
  - `deferred`: `ai_task`, `conversation` ("AI 태스크/음성 대화 도메인은 직접 가전 제어가 아니므로 보류")
  - `unsupported`: FHC 미지원 도메인 ("현재 미지원 도메인입니다.")
  - `query_only`: sensor, weather, calendar 등 ("상태 및 정보 조회만 지원")
  - `supported`: light, switch, climate, vacuum 등 ("제어 및 자동화 지원")
- UI 배지 표시:
  - 예: `발견 12개 · 조회 가능 10개 · 허용 8개`
  - 예: `발견 2개 · AI 태스크 도메인은 직접 가전 제어가 아니므로 보류`

### 2.4 F4: 관리자 진단 로그 다운로드 (`addon/app/fhc/main.py`, `app.js`, `style.css`)
- **라우트**: `GET /api/history/export`
- **보안/권한**: HTTP 미들웨어에서 `/api/history/export` 및 `/api/history/` 하위 경로에 대해 Ingress 관리자 권한(`ha.is_admin`)을 강제 적용합니다.
- **포맷**: 표준 `zipfile`을 사용하여 단일 ZIP 파일(`fhc-diagnostics-{VERSION}-{TIMESTAMP}.zip`) 생성.
  - `manifest.json`: 스키마 버전, 앱 버전, HA 버전, 생성 시각, 원문 포함 여부, 대상 레코드 수.
  - `summary.json`: 상태별 건수, 평균 소요 시간(ms), 사용된 AI 공급자.
  - `requests.jsonl`: 요청별 진단 로그 (줄바꿈 구분 JSON).
- **Redaction**:
  - 기본 모드(`include_text=False`): 사용자 명령 원문, 엔티티 ID, 기기명, 영역명을 일관된 가명(`entity_1`, `device_1`, `area_1`)으로 마스킹.
  - 원문 포함 모드(`include_text=True`): 분석을 위해 원문 및 기기명을 남기되, OpenRouter/Azure API 키, Supervisor 토큰, 세션 토큰, 패스워드, GPS 좌표는 엄격하게 마스킹.
  - 삭제된(`hidden=True`) 레코드는 원문 포함 모드에서도 절대 내보내지 않음.

### 2.5 B 도메인 확장 (`addon/app/fhc/actions.py`, `catalog.py`, `engine.py`)
- **vacuum**: `start`, `pause`, `stop`, `return_to_base` (이미 docked 상태일 때 return_to_base no-op 처리).
- **button**: `press` (초기 unknown 상태 허용).
- **fan**: `turn_on`, `turn_off`, `set_percentage`, `oscillate`.
- **cover**: `open_cover`, `close_cover`, `stop_cover`, `set_cover_position`.
- **humidifier**: `turn_on`, `turn_off`, `set_humidity`, `set_mode`.
- **media_player**: `turn_on`, `turn_off`, `media_play`, `media_pause`, `media_stop`, `volume_set`, `volume_mute`.
- **helpers**: `input_boolean`, `number` / `input_number`, `select` / `input_select`, `counter`, `script`, `automation`, `scene`.

### 2.6 C 도메인 확장 및 단순 조건 사전 검증 (`addon/app/fhc/actions.py`, `engine.py`)
- **상태 조회**: sensor, binary_sensor, weather, calendar, todo, person, device_tracker, zone, sun, event, camera, image, update.
  - `make_action` 시 `is_query=True` 설정.
  - `engine.py`에서 물리 HA 서비스를 호출하지 않고 `ha.fresh_state`를 조회하여 `action["query_result"]` 및 `record["query_results"]`에 포맷팅 후 `query_succeeded`로 완료.
- **단순 명시 조건 평가**:
  - "거실 온도가 28도 이상이면 에어컨 냉방 25도로" 패턴을 `_evaluate_condition()`에서 파싱.
  - 카탈로그의 센서를 매칭하고 최신 센서 값을 읽어 `curr_val >= target_val`을 평가.
  - 조건 불만족(False) 시 물리 서비스 호출 0건, `record["status"] = "succeeded"`, `record["reason"] = "condition_not_met"`, `record["condition_result"] = False`로 즉시 정상 종료.

---

## 3. 검증 증거 및 결과

| 검증 항목 | 명령어 | 결과 |
|---|---|---|
| 단위 및 통합 테스트 | `uv run pytest -q` | **77 passed**, 1 warning, 2.38s |
| Python 린터 | `uv run ruff check addon/app tests scripts` | All checks passed! |
| Python 포매터 | `uv run ruff format --check addon/app tests scripts` | 19 files already formatted |
| JavaScript 구문 검사 | `node --check addon/app/fhc/static/app.js` | 정상 통과 |
| Git 변경 공백 검사 | `git diff --check` | 정상 통과 |
| Docker 컨테이너 빌드 | `docker build -t fhc-check addon` | 정상 빌드 완료 (11/11 stages) |

### 3.1 신규 추가된 회귀 테스트 (`tests/test_corrections.py`)
- `test_f1_swap_and_cycle_renames_preserve_exclusion`: 두 엔티티 이름 교환(swap) 및 3개 엔티티 순환(cycle) rename 시 제외 정책(`enabled=False`)이 온전히 유지됨을 검증.
- `test_f2_clear_history_strictly_wipes_proposed_plan_and_contents`: 이력 삭제 시 `proposed_plan`, `query_results`, 원문 텍스트가 DB에서 물리적으로 드롭됨을 검증.
- `test_f3_domains_endpoint_detailed_counts`: `/api/domains`에서 `discovered_count`, `controllable_count`, `queryable_count`, `allowed_control_count`, `status`, `note`의 분리 계산 및 반환 검증.
- `test_f4_diagnostic_export_zip_and_redaction`: 비관리자 403 차단, 관리자 ZIP 압축 다운로드, `manifest.json`/`summary.json`/`requests.jsonl` 파일 구조, 민감 토큰 마스킹, hidden 레코드 배제 검증.
- `test_expanded_b_domains_execution`: vacuum `return_to_base`, button `press`의 실제 디스패치 및 초기 상태 처리 검증.
- `test_c_domain_query_and_condition_evaluation`: sensor 상태 조회(물리 호출 없음), 단순 조건 충족 시 제어 호출, 단순 조건 불만족 시 0건 호출(`condition_not_met`) 검증.

---

## 4. 제약 사항 및 보류 항목

1. **ai_task / conversation**: 일반 가전 실행 범위가 아니므로 명시적으로 `deferred`로 분류하고 사유를 UI/API에 안내합니다.
2. **시스템 업데이트 / OS 제어 (`update`)**: 버전 조회만 지원하며, 시스템 변경 작업(install/skip)은 가전 리모컨 범위 밖으로 보호 유지합니다.
3. **복잡한 장기 스케줄링**: "10분 뒤 꺼줘", "매일 아침 7시에" 등 복잡한 시간 기반 예약은 HA Automation의 고유 영역으로 보류를 유지하며, 즉시 실행 및 단발성 상태 조회에 집중합니다.
4. **Mock vs Live 구분**: 이번 회귀 및 신규 검증은 프로젝트 내부 격리 테스트 및 가상 fixture를 기반으로 수행되었습니다. 실운영 HAOS 기기에는 사용자 최종 확인 후 제공됩니다.

---

## 5. 변경 파일 목록

- `addon/app/fhc/store.py`: F1 원자적 레지스트리 reconcile, F2 화이트리스트 기반 이력 클리어
- `addon/app/fhc/catalog.py`: B/C 도메인 SUPPORTED & DEFERRED 딕셔너리 확장, compact() 메타데이터 보강
- `addon/app/fhc/actions.py`: B/C 도메인 capabilities, options_for, make_action, validate_fresh, is_already_in_state, describe_action 전면 확장
- `addon/app/fhc/engine.py`: B/C 액션 프롬프트 및 지원 목록 반영, 쿼리 비물리 실행, 단순 명시 조건 사전 평가
- `addon/app/fhc/main.py`: `/api/domains` 상세 카운트 반환, `GET /api/history/export` ZIP 다운로드 및 redaction, 관리자 권한 보호 미들웨어 경로 검증
- `addon/app/fhc/static/index.html`: 진단 로그 다운로드 버튼 및 원문 포함 체크박스 추가, 버전 표기 갱신
- `addon/app/fhc/static/app.js`: F3 상태/카운트 상세 렌더링, 로그 ZIP blob 다운로드 구현
- `addon/app/fhc/static/style.css`: 로그 다운로드 버튼 및 내보내기 옵션 스타일 추가
- `tests/test_corrections.py`: F1, F2, F3, F4, B 도메인, C 도메인, 조건 검증 테스트 추가 (총 77개 테스트 통과)
- `addon/app/fhc/__init__.py`: 버전 0.2.0-dev.7 갱신
- `pyproject.toml`: 버전 0.2.0.dev7 갱신
- `addon/config.yaml`: 버전 0.2.0-dev.7 갱신
- `addon/Dockerfile`: 빌드 버전 0.2.0-dev.7 갱신
- `addon/CHANGELOG.md`: 0.2.0-dev.7 변경 내역 기록
