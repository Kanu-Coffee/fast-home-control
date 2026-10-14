# FIX_06_REPORT — FIX_06 보정 구현 및 실기동(모의/실모델 분리) 보고서

작성일: 2026-10-14 · 역할: Executor · 판정: **R1~R5 보정 완료, 실기동 서비스 계약 통과, 실모델 왕복은 튜닝 잔여로 정직 기록**

기준: `FIX_06.md`(Reviewer). FIX_05에서 인정된 부분(password/read 정책·TTS target·저널·rename·조명/공조 회귀)은 재작성하지 않고 유지했다.

---

## 1. 검증 명령과 결과(모든 라운드)

| 항목 | 결과 |
| --- | --- |
| `uv run pytest -q` | **109 passed**(FIX_05 대비 +8: FIX_06 R1~R4 회귀), Starlette deprecation warning 1개 |
| `uv run ruff check addon/app tests scripts` / `ruff format --check` | 통과 / 20 files |
| `node --check addon/app/fhc/static/app.js`, `git diff --check` | 통과 |
| 실기동(프로젝트 소유 HAOS VM) | §5 참조 — **service_contract 9/9(scripted-mock+실HA, 라벨 명기)**, e2e Microsoft 2/7·Jev 1/7(모두 안전 거부, 잘못된 전송 0건) |

## 2. R1 — 실제 달력 응답 계약

