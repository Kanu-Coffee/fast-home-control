# Fast Home Control: 001_domain-expansion-and-ux 구현 보고서 (REPORT)

- 작성일: 2026-10-13
- 역할: Executor
- 대상 계획: `.handoff/001_domain-expansion-and-ux/PLAN.md` (단계 A)
- 브랜치: `dev`
- 버전: `0.2.0-dev.1`

---

## 1. 개요 및 구현 범위

`PLAN.md`에 정의된 단계 A 요구사항을 충족하도록 다음 핵심 항목을 설계 및 구현했습니다.

1. **설정 UX 및 숨김 해결**:
   - `addon/config.yaml`의 기본 `options`에 API 키(`openrouter_api_key`, `azure_api_key`) 및 `openrouter_model`, Azure 엔드포인트/배포 설정을 기본 빈 값/기본값으로 명시하여, Home Assistant 설정 화면에서 "사용하지 않는 선택적 구성 옵션 표시" 없이 기본 노출되도록 개선.
   - Azure endpoint의 schema를 `str?`로 조정하여 빈 문자열 기본값과의 스키마 충돌을 방지하고 애플리케이션 레벨에서 HTTPS 검증 유지.
2. **사용자 리모컨 화면과 관리자 모드 분리**:
   - 기본 진입을 간결한 사용자 리모컨 모드로 재구성: 상시 연결 문구, 상시 진단, 미지원 도메인 나열을 기본 화면에서 제거하고, 자연어 입력창과 간결한 실행 결과 요약 제공.
   - 최근 성공한 명령을 기반으로 한 동적 원클릭 바로가기 카드(최대 6개) 제공.
   - 우측 상단 `사용자 / 관리자 모드` 전환 버튼을 통해 관리자 화면(동적 공급자/모델 폼, 연결 상태/수동 재탐색, 도메인/엔티티 세부 제어, 상세 진단 로그 및 기록 삭제) 분리.
3. **OpenRouter 모델 선택 및 동적 공급자 설정**:
   - `openrouter_model` 설정 추가 (기본값: `microsoft/microsoft-decision-1`).
   - 관리자 모드에서 OpenRouter와 Azure를 세그먼트 버튼으로 전환하여 해당 공급자의 설정 항목만 동적으로 입력 가능.
   - Supervisor 자기 옵션 API (`/addons/self/options`) 연동을 통해 비밀 키를 마스킹하고 안전하게 저장 및 즉시 재반영.
4. **공식 도메인 확장 (climate 및 light 매개변수)**:
   - `climate`: 전원 ON/OFF뿐 아니라 HVAC 모드(`set_hvac_mode: fan_only, cool, heat`), 온도 조절(`set_temperature`) 지원.
   - `light`: 단순 ON/OFF뿐 아니라 밝기 설정(`brightness_pct`), 상대 밝기 조절(`brightness_step_pct`), RGB 색상 설정(`rgb_color`) 지원.
   - `catalog.py`에서 엔티티별 기능 메타데이터(`hvac_modes`, `temp_range`, `color_modes`) 추출 및 모델 전달.
   - `ha.py`에서 WebSocket `call_service` 시 `service_data` 파라미터 전송 지원.
   - No-op 판정 개선: light가 이미 ON 상태여도 색상이나 밝기 변경 요청 시 정상 실행(no-op 처리 방지), 동일한 상태일 때만 `already_in_state` 처리.
5. **엔티티 세부 제어 정책 및 DB 마이그레이션**:
   - SQLite `PRAGMA user_version` v1에서 v2로 순차 마이그레이션 구현 (기존 정책 무손실 매핑).
   - 도메인 마스터 허용 스위치와 엔티티 개별 포함/제외 토글 지원.
   - 엔티티가 제외되거나 도메인이 OFF된 기기는 카탈로그 및 실행 대상에서 완전 배제.

---

## 2. 변경된 주요 파일 및 내용

