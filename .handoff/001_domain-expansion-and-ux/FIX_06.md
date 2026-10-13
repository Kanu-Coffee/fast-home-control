# FIX_06 — FIX_05 보정 리뷰: 실제 달력 계약·계획 사전검증·조건 불확실성

작성일: 2026-10-14 · 역할: Reviewer · 판정: **수정 필요**

## 1. 검토 대상과 진전

기준 HEAD는 dev `5bc123f`. 이후 작업 트리 변경 및 FIX_05_REPORT, 신규 scripts/verify_fix05_live.py, `.local/fix05-bc-live*.json`의 비밀 없는 결과 필드를 검토했다. PLAN과 기존 FIX/보고서 요구를 이어서 적용한다. Reviewer는 제품 코드·설정·VM·Main·릴리스를 변경하지 않았다.

재실행: `uv run pytest -q` **101 passed**, Starlette deprecation warning 1개. Ruff check/format(20 files), JS 구문, git diff --check 통과. 아래 재현은 임시 Store/FakeHA/ScriptedProvider 및 직접 payload 생성에 의한 backend 검증이다. 실제 모델이 해당 오실행을 했다는 주장과 구별한다. 이번 리뷰에서는 신규 API 호출/VM 기동을 하지 않았다.

이전 주요 결함의 보정은 인정한다: password 카탈로그/백엔드 보호, read 정책/API/rename 보존 및 개인 도메인 opt-in, TTS 고정 fallback 삭제와 secondary target 정책 검사, 제어 도메인 query 및 response query 권한 구분, provider trace, typed 조건 source/operator/literal 선택, 일반 장면/벽면 이름 처리, todo 실제 UID 조회. 이 부분을 재작성하지 말고 유지한다.

이번 보고서는 호스트 Engine→실제 HAOS 경로, addon 미설치, 모델 실패/미검증 항목을 구분한 점이 개선됐다. 그러나 달력의 실제 응답/생성 계약과 아래 실행 결함이 남아 **B/C 완료 및 설치형 Dev 검증 완료로 판정할 수 없다**.

## 2. R1 [P2] 실제 달력에 일정이 있어도 “일정이 없습니다”를 반환한다

위치: `engine.py:format_response`, `_unwrap_response`; `tests/test_corrections.py:test_fix05_r2_readonly_calendar_get_events_end_to_end`.

HA calendar.get_events의 entity payload는 `{"events": [...]}`이다. format_response는 val이 list일 때만 events로 사용하므로 실제 dict를 빈 일정으로 취급한다. 이벤트 start/end도 HA 서비스는 ISO 문자열로 내보내는데 현재 코드는 Google calendar형 `{date/dateTime}` dict를 가정한다.

재현: FakeHA response를 실제 형태인 `{"response": {"calendar.c": {"events": [{"summary": "실제 회의", "start": "2026-10-15T09:00:00+09:00", "end": "2026-10-15T10:00:00+09:00"}]}}}`로 구성하고 Engine 실행 → succeeded, query_result=**“일정이 없습니다.”**, 저장 response에는 회의 1개가 있음.

기존 단위 테스트는 entity payload에 이벤트 list를 직접 넣어 잘못된 계약을 정상으로 검증한다. [Core 2026.10.1 calendar/services.py](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/calendar/services.py)의 async_get_events_service 응답에 맞춰 fixture와 파서를 수정한다. 실제 일정이 있는/없는 목록, 종일/시간 일정, HA timezone, malformed response를 구별한다. 계약 오류를 실제 빈 목록처럼 성공 처리하지 않는다. 실제 테스트 HAOS에 고정 일정을 넣고 화면에 제목/시각이 표시되는지 검증한다.

## 3. R2 [P2] 시간 일정 생성이 잘못된 서비스 필드와 임의 길이를 사용한다

위치: `actions.py:1136-1148`, temporal_tokens 및 input_datetime binding; calendar create 단위 테스트.

시간 지정 create_event payload가 `start_date_time` + **duration='01:00:00'**이다. Core create_event는 start_date_time/end_date_time 쌍 또는 날짜 쌍/in을 요구하며 duration은 get_events의 조회 필드다. 현재 단위 테스트는 이 잘못된 duration을 기대값으로 고정했다.

재현: `내 달력에 내일 9시부터 11시까지 "회의"라고 입력해줘` → summary='회의', start_date_time=내일09:00, duration='01:00:00'. 원문의 종료 11시는 선택할 경로가 없고 1시간을 임의 생성한다. HA 실제 스키마를 만족하지 않는다.

추가 재현: `기상을 오후 8시 30분으로` → temporal_tokens는 '8시'만 08:00 토큰으로 만들고, 해당 토큰 선택 시 set_datetime(time='08:00:00'). 오후/분을 버려 실제 요청 값 20:30을 표현할 수 없다. 날짜+시간 helper도 단일 datetime_value 선택만 있어 두 요소를 함께 설정하는 경로가 부족하다.

