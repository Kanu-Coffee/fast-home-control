# FIX_04 — FIX_03 구현 재리뷰: 조건 안전성 및 B/C 완료 범위

작성일: 2026-10-13 · 역할: Reviewer · 판정: **수정 필요**

## 검토 기준과 검증 결과

기준 HEAD `219d03e`(dev), 그 이후 작업 트리의 제품/시험 파일 16개와 미추적 FIX_02_REPORT/FIX_03_REPORT를 포함해 검토했다. PLAN, REPORT, FIX_01~03 및 해당 보고서의 요구와 현재 구현/증거를 대조했다. 이번 Reviewer는 제품 코드, VM, 설정, Main, 릴리스를 변경하지 않았다.

- `uv run pytest -q`: **81 passed**, Starlette deprecation warning 1개.
- `uv run ruff check addon/app tests scripts`: 통과.
- `uv run ruff format --check addon/app tests scripts`: **실패**, `scripts/evaluate_stage_a.py:164` 1개 파일 formatting 필요. 보고서의 format 통과 주장과 현재 작업 트리가 다르다.
- `node --check addon/app/fhc/static/app.js`, `git diff --check`: 통과.
- 합성 FakeHA/ScriptedProvider + 임시 Store로 아래 경로를 재현했다. 이는 backend 방어의 시험이며 실제 모델이 해당 문장을 잘못 승인했다는 증거로 해석하지 않는다.
- `.local/stage-a-evaluation-{model}.json` 두 파일의 15개 결과/반환 모델/시간/호출 수를 읽어 보고서와 대조했다. 비밀 파일이나 API 키를 출력하지 않았다. 신규 API 호출/HAOS 기동은 하지 않았다.

해결된 항목은 유지한다: SecretStr 다운로드 오류, SQL 필터 선적용 및 limit 검증, 기본 export의 기존 합성 상태 marker 제거, automation skip_condition=false/stop_actions=true, select enum 전체 보존, 사용자 query/조건 false 결과 표시, 민감 cover 기본 차단, input_text password 쓰기 거부, query/메시지 shortcut 필터.

**FIX_03_REPORT의 “모든 요구사항 보정 완료” 및 B/C 실기동 검증 완료 판정은 승인하지 않는다.** 아래는 기존 요구의 잔여/재현 결함이며 새 기능 범위를 임의 추가한 것이 아니다. 다음 Executor는 안전 보정과 B/C 구현을 이어가고, 단순 보고서 수정으로 끝내지 않는다.

## R1 [P1] 정규식 조건 감지를 벗어나면 여전히 무조건 실행한다

위치: `engine.py:31-176`, `:398-409`.

COND_INDICATOR에 걸리지 않으면 None을 반환하고 그대로 실행한다. 조건 source/comparator/literal을 모델이 선택하는 typed 계획은 구현되지 않았다. 이름/영역 부분 문자열로 센서를 선택하는 로컬 의미 파서도 그대로다. 정규식을 더 늘리는 방식은 사용자 요구와 FIX_03 R1을 충족하지 않는다.

재현(기본 FakeHA, ScriptedProvider가 천장등 turn_off와 supported/exact를 승인):

| 원문 | 현재 결과 |
| --- | --- |
| `거실 온도가 28도보다 높다면 거실불 꺼줘` | succeeded, condition_result 없음, turn_off 1건 |
| `만약 거실 온도가 높다면 거실불 꺼줘` | succeeded, condition_result 없음, turn_off 1건 |
| `거실 온도가 28도 이상이 아니면 거실불 꺼줘` (거실 온도 29°C) | condition_result=True, turn_off 1건. 부정 무시 |
| `거실 온도가 28도 이상이고 습도가 70% 이상이면 거실불 꺼줘` (온도 29°C, 습도 센서 없음) | 첫 조건만 평가하여 True, turn_off 1건 |

센서 unit='K', state='29'에 `28도 이상이면`을 평가하면 True를 반환하고 observed_unit='°C'로 기록한다. 지원하지 않는 단위를 거부하지 않고 잘못된 단위로 표기한다.

수정 및 수용 기준:

1. 모델 단계에서 conditional 여부 및 허용 source/ref, 속성, comparator, literal ID/단위를 선택하고, 조건을 포함한 전체 계획을 verification에 전달한다. source도 정책/identity/freshness 검증 대상에 포함한다. 로컬 정규식은 수치/문자 span 추출 보조로 제한한다.
2. 조건 없음과 조건 해석 실패를 별도 계약으로 표현한다. 조건이 포함된 요청을 완전한 supported typed 계획으로 표현하지 못하면 전송 0건 거부한다. 부정/복합 조건은 지원 구현 전까지 전송 0건이다. 모델 exact=true가 backend 검증을 우회하지 못하게 한다.
3. 알려진 비교 가능한 단위만 허용/변환한다. 단위 없음/불일치/K 등 미지원은 판단 불가로 거부한다. `도`의 단위도 HA 환경 및 명시 단위에 맞춰 결정하고 고정 °C로 가정하지 않는다.
4. fresh_states 캐시에 있다는 이유로 오래된 조건 관측을 재사용하지 않는다. 실행 직전 source 값을 확인하고 사용 시각·원래 값/단위·변환 값·결과를 진단에 기록한다.
5. 위 문장들, aliases/일상 동의어, 제외/동명/누락 센서, unknown/unavailable, 단위, 상태 변화 회귀를 추가한다. 실제 모델을 붙인 테스트도 별도로 수행한다. 정규식 몇 개와 scripted 정상 1개만으로 완료 판정하지 않는다.

## R2 [P2] 제어 도메인의 상태 조회가 실행 파이프라인에 연결되지 않았다

위치: `actions.py:430-436`, `engine.py:256`, `main.py:226-267`.

options_for에 추가한 제어 도메인 query는 text 정규식에 의존한다. 그런데 Engine은 `options_for(entity, values)`로 호출하여 text를 전달하지 않는다. vacuum에 `청소기 상태 어때`를 주어도 실제 파이프라인의 choices는 vacuum_action뿐이다. 직접 options_for(..., text='청소기 상태 어때')를 호출해야 query가 나타난다. 호출 인자 추가만으로는 동의어 누락 문제가 남는다.

수정: 정책상 조회 가능한 엔티티의 query 선택지는 표현과 무관하게 제공하고 의미 선택을 모델에 맡긴다. read/query와 write/control의 **허용 정책**도 분리한다. CONTROL_DOMAINS/QUERY_DOMAINS 상수 분리는 정책 분리가 아니다. domain/개별 entity master 우회 방지를 유지한다. API counts도 실제 기능과 권한에서 계산한다.

검증: `청소기 상태 어때`, `청소기 지금 뭐 해`, `선풍기 켜져 있어?`가 동일한 query 후보를 받고 backend fresh 값으로 응답하며 물리 서비스는 0건. 조회만 허용/쓰기 금지한 정책에서 query 성공·write 차단을 시험한다.

## R3 [P1] 기능·값·복수 속성 검증이 부분 보정에 그쳤다

위치: `actions.py:151-170`, `:274-390`, `:555-630`, `:698-728`, `:734-765`.

- cover와 media_player에 `flags & flag or flags == 0`가 남아 feature=0을 모든 지원으로 승격한다. cover supported_features=0, 도메인 open/close/set_position 서비스가 있으면 cover_action/position choices가 제공됨을 재현했다.
- fan/media power는 도메인 서비스만 확인한다. 실제 해당 Core의 엔티티별 feature 규약을 적용하고 legacy 호환이 필요하면 공식 근거에 한정한다.
- input_number min=0,max=10,step=2에서 `숫자를 3으로`를 scripted 선택하면 **set_value(value=3.0)를 전송**한다. 단위/step을 읽어도 후보 및 preflight 값 검증에 반영하지 않았다.
- fan percentage=50 + oscillate_on 선택 시 `selected`에는 두 속성이 있지만 반환 action은 set_percentage 하나다. humidifier humidity+mode, media play+volume/source 등도 elif 우선순위로 나머지 요청을 버린다. turn_off 충돌만 고쳐 전체 문제를 해결한 것은 아니다.
- script mode=restart, state=on에서 명시 실행을 요청하면 already_in_state로 처리하고 **호출 0건**이다. script는 on 상태여도 restart/queued semantics에 따라 실행 요청이 의미 있으므로 일반 light no-op 규칙을 적용할 수 없다.