| 파일 | 변경 내용 |
|---|---|
| `addon/config.yaml` | 버전 `0.2.0-dev.1` 승격, `options`에 API 및 모델 기본 키 노출, schema `azure_endpoint: str?` 변경 |
| `addon/translations/ko.yaml` | `openrouter_model` 번역 항목 추가 |
| `addon/app/fhc/__init__.py` | `VERSION = "0.2.0-dev.1"` 갱신 |
| `pyproject.toml` | 버전 `0.2.0.dev1` 승격 |
| `addon/app/fhc/config.py` | `openrouter_model` 필드 추가, `public_dict()`, Supervisor 자기 옵션 API 호출 및 options 비동기 저장 함수(`save_options`) 구현 |
| `addon/app/fhc/provider.py` | OpenRouter 모델 호출 시 하드코딩 대신 `self.options.openrouter_model` 사용 |
| `addon/app/fhc/ha.py` | `ha.call()`에 `service_data` 및 `return_response` 파라미터 지원, `ha.event()` 메타데이터 변경 감지 대상에 climate 속성 추가 |
| `addon/app/fhc/catalog.py` | `climate` 도메인 지원 추가, 엔티티별 기능(`features`: `hvac_modes`, `temp_range`, `color_modes`, `brightness`) 추출 및 `compact()` 확장, 정책 필터링 연동 |
| `addon/app/fhc/engine.py` | ON/OFF 하드코딩 프롬프트 제거 및 climate/light 매개변수 지원 프롬프트 확장, literal extractor(온도, 밝기, 색상), 엔티티별 dynamic action criteria 생성, typed plan 빌드, 세분화된 no-op 및 preflight 검증 |
| `addon/app/fhc/store.py` | SQLite `PRAGMA user_version` v1 -> v2 마이그레이션, 구조화된 `PolicyDict` 및 엔티티 정책(`set_entity_policy`), 최근 성공 명령 추출(`recent_shortcuts`) 구현 |
| `addon/app/fhc/main.py` | `GET/POST /api/config`, `GET /api/shortcuts`, 도메인/엔티티 정책 조회 및 업데이트(`GET/PUT /api/policy`) 엔드포인트 추가 |
| `addon/app/fhc/static/index.html` | 사용자 리모컨과 관리자 설정 패널 분리 마크업, 동적 바로가기 그리드, 세그먼트 컨트롤 및 엔티티 목록 아코디언 추가 |
| `addon/app/fhc/static/app.js` | 사용자/관리자 모드 토글, 원클릭 동적 바로가기 실행, 공급자 동적 설정 폼, 도메인/엔티티 세부 정책 제어 로직 구현 |
| `addon/app/fhc/static/style.css` | 리모컨 카드 레이아웃, 세그먼트 버튼, 토글 스위치, 반응형 스타일링 현대화 |
| `tests/conftest.py` | `FakeHA.call`에 `service_data` 및 `return_response` 시그니처 지원 및 호환 튜플 유지 |
| `tests/test_config.py` | 모델 기본값, 비밀키 마스킹(`public_dict`), `save_options` 파일 저장 테스트 추가 |
| `tests/test_api.py` | `/api/config`, `/api/shortcuts`, `/api/domains`, 엔티티별 `/api/policy` 테스트 추가 |
| `tests/test_engine.py` | climate 송풍(`fan_only`) 및 온도 조절(`set_temperature`), 범위 밖 온도 거부, light 색상/밝기 실행 및 on 상태 no-op 방지, 엔티티 제외 정책 테스트 추가 |
| `README.md`, `addon/DOCS.md`, `addon/CHANGELOG.md`, `docs/architecture.md` | 확장된 지원 도메인, UI 분리, 모델 설정 및 버전 `0.2.0-dev.1` 반영 |

---

## 3. 검증 결과

### 3.1 자동 단위 및 회귀 테스트
- **테스트 러너**: `uv run pytest -q`
- **결과**: `44 passed, 1 warning in 1.99s` (기존 37개 + 신규 7개 테스트 전체 통과)
- **통과 항목 요약**:
  - 기존 light/switch ON/OFF 전 기능 회귀 없음 검증.
  - climate 송풍 모드(`fan_only`) 및 온도 설정(`25.0°C`) 정상 실행 검증.
  - climate 범위 밖 온도(`50°C`) 안전 거부(`temperature_out_of_range`) 검증.
  - light ON 상태에서 색상(`rgb_color`) 및 밝기(`brightness_step_pct`) 변경 시 no-op 오판 없이 정상 실행 검증.
  - 동일한 상태일 때만 `already_in_state` no-op 처리 검증.
  - 엔티티 개별 정책 제외 시 카탈로그 제외 검증.
  - SQLite `user_version` v1 -> v2 마이그레이션 및 정책 하위 호환성 검증.
  - `public_dict` 호출 시 비밀키 원문 미노출(마스킹) 검증.
  - 신규 API 엔드포인트(`/api/config`, `/api/shortcuts`, `/api/domains`, `/api/policy`) 계약 검증.

### 3.2 린트 및 코드 포맷
- **Ruff Lint**: `uv run ruff check addon/app tests scripts` → **All checks passed!**
- **Ruff Format**: `uv run ruff format --check addon/app tests scripts` → **16 files already formatted**
- **JavaScript 구문 검사**: `node --check addon/app/fhc/static/app.js` → **통과 (오류 없음)**

### 3.3 컨테이너 빌드 검증
- **명령**: `docker build -t fhc-check addon`
- **결과**: 정상 빌드 완료 (`exporting to image`, `naming to docker.io/library/fhc-check:latest`)

---

## 4. 계획 대비 세부 조정 사항 (Deviations)

1. **`ha.call` 호환 시그니처 및 테스트 러너**:
   - `ha.py`의 `call` 메서드에 `service_data` 및 `return_response` 파라미터를 추가하면서, `engine.py`에서는 `service_data`가 없을 때 불필요한 빈 딕셔너리 대신 기본 키워드 인자 없이 호출하도록 처리하여 기존 FakeHA 및 레거시 어댑터와의 하위 호환성을 완벽히 유지했습니다.
2. **동적 바로가기 실행 연타 방지**:
   - 바로가기 카드는 사용자가 연타하거나 이전 요청 처리 중일 때 중복 호출되지 않도록 `busy` 가드를 공유하며, 실패/모호 요청은 카드 추천에서 제외하도록 필터링했습니다.

---

## 5. 남은 제약 및 후속 과제 (단계 B/C)

- **단계 B**: fan, cover, humidifier, vacuum, media_player 및 도우미 도메인(input_boolean, number, select) 확장.
- **단계 C**: sensor, weather, calendar, todo 등 읽기 전용 및 결과 포맷형 서비스 확장.
- **라이브 HAOS/VM 연동**: 본 단계 A의 구현 및 단위 테스트는 통과하였으며, 사용자 피드백에 따라 개발 전용 HAOS 인스턴스에 업그레이드 배포하여 실기동 확인 가능합니다.