- `format_response`가 Core 2026.10.1 `calendar/services.py`의 실제 응답(`{"events": [...]}`, start/end ISO 문자열; dict `date/dateTime` 구형도 허용)을 파싱하도록 수정. `(display, contract)` 튜플을 반환하고 `action["response_contract"]`·`query_results[].response_contract`에 ok/empty/**malformed**를 기록 — 응답 키 불일치를 "일정이 없습니다" 성공으로 처리하지 않음. todo/weather도 같은 구분 적용.
- `response_query` 처리와 무관했던 기존 단위 테스트 fixture를 실제 스키마(`{"events": [...]}`)로 교체(`test_fix05_r2_readonly_calendar…`), 계약 오류 재현/식별 테스트 추가(`test_fix06_r1_calendar_response_contract`, `…_engine_malformed_calendar_display`).
- **실기동**: fixture VM에 로컬 캘린더(config entry)를 생성하고 scripted-mock으로 `create_event(start/end)→get_events` read-back → 제목 `FHC 회의` 1건이 응답과 사용자 표시(`1개 일정: 2026-10-15T14:30 FHC 회의`)에 실제 표시. `.local/fix06-live-scripted.json`.

## 3. R2 — 일정 생성 종료 시각·한국어 시각 토큰·timezone

- `create_event`: 시간 지정 시 `calendar_time`(시작)과 **`calendar_end_time`(종료)** 토큰을 모두 요구 → `start_date_time`/`end_date_time` 페어 생성. 종료 없으면 `calendar_end_required`로 거부하고 **임의 1시간 duration을 만들지 않음**(잘못된 `duration` 필드 제거 — get_events 전용 필드다). 종일 일정은 start_date/end_date 유지. `end<=start` 거부.
- `temporal_tokens` 확장: `오후 8시 30분`→20:30(오전/아침/새벽=am, 오후/저녁/점심=pm, `밤`은 ambiguous → 옵션 비노출·선택 시 거부), `HH:MM` 유지, `10월 20일` month_day 토큰(연도 경계: 지남이면 다음 해). input_datetime은 has_date/has_time에 따라 `datetime_day_value`/`datetime_time_value` **두 요소 동시 선택 지원** → `{"datetime": "2026-10-20 15:30:00"}` 결합(has_date+has_time 헬퍼의 공식 규약).
- timezone: `Engine._now`가 HA `time_zone`을 확인할 수 없으면 UTC 가정 없이 **None**을 반환하고, 날짜/시간 쓰기·조회는 `timezone_unknown`으로 거부. bare `도` 조건 단위는 HA 설정 단위, 없으면 센서 native.
- 테스트: fix05_r4(14:30~16:00 start/end, duration 부재, 종료 누락 거부), fix06_r2(KO 토큰·중복 span·month_day, date+time 결합, ambiguous 밤, timezone naive/None 거부). 시각은 fixed `datetime(2026,10,14, tz=Asia/Seoul)`로 날짜 의존 제거.
- **실기동**: `기상 시각을 오후 8시 30분으로 설정해줘` → VM의 새 `input_datetime.fhc_wake`(has_time) helper에 write 후 read-back state `20:30:00` 확인. 달력 `내일 14:30~16:00` 생성 read-back 확인. `.local/fix06-live-scripted.json`.

## 4. R3 — todo 참조를 첫 쓰기 전 preflight로 이동

- `_resolve_todo_item`을 `_execute_plan` 루프에서 **preflight 루프**(모든 primary/secondary 검증과 같은 구간)로 이동. 모든 plan action의 UID 해석·policy·identity·secondary 가용성을 검사한 뒤 환경 재확인(ready/version/policy)을 통과해야만 execution 단계가 시작된다. 해석 구간에서.await(읽기) 중 registry/policy가 바뀌면 `environment_changed`로 0건 거부.
- 재현 테스트: `거실불 끄고 장보기 목록에서 'FHC 우유' 완료로 바꿔줘`(동명 2건) → **rejected/todo_item_ambiguous, light.turn_off 포함 제어 전송 0건, 읽기(get_items)와 쓰기 호출을 response_calls/calls로 분리 기록**. not_found도 preflight에서 0건.
- **실기동**: 위 혼합 명령을 실제 VM(todo 동명 2건 시드)에서 실행 → 0 전송. `.local/fix06-live-scripted.json: todo_duplicate_refused_before_write`.

## 5. R4 — 조건 분류/단위를 독립 typed 계약으로

- scope의 `conditional` noul(0.7) 폐지 → **`condition_class` 3-way choice**: none(조건 없음)/typed(명확한 수치 비교 조건)/unclear(조건 구문이 실제로 존재하나 부정·복합·기준 없음·대상 모호). unclear는 `condition_unsupported`로 별도 거부(사유 구분, 로컬 정규식 판정 아님). 최소 확신 0.7 — **중간 확신(예: 0.68 typed)은 조건 없음으로 강등되지 않고 `low_confidence`로 실행 0건**(`DoubtfulConditionProvider` 회귀로 재현).
- 단위 계약: source에 번역 가능한 native 단위가 없으면 `condition_unit_unspecified`; 모델 선택 단위가 원문 명시 단위와 다르면 `condition_unit_conflict`; sensor/ literal/ 선택 단위 3자 교차 검증 후 변환 비교. 해석된 값·단위·연산 기호를 최종 `exact` 검증 상태(`verify_state["condition"]`)에 제공한다.
- VALID 문구에서 "부정/복합 조건 false"를 제거해 supported와 condition 분류가 서로를 침범하지 않음. 명확한 비조건 명령(동의어 포함)의 정상 경로는 회귀 테스트로 유지(`test_fix06_r4_condition_unclear_and_unit_guards` 케이스 4).
- 실기동: 조건 false 왕복은 이번 Microsoft run에서 `low_confidence`(actions phase)로 안전 거부 — 왕복 미통과로 정직 기록(§6).

## 6. R5 — live 하네스 3단계 분리 및 실기동 결과

`scripts/verify_fix05_live.py` → **`scripts/verify_live_bc.py`**로 재작성. case마다 `layer`를 명기하고 **실행되지 않은 서비스는 pass 계산에서 제외(not_exercised)**:

- **service_contract(scripted-mock 모델 + 실제 HA 서비스, 출력에 라벨)**: calendar 생성(start/end)·read-back 표시·get_events nonempty·weather daily 예보 응답·TTS speak 실호출(media_player.bedroom payload)·todo 동명/부재 preflight 거부·input_datetime 20:30 read-back·climate 24도 read-back → **9/9 asserted pass, not_exercised 0**.
- **e2e_model(실제 OpenRouter 모델, 안전 임계값 미완화)**:
  - Microsoft Decision-1 **2/7**: todo not-found(0건)·TTS 모호(0건) 통과; R5 조건/TTS 지정 `low_confidence`(actions), calendar/weather `conflicting_actions`(모델이 query와 응답조회 혼선택), climate `plan_not_verified` — 전부 전송 0건.
  - Jev 1.13 **1/7**: 6건 `unsupported_or_ambiguous`/`plan_not_verified`, 0 전송.
  - 실패 사유·phase를 `.local/fix06-live-microsoft_microsoft-decision-1.json` / `…-typesafe_jev-1.13.json`에 케이스별 저장(모델별 별도 파일, 덮어쓰기·누적 없음).
- **R1 live**: VM에 password `input_text.fhc_secret` helper를 추가하고 `FHC 기록 값 알려줘` → catalog·질문·query_results 전부 비노출, evidence `.local/fix06-live-r1-password.json`(pass; 명령 원문 문자열만 model input에 존재 — 원문은 비신뢰 데이터로 노출 자체가 무해).
- fixture 상태 누적 방지: 매 run `local_calendar` config entry 재생성(get_events 응답에 uid가 없어 이벤트 단위 삭제 불가), FHC* todo 시드 정리. demo read-only 캘린더·중복 weather는 정책으로 제외해 **모호성 실패가 fixture 노이즈가 아니라 앱 판단이 되도록** 함(실사용 환경의 모호성 보호와는 무관).
- VM fixture 변경(README/`tests/fixtures/haos.yaml`에 기록): input_datetime/input_text 블록 YAML 추가, local_calendar는 YAML platform이 제거되어 config-flow API로 생성(하네스가 자동 수행).

## 7. 설치형 검증 상태 — 미완료(정직 기록)

- dev.8 버전 표기(config/package/Docker/UI)는 통일했지만 **VM에는 dev.7 addon이 설치 상태로 남아 있고 dev.8 미설치**. 설치는 (a) dev 리포지토리의 커밋/푸시(사용자 승인 행위) 또는 (b) Supervisor `.storage`/local repo에 대한 비문서적 수술이 필요해 이번 라운드에서 수행하지 않았다. R5의 "addon 설치/Ingress/관리자 읽기 토글/로그 다운로드" 실측은 **차기 설치 검증 라운드의 blocker**로 남는다.
- 운영 VM·다른 Docker 서비스·호스트 방화벽 변경 없음. VM은 ACPI 정상 종료(stopped), baseline 디스크/OVMF 보존. `.local` 증거·갱신 토큰은 Git 제외.

## 8. 남은 리스크

1. `condition_class` 선택 질문 추가 후 Decision-1의 actions-phase 저신뢰가 관측됨(§6). 로컬 정규식으로 되돌리지 않고, 질문 분할/기준 문구·후보 표현(별칭/영역 노출) 튜닝이 필요. 성능 재생(초 단위 기준) 요구 없음.
2. calendar/weather 실체 복수 시 모델의 query+response 혼선택(conflicting) — 안전 거부는 유지되나 왕복률을 낮춘다. 스코프 그룹핑 개선 후보.
3. demo fixture의 영문 friendly name(Bedroom 등)과 한국어 지칭 대응은 모델 의미 판단에 의존 — 실기동에서 TTS 지정 왕복 실패의 원인 중 하나.
4. `get_events` 응답에 uid가 없는 HA 계약상 일정 단위 삭제는 config entry 재생성으로 대체(주거용 데이터 아님).

## 9. 최종 변경/상태

- 제품: `actions.py`(temporal/create_pair/datetime_split/access 계약 확장), `engine.py`(format_response+contract, preflight 참조 해석 통합, condition_class 3-way, 단위 strict, `_now` tz-required), 관련 store/main/static 변경은 FIX_05에서 유지.
- 테스트: `conftest.py`(condition_class 대응, 실HA 중첩 응답 형태), `test_corrections.py` +8 회귀·수정, `tests/fixtures/haos.yaml` 도커 헬퍼 반영, `scripts/verify_live_bc.py` 신규(구 verify_fix05_live.py 대체), `scripts/evaluate_stage_a.py` 갱신 유지.
- 버전 0.2.0-dev.8 그대로(미설치), 커밋하지 않음(작업 트리 유지). 109 passed / ruff / node / diff-check 전부 통과.
