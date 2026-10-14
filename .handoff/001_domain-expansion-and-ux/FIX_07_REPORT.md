# FIX_07_REPORT — 정상 자연어 경로 복구·설치형 dev.8 검증·값 완전성 보정

작성일: 2026-10-14 · 역할: Executor · 판정: **R1~R3 보정 완료, dev.8 설치형 검증 완료, 실모델 왕복 잔여 변동성 기록**

기준: `FIX_07.md`(Reviewer, HEAD `5301737` 이후 작업 트리). FIX_06에서 인정된 password/read 정책/TTS secondary/저널/rename/조명·공조 회귀는 재작성하지 않고 유지했다.

---

## 1. 검증 명령과 결과

- `uv run pytest -q`: **114 passed**(FIX_07 회귀 +5), Starlette deprecation warning 1개(기존과 동일).
- `uv run ruff check addon/app tests scripts` 통과, `ruff format --check` 20 files, `node --check` 통과, `git diff --check` 통과.
- GitHub Checks(run `38489605884`, push `cb6a248`): test·arm-build **success**.
- 실기동: 프로젝트 전용 QEMU HAOS(Core 2026.10.1) — §4.

## 2. R1 — 정상 B/C 자연어 경로 복구 (안전 진단 먼저)

`scripts/probe`(임시 관측 래퍼)로 실제 모델의 단계별 선택·확신도를 비밀 없이 관찰한 결과와 조치:

| 관찰 | 원인 | 조치 |
| --- | --- | --- |
| calendar/weather `conflicting_actions` | query_state와 응답 조회가 독립 질문이라 모델이 함께 선택 | **단일 상호배타 선택으로 통합**: calendar/todo/weather/input_datetime은 `query_state`가 각 action choice 안에 들어가고 별도 query 속성 폐지(응답 서비스가 없는 weather sf=0 등은 일반 query로 폴백). 모델이 구조적으로 혼용 불가. |
| `condition_unit 0.53` 저확신 → 조건 거부 | 단위는 literal/센서 native에서 백엔드가 결정하는 보조 정보인데 선택 게이트에 걸림 | 단위 선택만 저확신 시 `none`(파생)으로 강등, source/operator/value는 0.6 게이트 유지. 단위 모호·충돌 거부는 `_evaluate_condition`의 `condition_unit_unspecified/conflict`가 계속 담당. |
| TTS `tts_output` cross-ref를 모델이 계속 none 선택 | 2-대상 참조 선택이 Decision-1에 부담 | 스피커 엔티티에 일반 yes/no 속성 **`broadcast_output`** 신설, tts target은 text_action만 선택하고 엔진이 정확히 1:1일 때만 speak action에 출력 ref를 결합(다중/0개면 `tts_output_ambiguous`/`tts_output_target_required`, 전송 0건). 관측상 침실↔Bedroom 지칭도 instructions 보강("불/전등은 light만", "'냉방' 명시 시 cool", "tts 방송≠재생")으로 해결. |
| climate 2도 실패 두 종류 | (a) 스코프에 거실 switch까지 포함 → verify가 정상 거부, (b) "명칭만으론 cool 추론 금지" 문구가 '냉방 24도'의 cool 선택을 억제 | action instructions를 구체화: 불/전등/조명=light만(switch 제외 명시), "'에어컨' 명칭만 추론 금지; '냉방' 명시 시 cool 선택". 재시도 probe: `거실불 꺼줘` verify 0.994, `거실 에어컨 냉방 24도` cool 0.85→verify 0.9996 실HA 전송 성공. |
| 검증 중간 실패(plan_not_verified) 잔여 | 모델 자체의 확률 변동(성공 사례와 동일 입력) | 임계값 인하 없음. 단발 결과로 보고(§4). |

- 정규식/top-K 후보 제거는 도입하지 않았고, 모든 대상 후보는 기존 허용 카탈로그 전체에서 의미 판단된다.
- fixture 명확화(허용된 테스트 VM 작업): 데모 calendar read-only 2개·중복 weather·미등록 mp 7개·demo sensor 다수·climate.ecobee를 **앱 정책(엔티티 제외)**으로 정리하고 tts/센서/에어컨/캘린더에 한글 registry 이름·영역을 부여(VM 한정, 재현 절차는 `docs/testing.md`에 반영). 운영 사용자 수동 매핑 요구 없음.

## 3. R2/R3 코드 보정

- **R3(시간 literal)**: `TIME_RE`가 `오전|오후|아침|저녁|점심|새벽|밤` 접두사를 같은 span으로 consuming(`오후 8:30`→20:30), `N시 M분`은 분을 span에 병합하되 **잘못된 분(75분)은 토큰 전체를 무효화**(20:00으로 잘아 쓴 후보 만들지 않음), `2028년 10월 20일` 명시 연도 보존·`2월 30일` 등 무효 날짜는 토큰 없음 → 요청 시 `datetime_value_required/invalid`. 경계 테스트: 오전 12시→00:00, 오후 12시→12:00, 12월 31일, 지남 월/일→다음 해. has_date+has_time helper는 `{"datetime": "YYYY-MM-DD HH:MM:00"}` 단일 결합(FIX_07 R4의 input_datetime 지시 포함). timezone 미확인 시 날짜·시간 쓰기/조회는 `timezone_unknown` 거부 유지.
- **R4(전원+속성)**: fan/humidifier/media_player에서 명시 `turn_on`을 속성 action과 **별건으로 순서 보존**(turn_on 먼저), `turn_off`+속성 상충은 계속 전송 전 거부. 이미 켜진 경우 no-op은 action별 `already_in_state`가 유지. `test_fix07_r4_*` 단위 + engine 회귀.
- **R1(구조)**: 통합으로 `RESPONSE_QUERY_PROPS` 단일 선택, `make_actions` 통합 query 경로의 민감/read 차단 유지. `tts_output` cross-ref는 엔진 결합 전용(direct make_actions 방어는 유지).