수정: feature/enum/range/step/unit에서 생성한 동일한 capability 계약을 choices와 preflight에 적용한다. 모델 선택을 그대로 신뢰하지 말고 backend에서 재검증한다. 수치를 int로 조용히 절삭하지 않는다. 복수 속성은 공식 서비스가 함께 지원하면 묶고, 그렇지 않으면 검증된 복수 action으로 구성한다. 사용자가 요청하지 않은 속성 누락·추가가 있으면 전송 전에 거부한다. script/scene 등 비멱등 효과의 no-op도 도메인별로 검토한다. supported_counts는 domain 이름 등록 여부가 아닌 실제 제공 가능한 동작으로 계산한다.

## R4 [P2] 본문 쓰기 및 진단 다운로드가 기존 요구를 일부 놓쳤다

위치: `actions.py:462-473`, `:654-670`, `main.py:477-602`, `provider.py`.

- extract_message는 따옴표 첫 구간 또는 몇 개 정규식만 읽고 실패하면 전체 명령문을 반환한다. 보고서의 `입력란에 오늘 저녁 7시 회의라고 입력해줘` → `오늘 저녁 7시 회의` 주장은 재현되지 않는다. 실제 반환은 **전체 지시문**이다. `거실 알림에 안녕 보내줘`도 전체 지시문을 반환한다.
- tts.speak에는 여전히 media_player_entity_id가 없어 실제 서비스 필수 인자가 빠진다. notify legacy service-only discovery도 없다.
- export가 model_trace/decisions/scope_scores/condition_evaluation을 제거하여 returned_model, 실패 phase의 상세 관측, literal 선택 및 조건 값 근거를 분석할 수 없다. 이번 제브 비교에서 실제 반환 snapshot은 중요한 정보다. 민감 원본을 다시 통째로 넣지 말고 해당 필드를 안전한 typed 진단 DTO로 포함한다. provider 실패 trace 자체의 누락도 아직 수정하지 않았다.
- include_text=true에서 query_results.state는 무조건 원문 문자열을 출력한다. 기존 input_text.pin query 기록에 합성 PRIVATE_PASSWORD_MARKER를 넣으면 raw export에 남는다(기본 export에서는 제거됨). 원문 포함 선택도 password-mode 값/개인 상태 전체 공개 허가는 아니다. 과거 기록을 포함해 민감 도메인/필드를 검사할 계약이 필요하다.

수정/검증: 모델이 원문 본문 span과 대상들을 선택하게 하고 backend에서 범위·원문 일치·최소/최대 길이·민감 모드를 검증한다. 미해석 시 전체 명령 fallback을 금지한다. 복수 문구/복수 대상/따옴표가 대상명에도 쓰이는 사례를 추가한다. tts 엔진과 허용 media target을 실제 서비스 스키마에 맞춰 연결한다. 로그는 original 포함 여부와 별개로 비밀/민감 필드를 보호하고 분석에 필요한 모델/조건/실패 근거를 보존한다.