수정/검증:

- 모델이 원문 시작·종료/명시 duration에 대응하는 typed token을 선택하고 backend가 실제 end_date_time을 계산한다. 종료가 없으면 임의 1시간을 만들지 말고 허용 계약에 따라 거부한다. [Core calendar 서비스 스키마](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/calendar/services.py)를 기준으로 검증한다.
- 한국어 오전/오후·분·명시 날짜 및 has_date/has_time 조합을 원문 span과 연결한다. 미지원 표현은 의미를 잘라 바꿔 쓰지 말고 전송 전에 거부한다. timezone 모르면 시간 기반 쓰기를 UTC로 조용히 가정하지 않는다.
- [input_datetime 공식 규약](https://www.home-assistant.io/integrations/input_datetime/)에 맞는 실제 값으로 테스트한다. 테스트 시각을 고정한다. 현재 내일 기대값 '2026-10-15'와 실제 datetime.now()를 결합한 테스트는 다음 날짜에 깨질 수 있다.
- 실제 HAOS에 테스트 helper/local calendar를 추가하여 시간·날짜·datetime 값과 생성된 일정의 시작/끝을 read-back한다. 운영 사용자의 YAML/수동 매핑을 요구하지 않는다.

## 4. R3 [P1] todo 대상 모호성을 첫 제어 이후에 발견한다

위치: `engine.py:_execute_plan`, `_resolve_todo_item`, preflight loop.

todo UID 해석이 각 action 실행 직전에 수행되어, 앞 action은 이미 전송될 수 있다. 이는 모든 대상·매개변수/미지원 절을 첫 제어 전에 검증한다는 기존 계약을 충족하지 않는다.

재현: todo 목록에 summary='우유'인 UID a/b 두 항목. `거실불 끄고 장보기에서 "우유" 완료로 바꿔줘`를 scripted 계획으로 실행 → **partial / todo_item_ambiguous**, light.turn_off는 이미 **1건 전송**. 대상 모호성을 알아내기 위한 조회는 실행 전에도 가능하다.

수정/검증:

- 모든 todo update/remove UID 및 response 기반 참조를 첫 write 전에 preflight에서 해석한다. 같은 요청의 여러 항목도 서로 검증하고, any ambiguous/not_found이면 제어 0건으로 거부한다. 읽기 서비스 호출과 물리/쓰기 전송은 구별해 기록한다.
- UID를 해석한 뒤에도 write 직전 정책/identity/HA catalog version을 재검사한다. 현재 loop 진입 검사 뒤 get_items await 사이에 환경이 바뀌면 검사 없이 다음 write가 진행된다.
- 앞뒤 action 순서를 바꾼 혼합 도메인 명령, 중복/삭제 항목, get_items 동안 registry/policy 변경, 이후 네트워크 실패를 시험한다. 실행 후 통신 실패의 partial/uncertain와 실행 전부터 발견 가능한 모호성 거부를 구분한다.

## 5. R4 [P1] 조건 여부의 불확실성을 조건 없음으로 바꾼다

위치: `engine.py:CONDITION_INSTRUCTIONS`, scope conditional threshold, `_evaluate_condition` 단위 처리.

typed 선택으로 전환한 방향은 맞다. 하지만 `conditional = noul(...) >= 0.7`은 조건 존재 확률 0.69도 조건 없음으로 처리한다. 이후 조건 질문/검증 정보가 없고, exact가 true이면 무조건 실행한다.

재현: ScriptedProvider의 scope conditional만 **0.69**, supported/exact는 기존 승인 값. 센서 없는 `거실 온도가 28도 이상이면 거실불 꺼줘` → **succeeded, condition_result 없음, turn_off 1건**. 이는 현재 모델에서 관측한 오실행이 아니라 불확실한 분류 결과에 대한 backend 계약 결함이다.

또한 CONDITION_INSTRUCTIONS는 부정·복합·기준 없는 **조건을 false**로 지시하여 “조건 없음”과 “미지원 조건”을 합친다. 후속 condition_none 경로에는 별도의 reject category가 없다. 유효성 질문 한 개의 안전 판단에만 기대는 계약이다.

단위도 source에 unit이 없으면 °C/HA unit을 추정하여 비교한다. unit 없는 temperature sensor state='29', 조건 literal28℃/gt → **True, sensor_unit=None인데 observed_unit='°C'**로 기록됨을 재현했다. 이전 요구의 단위 모호 시 거부와 다르다. model-selected unit이 원문의 명시 literal 단위를 덮어쓰는 경로도 backend에서 확인해야 한다.

수정/검증:

- 조건 없음/지원 조건/미지원·모호한 조건을 별개 typed 선택으로 모델이 반환하게 하거나 동등하게 명확한 계약을 사용한다. 중간 확률·none/불확실한 source/operator는 무조건 실행으로 내려가지 않고 안전하게 거부한다. 로컬 문장 정규식으로 되돌리지 않는다.
- 단위 없는/불명확한 source는 거부한다. 원문의 명시 단위와 선택 단위의 일치, source의 native 단위, literal ID/값/단위/span을 backend에서 검증한다. 최종 verification에도 해석 가능한 실제 비교 수치·단위를 제공한다.
- 확실한 비조건 명령의 기존 성능/동의어를 유지하며 unsupported/ambiguous 조건, 분류 임계값 경계, 단위 누락·충돌, 제외 source, true/false/unknown과 혼합 명령을 회귀 검증한다. 부정·복합 지원을 새로 요구하는 것이 아니라 미지원 조건을 조건 없음과 구별하는 보정이다.

## 6. R5 [P2] 계약 8/8은 실행되지 않은 기능의 서비스 검증을 증명하지 않는다

확인한 두 live 파일은 보고서 수치와 일치한다: Microsoft roundtrip **4/8**, Jev **1/8**. Microsoft 4개는 조건 false, TTS 모호 거부, todo add/update이고, Jev 1개는 모호 거부다. TTS 지정·날씨·달력은 양 모델 모두 action 없이 거부됐다.

현재 verify_fix05_live.py의 계약 체크 다수는 `all(... for a in actions if ...)`라 action=[]이면 True다. 이런 시험은 “이번 요청에서 잘못된 전송을 관측하지 않았다”는 근거이며 실제 TTS/달력/날씨 schema·응답 처리가 성공했다는 근거가 아니다. 일부 roundtrip도 sent/최종 값을 확인하지 않고 제안 action 존재만 검사한다. todo read-back을 기록하더라도 assertion과 연결되지 않은 부분이 있다.

수정/검증:

- safety-negative(전송 0건), 실제 service-contract(필수 서비스 실행 및 schema/응답 일치), end-to-end(real model 선택부터 효과까지)를 별도 상태로 기록한다. 서비스가 실행되지 않으면 contract는 **not_exercised**, pass로 계산하지 않는다. expected action 종류/대상/매개변수/전송 status와 read-back을 assert한다.
- 실제 모델이 demo 대상 모호성으로 거부하면 테스트 fixture의 이름/별칭/영역을 명확하게 한다. 기능 확인을 위해 **scripted 선택 + 실제 HA 서비스** 시험을 별도로 실행할 수 있으며 모의 모델임을 표시한다. 실제 모델 결과를 숨기거나 안전 임계값을 낮추지 않는다.
- calendar 생성/목록, input_datetime 값, TTS 실제 출력 target 호출, weather 응답, todo 삭제/동명 및 B 복수 속성을 실제 HAOS로 확인한다. VM에 helper가 없는 것은 사용자 입력 blocker가 아니므로 소유 테스트 fixture에 추가하고 진행한다.
- 두 모델의 동일 fixture 초기화·고정 정답·코드/프롬프트/반환 모델 버전을 유지한다. 결과 파일을 model별로 저장하고 덮어쓰기·케이스 간 상태 누적을 방지한다. 101개 테스트 통과를 전체 한국어 정확도나 B/C 실기동 완료로 확대하지 않는다.
- dev.8은 아직 설치되지 않았다는 보고를 유지한다. 실제 addon 설치/업데이트와 Ingress/관리자 읽기 토글/로그 다운로드까지 확인한 뒤 설치형 검증으로 표시한다. 설치된 버전보다 높게 올려 시험하고 Main/안정 릴리스는 별도 승인 전까지 건드리지 않는다.

## 7. 다음 실행 및 보고

다음 산출물은 **FIX_06_REPORT.md**다. 기존 PLAN/FIX/REPORT는 보존한다. R1~R4 보정과 R5의 실제 시험을 연결해 진행한다. 현재 모호성/응답 처리 문제를 해결하기 위한 개발을 사용자 재승인의 선행 조건으로 만들지 않는다.

이전 민감 상태/read 정책/TTS target/저널/rename/조명·공조 회귀를 유지하고 실제 기능별 완료/미구현/미검증을 구분한다. 아직 남은 legacy notify/time 등 FIX_02 B/C 표와 차이도 정직하게 기록한다. 이 리뷰는 모든 모델의 모든 정상 문장 성공이나 특정 초 이내 처리를 새 합격선으로 요구하지 않는다. **속도는 측정하되 엄격한 시간 기준으로 막지 않으며**, 핵심 기능이 실제 실행 가능한 MVP/Dev를 만드는 방향을 유지한다.

B/C 묶음 시험 전 사용자 운영 테스트를 요청하지 않는다. 프로젝트 소유 VM의 fixture·설치·자원 정리를 자율적으로 진행한다. 리뷰 문서 작성과 제품 수정/실기동 증거를 구분하고 안전 거부를 기능 성공으로 집계하지 않는다.
