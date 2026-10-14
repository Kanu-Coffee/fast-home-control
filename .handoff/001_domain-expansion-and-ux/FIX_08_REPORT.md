# FIX_08_REPORT — condition_unit 예외 분류 보정 및 지표·문서 정합성 정정

작성일: 2026-10-14 · 역할: Executor · 판정: **R1/R2 보정 완료, dev.9 버전 반영, 회귀 테스트 전원 통과**

기준: `FIX_08.md`(Reviewer, HEAD `289af02`). FIX_07까지 검증된 기능(B/C 확장, 설치형 Ingress/정책/진단 다운로드, 비밀 마스킹 등)은 그대로 유지하고, Reviewer가 지적한 P2 2건(R1 예외 분류, R2 검증 문서 및 지표 표기)을 정밀 보정했다.

---

## 1. 검증 명령 및 결과

- `uv run pytest -q`: **115 passed** (기존 114개 + `test_fix08_r1_malformed_condition_unit_fails_closed` 1개, Starlette warning 1개 동일).
- `uv run ruff check addon/app tests scripts`: **All checks passed!**
- `uv run ruff format --check addon/app tests scripts`: **20 files already formatted**.
- `hadolint addon/Dockerfile`: **통과** (exit code 0).
- `node --check addon/app/fhc/static/app.js`: **통과** (exit code 0).
- `git diff --check`: **통과** (공백/충돌 마커 없음).

---

## 2. R1 [P2] — condition_unit의 low_confidence와 invalid_model_response 구분

### 원인 및 문제
기존 `addon/app/fhc/engine.py:Engine._select_condition`에서는 `condition_unit` 선택 시 `except DecisionError:`로 모든 DecisionError를 포괄하여 잡은 뒤 `unit = "none"`으로 설정했다. 이로 인해 모델 응답이 구조적으로 깨지거나(`invalid_model_response`: malformed type, label mismatch, probability 문자열, NaN, 확률 합계 불일치 등) 발생해도 fallback으로 삼켜져 정상 단위 파생으로 처리되고 실제 HA 명령이 실행될 수 있는 공백이 존재했다.

### 구현 내용
1. `addon/app/fhc/engine.py:Engine._select_condition`:
   - `condition_unit`의 `except DecisionError as exc`에서 `exc.code == "low_confidence"`일 때만 안전하게 `unit = "none"`(literal/native 파생)으로 강등하도록 한정.
   - `invalid_model_response` 등 구조적/형식적 에러는 그대로 `raise`하여 fail-closed 처리(`status="rejected"`, `reason="invalid_model_response"`, HA 전송 0건).
   - `condition_source`, `condition_operator`, `condition_value` 선택부에서도 `exc.code == "invalid_model_response"` 발생 시 `condition_evaluation_failed`로 감싸지 않고 본래의 `invalid_model_response`를 유지하여 즉시 거부되도록 보정.
2. 단위 및 회귀 검증 (`tests/test_corrections.py:test_fix08_r1_malformed_condition_unit_fails_closed`):
   - Reviewer 재현 사례: `probabilities: {'°C': 'not-a-probability'}` → `rejected`, `invalid_model_response`, HA 전송 0건.
   - Malformed type (`type: "invalid_type"`) → `rejected`, `invalid_model_response`, HA 전송 0건.
   - 확률 합계 불일치 (0.5 != 1.0) → `rejected`, `invalid_model_response`, HA 전송 0건.
   - 확률 레이블 불일치 (`wrong_label`) → `rejected`, `invalid_model_response`, HA 전송 0건.
   - 정상 구조이나 낮은 확신도 (`0.45 < 0.6`) → `unit="none"`으로 fallback 후 literal/native에서 단위 정상 유도, `succeeded`, `condition_result=True`, HA `light.turn_off` 1건 정상 실행.

---

## 3. R2 [P2] — 결과 표 및 검증 범위 일치화