공식 근거: [TTS speak](https://www.home-assistant.io/integrations/tts/), [Core 2026.10.1 Fan](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/fan/__init__.py). 실행 시 지원 Core의 해당 서비스 등록 및 feature enum을 확인한다.

## R5 [P2] B/C 전체 완료 및 모델 속도 비교 결론을 증거에 맞춰야 한다

이전 FIX_03 R7에서 요구한 다음이 여전히 없거나 연결되지 않았다:

- vacuum fan_speed는 make_action 분기만 있고 options_for의 vacuum_speed 선택지가 없다. fan direction, select next/previous/first/last, counter set_value, light effect, climate fan/preset/swing도 없다.
- weather.get_forecasts, calendar.get_events/create_event, todo.get_items/명시 CRUD, input_datetime/time 제한 쓰기, legacy notify discovery, tts target, camera 제어, update 버전/현재 정보 등 typed 속성 조회가 없다. input_datetime을 query_only로 분류한 것은 요청된 쓰기 구현을 완료한 것이 아니다.
- [Calendar](https://www.home-assistant.io/integrations/calendar/) 및 [Todo](https://www.home-assistant.io/integrations/todo/)의 실제 응답 데이터를 읽지 않고 entity state만 반환하는 것으로 일정/할일 조회를 대체할 수 없다.
- B/C fixture 기반 실제 실행 및 typed 조건/응답 서비스/문구 쓰기/혼합 명령의 HAOS 증거가 보고서에 없다. 설치 상태 및 export 성공과 A의 조명·공조 평가를 B/C 완료 증거로 확대하지 않는다. 보고서의 /api/status 예시는 실제 코드의 필드와 다르며 /api/domains에도 query_only boolean이 아니라 status 문자열을 반환한다. 실제 관측 데이터를 명확히 구분해 새 보고서에 기록한다.

모델 비교 파일에서 직접 확인한 내용:

| 항목 | Microsoft Decision-1 | TypeSafe Jev 1.13 |
| --- | --- | --- |
| 전체 기대 결과 일치 | 14/15 | 6/15 |
| 유효 제어 성공 | 9/10 | 1/10 |
| 음성 사례 안전 거부 | 5/5 | 5/5 |
| returned_model | microsoft/microsoft-decision-1-20261009 | typesafe/jev-1.13-20260917 |
| 전체 평균 total ms | 3428.9 | 2029.0 |
| 실제 평균 HTTP calls | 3.47 | 3.27 |

성공/거부 분포가 다르므로 전체 평균 40.8% 차이는 **완료된 제어의 속도 우위**를 증명하지 않는다. 동일 성공 사례의 단계별/첫 전송/HA ACK 및 실패·거부 시간은 분리한다. 표본이 작으므로 일반 정확도/캘리브레이션 보장이나 사고율로 확대하지 않는다. 현재 Microsoft 기본 유지 및 두 모델 검증 지속은 합리적이다. 실패를 줄이기 위해 안전 임계값을 임의로 낮추지 않는다.

평가 harness 자체도 보정한다: reset_ha_case가 예외를 pass로 삼켜 reset 실패를 숨긴다. 실제 초기 상태를 fresh 확인하고 실패 시 해당 case를 setup_failed로 분리한다. 상대 밝기 expected={}는 실제 변화량을 검증하지 않아 dim no-op도 통과할 수 있다. 초기 brightness 및 기대 변화를 명시한다. wrong extra dispatch는 result action 목록뿐 아니라 실제 테스트 HA 서비스 관측으로 확인한다. 이번 15개는 A corpus이므로 B/C 및 조건/본문 사례를 추가하고 fixture/정책/prompt/code 버전을 기록한다.

## 다음 Executor의 진행/인수 기준

1. R1 안전성 → R2/R3 공통 실행 계약 → 미완 B/C 응답 조회·제한 쓰기 및 R4 → 실제 VM 묶음 시험을 진행한다. 보고서만 보정하거나 정규식 몇 개 추가하고 종료하지 않는다. 제품 기능 개발을 계속할 수 있으며 Reviewer 재승인을 개발 선행 조건으로 요구하지 않는다.
2. FIX_02 B/C 표를 동작별 구현/검증/실제 미지원/보류 표로 관리한다. 계획상 보류(ai_task/conversation/업데이트 설치/장기 예약)는 유지하되 필수 B/C를 임의 보류로 바꾸지 않는다. 실제 blocker가 있으면 증거를 남기고 다른 독립 기능을 계속한다.
3. 본 문서의 repro 및 기존 F1/F2/다운로드/정책/조명·공조 회귀를 통과시키고 실제 HAOS에서 B/C를 검증한다. 두 허용 OpenRouter 모델을 동일한 fixture/정답으로 시험한다. Azure mock/live를 구분한다. 중간 빌드의 사용자 운영 시험을 요청하지 않는다. 엄격한 초 단위 성능 합격선은 추가하지 않는다.
4. VM 소유·격리 및 설치된 Dev 버전을 먼저 확인한다. dev.7 이후 실제 업데이트 시험은 더 높은 버전을 사용하고 버전 표기를 맞춘다. Main/안정 릴리스 승인과 Dev 개발 권한을 혼동하지 않는다.
5. 다음 산출물은 **FIX_04_REPORT.md**다. 기존 PLAN/FIX/REPORT를 덮어쓰지 않는다. 해결/미해결, 실제 명령·결과, mock/live/HAOS/browser, 자원 정리 및 Git 상태를 구분한다. 현재 코드에 없는 동작·테스트명·응답 예시를 완료 증거로 쓰지 않는다.