## 4. 실기동 (프로젝트 소유 VM, mock/실모델 구분)

`scripts/verify_live_bc.py` 3레이어(교체 커밋에 포함):

- **safety_negative/service_contract (scripted-mock 라벨 + 실제 HA)**: 9 assertions 전부 통과 — 달력 start/end 생성 후 `FHC 회의` read-back, get_events 실응답(`{"events":[...]}`) 표시("1개 일정…"), weather `get_forecasts_daily` 실응답·`response_contract=ok`, **TTS speak 페이로드 media_player_entity_id=media_player.bedroom**(secondary 라벨, living_room 하드코딩 없음), todo 동명 2건 → preflight `todo_item_ambiguous` 제어 0건, `input_datetime.fhc_wake`=**20:30:00** read-back, climate 목표 24 read-back.
- **e2e_model(실제 OpenRouter, cb6a248)**: Microsoft Decision-1 **6/8** 통과 — 조명 off 실전송(2등), typed 조건 false(전송 0건), TTS 지정 실전송, 일정/예보 실응답, todo 부재 거부, tts 모호 0건. 잔여 실패 2건(todo·climate)은 `plan_not_verified` **0전송 안전 거부**이며 같은 입력의 probe 재시도에서 각각 성공했음을 함께 기록(확률 변동). 임계값·후보 조작 없음. Jev 1.13 동일 fixture/기대값에서 **2/8**(모두 0건·보수 거부; B_climate 실전송 1건 성공) — 모델 간 차이로 보고.
- **R1 password live**: VM에 password `input_text` helper 존재 상태에서 catalog/모델 입력/query_results 비노출 + 0건(`.local/fix06-live-r1-password.json`, 이전 라운드).
- 증거: `.local/fix06-live-scripted.json`, `.local/fix06-live-microsoft_microsoft-decision-1.json`, `.local/fix06-live-typesafe_jev-1.13.json`(모델별 파일·케이스별 layer/executed/return된 모델 문자열 저장, 누적·덮어쓰기 없음).

## 5. 설치형 검증 (R2 승인 범위)

- 코드+문서 커밋 `cb6a248` → GitHub push → Checks success(test, arm-build) 확인.
- VM Supervisor `/store/reload` → `/addons/a1444ce0…/update`: **dev.6→dev.8** 설치·`state=started` (공식 `#dev` git 저장소 경로, 로컬 저장소 수술 없음).
- Ingress 관리자 세션: `api/status` version 0.2.0-dev.8·ha_ready·execution_ready → `거실불 꺼줘` POST/sent 2건 + HA 상태 read-back(해당 2등만 off, kitchen/office/entrance 유지).
- `PUT /api/policy`(read_domains + entity read_enabled) 저장·조회 확인 → **addon restart 후 정책·버전 보존**. `GET /api/history/export` 200/zip, requests.jsonl 파싱, 기본 다운로드에 명령 원문 없음, 토큰 조각 없음 검증.
- 잔여 테스트 정책은 컨테이너 store에서 기본값으로 복원(검증 흔적 정리).
- `.local/fix07-install-verification.json`에 원문 비밀 없이 결과 기록.

## 6. FIX_02 B/C 표 대비 상태

- B: 구현·단위·실HA(모의 선택) 검증 완료. camera는 discovery 서비스 집합만 노출. media_player group join·임의 URL·script 생성 등 제외 유지(기존 표대로).
- C: sensor·weather(지원 예보)·calendar(목록/명시 생성)·todo(목록/추가/UID 대상 상태 변경·삭제)·조건 model_typed·input_datetime 시간/날짜 — **실HA 계약 + 실모델 왕복 모두 확보**(위 4장 구분 참조). person/device_tracker/zone·calendar·todo 읽기는 opt-in 유지.
- notify(도메인만 가능, send_message 실전송 왕복 미검증)·time/date 도메인 미지원·image/event/update 조회만: 문서·CHANGELOG와 동일하게 미완/보류로 유지.

## 7. 남은 리스크

1. 실모델 변동성: 동일 입력의 `plan_not_verified`(0건)가 간헐 — probe 재시도에서 성공하므로 안전·성능 분리 기록. 광범위 한국어 정확도 보증은 없음(요구도 안 함).
2. Jev 비교군이 정상 문장을 대량 unsupported로 거부 — 기본 모델(Microsoft) 대비 비교 기록일 뿐 배포 기준으로 삼지 않음.
3. `main`(안정) 릴리스·운영 HA 자동 업데이트는 본 라운드에서 미수행(별도 승인 대 기 유지).
4. dev.8은 VM에만 설치됨. 재사용 fixture baseline에는 dev.6 디스크 상태가 갱신되지 않았고, 데모 데이터·todo 항목은 매 run 재시드로 대응(VM stopped 유지, 운영 VM 미변경).

## 8. 최종 상태

- 커밋 1: `cb6a248` (FIX_05~07 구현·테스트·문서·verify_live_bc + FIX_02~06_REPORT). 커밋 2: dev.8 설치형 검증 문서(`docs/verification.md` 신규 섹션) + `FIX_07_REPORT.md`.
- VM: 검증 종료 후 ACPI 정상 종료(stopped), `test-resources.json` 갱신(dev.8 설치·검증일·마지막 테스트 앱 커밋). `.local` 파일은 Git 제외. 운영 VM/방화벽/타 서비스 미변경.