### 문서 정정 (`docs/verification.md`)
1. **계층 및 분모 분리**:
   - **서비스 계약 (호스트 Engine → 동일 테스트 HA, 모의 모델 라벨 + 실제 HA 서비스)**:
     - `service_contract 8개`: 달력 start/end 생성 후 이벤트 제목 read-back, get_events 실제 `{"events":[...]}` 응답 표시, weather 지원 예보 유형 실응답, TTS speak의 media_player_entity_id=선택 스피커(고정 fallback 없음), todo 동명/부재 preflight 0전송 거부, input_datetime 오후 8시 30분→20:30 read-back, climate 목표온도.
     - `safety_negative 1개`: password mode input_text 제외 및 안전 거부.
     - 합계 **9개 assertion 통과**.
   - **실모델 왕복 (정상 요청 6건 + 음성 사례 2건, 합계 8건)**:
     - **Microsoft Decision-1**: 전체 기대 결과 일치 **6/8**
       - 정상 요청 6개 중 5개 성공 (조명 off, typed 조건 false(0전송), TTS 출력 지정 전송, 일정 조회, 예보 조회).
       - 공조 온도 설정 1건은 `plan_not_verified`로 거부.
       - 음성 사례 2개 중 1개 기대 사유 일치 (TTS 모호 거부).
       - todo 부재 사례는 corpus 기대 사유 `todo_item_not_found`와 달리 `plan_not_verified`로 거부되어 사유 불일치 (0전송 안전 거부).
       - 거부 사례의 실제 물리 전송은 모두 0건.
     - **TypeSafe Jev 1.13**: 전체 기대 결과 일치 **2/8**
       - 정상 요청 6개 중 1개 공조 온도 설정 실전송 성공 (나머지 5건은 거부).
       - 음성 사례 2개 중 1개 기대 사유 일치 (TTS 모호 거부).
       - 거부 사례의 실제 물리 전송은 모두 0건.
2. **설치 앱 검증과 호스트 엔진 테스트 명확한 구분**:
   - 최신 설치형 앱(HAOS 애드온 Ingress)에서 직접 확인한 항목은 `조명 off 실전송`, `정책 저장 및 애드온 재시작 후 보존`, `진단 ZIP 다운로드(토큰/비밀번호/명령원문 비노출)`.
   - 달력·TTS·날씨 등의 심층 계약 검증은 `호스트 Engine → 동일 테스트 HA` 경로임을 명확히 기술.
   - 대표 기능 MVP와 미지원 기능(notify send_message 왕복 미검증, time/date 미지원 등)의 경계를 명시.

---

## 4. 버전 갱신 (0.2.0-dev.9)

코드 변경에 따라 `0.2.0-dev.8`에서 `0.2.0-dev.9`로 버전을 상향 조정하고 프로젝트 내 모든 설정 파일을 일치시켰다:
- `addon/config.yaml`: `version: 0.2.0-dev.9`
- `addon/app/fhc/__init__.py`: `VERSION = "0.2.0-dev.9"`
- `pyproject.toml`: `version = "0.2.0.dev9"`
- `addon/Dockerfile`: `ARG BUILD_VERSION=0.2.0-dev.9`
- `addon/app/fhc/static/index.html`: `0.2.0-dev.9`
- `addon/CHANGELOG.md`: `0.2.0-dev.9` 변경 내역 추가
- `uv.lock`: `uv sync`를 통해 종속성 잠금 파일 갱신

---

## 5. 최종 상태 및 Git 상태

- 테스트 통과: 115 passed
- 코드 스타일/린트: ruff check & format, hadolint, node --check 모두 통과
- Git 브랜치: `dev`
- 변경 파일:
  - `addon/app/fhc/engine.py` (R1)
  - `tests/test_corrections.py` (R1 테스트)
  - `docs/verification.md` (R2)
  - `addon/config.yaml`, `addon/app/fhc/__init__.py`, `pyproject.toml`, `addon/Dockerfile`, `addon/app/fhc/static/index.html`, `addon/CHANGELOG.md`, `uv.lock` (버전 갱신)
  - `.handoff/001_domain-expansion-and-ux/FIX_08_REPORT.md` (본 보고서)
- Main 브랜치 승인 및 안정 릴리스는 사용자 명시 승인 시까지 보류됨.
