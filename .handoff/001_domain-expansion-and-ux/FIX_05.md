# FIX_05 — 권한 보존·민감 상태·실제 B/C 서비스 계약 재리뷰

작성일: 2026-10-13 · 역할: Reviewer · 판정: **수정 필요, B/C 완료 판정 보류**

## 1. 대상과 확인 결과

기준 HEAD는 dev `3b1b748`이다. 이후 작업 트리의 제품/시험 파일 17개 및 미추적 FIX_02~04_REPORT를 포함해 검토했다. PLAN, REPORT, 기존 FIX/보고서의 요구를 현재 구현과 대조했다. 이번 Reviewer는 제품 코드/운영 설정/VM/Main/릴리스를 변경하지 않았다.

재실행 결과:

- `uv run pytest -q`: **86 passed**, Starlette deprecation warning 1개.
- Ruff check 및 format check: 통과(19 files). 이전 formatting 실패는 해결됐다.
- `node --check addon/app/fhc/static/app.js`, `git diff --check`: 통과.
- 임시 Store + FakeHA/ScriptedProvider 및 직접 action 생성/endpoint 함수 호출로 아래 결함을 재현했다. 이는 backend 계약의 시험이며 실제 모델이 해당 요청을 잘못 승인했다는 주장이 아니다. 합성 privacy marker만 사용했다.
- 공식 HA Core 2026.10.1 서비스 소스와 생성 payload를 대조했다. 이번 리뷰에서 신규 모델 API 호출/HAOS 기동은 하지 않았다.

유지할 개선: 제어 도메인의 query 후보가 표현과 무관하게 제공됨, number step 검사, fan 복수 속성 action 구성, script 재실행 no-op 보정, 실패 provider trace 및 진단 DTO 확장, 이전 API 키/export/automation/enum 보정.

그러나 FIX_04_REPORT의 “보정 완료”, “B/C 도메인 완료”는 아래 구현 결함과 실기동 공백 때문에 승인할 수 없다. 다음 Executor는 본 문서를 수행하고 **FIX_05_REPORT.md**를 새로 작성한다. 기존 문서와 보고서는 역사로 보존한다.

## 2. R1 [P1] password 상태가 query 경로와 모델 입력으로 노출된다

위치: `actions.py:148-160`, `:535-539`, `:630` 부근 query 조기 반환, `:878-880`; `engine.py` details/state 및 query_result; `main.py` export is_sensitive.

password-mode input_text의 text_action은 제외했지만 query_state는 제공한다. make_actions의 query 조기 반환은 password 쓰기 보호를 건너뛰고 validate_fresh도 query를 바로 허용한다.

재현: input_text.note, friendly_name='기록', mode='password', state='PRIVATE_PASSWORD_MARKER', input_text 도메인 허용. ScriptedProvider가 query_state를 선택한 `기록 값 알려줘` → **succeeded**, query_results.state에 marker 원문 반환. 관련 group이 scope에 포함되면 action 단계 details에 entity.state를 넣으므로 실제 선택 전에도 password 값이 외부 모델 입력에 포함될 수 있다.

또한 export는 mode가 아니라 entity_id에 password/pin/token/secret 문자열이 있는지를 검사한다. 동일 input_text.note의 과거 query 기록을 include_text=true로 다운로드하면 marker가 남는다. 이름이 pin인 테스트만 통과한 것으로 민감 모드 보호가 검증된 것은 아니다.

수정/검증:

- 민감 모드/도메인에 대한 read/write/모델 노출/export 계약을 먼저 정한다. password input_text는 이번 범위에서 양쪽 모두 제외하고 query/action 계획 및 실제 디스패치 전에 backend에서도 검증한다. 이름에 비밀 단어가 있는지로 보안 정책을 결정하지 않는다.
- query 이외에도 details/state, condition source, diagnostic/export, shortcut 등 모든 경로를 검사한다. 과거 이력은 안전성 분류가 없거나 엔티티가 삭제됐으면 보수적으로 제외한다.
- 일반 이름/별칭/renamed ID의 password fixture로 모델 입력과 public result 및 default/raw export 전부에 marker가 없는지 시험한다. 현재 설정의 알려진 API 키 치환은 추가 방어로 유지한다.

## 3. R2 [P1] read 정책이 우회되거나 정상 저장/rename 시 사라진다

위치: `store.py:20-57`, `:120-185`; `main.py:34-46`, `:335-367`; `actions.py:148-160`, `:535-539`.

재현:

1. domains.light=True, read_domains.light=False. Catalog의 entity.read_allowed는 False인데 options_for에 query가 있고, Engine으로 `거실불 상태 알려줘`를 scripted query 선택하면 **succeeded, state='on' 반환**. query 권한을 backend에서 검증하지 않는다.
2. 같은 정책에서 `update_policy(Policy(domains={'switch': False}))` → read_domains가 **{}로 사라지고 light 읽기가 True**가 된다. API Policy에는 read_domains/read_enabled 필드가 없어 이를 정상 저장할 수도 없다. 관리자 UI에도 독립 읽기 제어가 없다.
3. read_domains.sensor=False, light.old(enabled=True, read_enabled=False, identity='stable')를 light.new로 reconcile → read_domains와 read_enabled **모두 유실**된다. set_entity_policy도 같은 구조로 재저장한다. rename swap의 write 제외 보정만으로 새로운 read 설정을 보존하지 못한다.
4. 기본 정책(domains에 person 없음)인데 person.someone 엔티티가 Catalog에 포함된다. is_domain_allowed의 새 기본 read True가 person/device_tracker/zone 및 개인 일정/할일을 명시 opt-in 없이 노출한다. 이는 기존 민감 도메인 보호/업데이트 후 무단 노출 금지와 맞지 않는다.

수정/검증:

- access 종류를 query/write/response query 및 secondary target까지 명시적으로 분류하고, 후보와 backend preflight 양쪽에서 해당 정책을 검증한다. write 허용이 명시 read 차단을 무효화하지 않게 한다.
- API/DTO/UI/DB validation 및 migration에 read 설정을 연결한다. 부분 정책 저장과 entity toggle/rename/swap/cycle/restart가 모든 필드를 보존하도록 원자적으로 갱신한다. 잘못된 타입/알 수 없는 필드가 조용히 허용되지 않게 한다.
- 개인 상태 도메인은 명시 opt-in을 유지하고 기존 설치의 허용 범위를 자동 확장하지 않는다. 일반 센서의 합리적 기본값과 민감 도메인을 구분한다.
- read-only calendar/todo/weather에서도 실제 get_events/get_items/get_forecasts를 제공해야 한다. 지금 write_allowed=False이면 query_state만 반환하여 실제 응답 조회가 사라진다.
- `/api/domains`의 queryable_count는 제어 가능한 엔티티를 제외하고 allowed_query_count는 write enabled로 계산한다. 현재 light의 count=(0,0)인데 entity.queryable은 둘 다 True인 모순을 재현했다. 실제 read/write 가능·허용 수를 각각 독립 집계한다.
- read denied/query, write denied/control, read-only response query, 무관한 설정 저장, rename/swap/cycle, 기본 민감 도메인, 재시작·업데이트 유지 시험을 추가한다.

## 4. R3 [P1] TTS 대상 ID를 추측하여 허용 범위 밖으로 전송한다

위치: `actions.py:889-895`; `engine.py` preflight/verification; capabilities.

`mp_id = entity.features.get('media_player_entity_id') or 'media_player.living_room'`는 자동 발견/원문 선택이 아니다. 현재 capabilities는 이 metadata를 구성하지 않아 일반 경로에서는 고정 fallback을 사용한다.

직접 재현: `침실 스피커로 "안녕" 방송해` → speak service_data의 media_player_entity_id가 **media_player.living_room**. HA에 해당 엔티티가 존재하고 제외되어 있다면 의도하지 않은 출력까지 가능하며, 없으면 실패한다. preflight는 tts 엔티티만 검증하므로 출력 장치 정책을 검사하지 않는다.

수정: 모델이 실제 발견되고 허용된 TTS 엔진과 출력 media_player ref를 선택하도록 한다. 원문 대상과의 의미 일치, 각 secondary target의 정책/identity/fresh capability, 최종 effect/진단을 모두 검증한다. 대상 누락/모호/제외이면 전송 0건. **고정 entity_id나 사용자 수동 매핑을 fallback으로 만들지 않는다.**

검증: 거실/침실 엔티티와 별칭을 서로 다른 ID로 두고 정확한 출력 대상, 제외 출력 차단, 없는 living_room ID, 다중/모호 대상, 전원/다른 기능과 섞인 명령을 실제 테스트 HAOS에서 확인한다. [공식 TTS 문서](https://www.home-assistant.io/integrations/tts/)의 엔진 target과 media_player_entity_id를 구분한다.

## 5. R4 [P2] C 단계 서비스명이 연결됐지만 실제 매개변수가 없다

위치: `actions.py:498-533`, `:898-928`; `engine.py:444-467`.

직접 생성한 payload:

| 요청/동작 | 현재 service_data | 문제 |
| --- | --- | --- |
| 기상시간 08:00, input_datetime.set_datetime | {} | 원문의 시간 유실, HA 필수 값 없음 |
| 내일 일정, calendar.get_events | {} | 조회 구간 없음, HA 스키마 불충족 |
| 회의 생성, calendar.create_event | summary만 | 시작/종료 또는 in이 없음 |
| 시간별 날씨, weather.get_forecasts | type='daily' 고정 | 요청 종류를 무시하며 제공 유형도 확인하지 않음 |

[Core input_datetime 서비스](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/input_datetime/__init__.py)는 date/time/datetime/timestamp 중 최소 하나를 요구한다. [Core calendar 서비스](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/calendar/services.py)는 get_events에 end_date_time 또는 duration, create_event에 유효한 시작/끝 또는 in을 요구한다. 현재 payload는 스키마를 만족하지 않는다. 신규 테스트는 set_datetime 서비스명만 assert하여 빈 dict를 정상 처리했다.

todo.update_item은 원문의 수정 종류와 무관하게 completed를 고정하고, 조회한 목록의 UID나 동명 항목 모호성을 검사하지 않는다. calendar/todo/camera choices는 각 실제 service/feature를 확인하지 않고 제공한다. input_datetime has_date/has_time 및 timezone metadata도 값 binding과 연결되지 않았다.

수정/검증:

- 날짜/시간/본문 span, timezone, 조회 범위, forecast type, todo UID/변경 속성을 typed 선택·검증한다. 실제 발견 서비스 및 entity flags/enum의 교집합에서 choices를 만든다.
- todo 목록 조회 → 이름/UID의 정확한 대상 선택 → 동명 거부 → 명시 작업의 순서를 구현한다. `수정`을 무조건 완료로 치환하지 않는다. 원문 전체를 메시지로 쓰는 fallback도 금지한다.
- 실제 HAOS의 날짜/시간 helper, local calendar/todo, 가능한 weather fixture에서 **값 변경·응답 내용**을 검증한다. 테스트 double도 실제 필수 schema를 확인하게 하여 빈 payload를 통과시키지 않는다. 마지막 finally 상태만 succeeded인지 확인하는 검증으로 끝내지 않는다.
- response query도 read 정책과 fresh capability 검증 대상이다. `return_response=True`만으로 validate_fresh를 통째로 생략하지 않는다. query/쓰기 실패 결과 및 사용자 표시를 정확히 구분한다.
- raw JSON 전체를 사용자 결과 한 줄에 출력하기보다 실제 요청 범위의 항목/측정값을 간결히 표시한다. 긴 대화 생성은 필요 없다.

## 6. R5 [P1] 조건 단계가 여전히 로컬 정규식 파서이며 정상 명령도 차단한다

위치: `engine.py:32-194`.

FIX_04가 요구한 model-selected typed condition을 구현하지 않고 COND_INDICATOR를 `면|라면|다면|...`로 넓혔다. 따라서 **장면**, **벽면**이라는 대상명도 조건으로 오인한다. scripted scope/action/exact 승인 뒤 `거실 장면 실행해줘`, `벽면 조명 꺼줘`가 condition_evaluation_failed로 거부됨을 재현했다. 사용자 동의어/이름을 로컬 파서가 의미 판단하지 말라는 요구와 정면으로 충돌한다.

또한 온도 28°C에서 `거실 온도가 28도 넘으면 거실불 꺼줘` → **condition_result=True, turn_off 1건**. 코드는 넘으면을 >=로 매핑해 경계 비교가 틀렸다. `28도를 넘으면`은 오히려 parse 실패한다. 정규식 확대가 정확한 의미 처리를 대체하지 못한다.

수정: FIX_04 R1대로 모델이 조건 여부/source/ref/comparator/literal ID/단위를 선택하고 backend가 계산하도록 전환한다. 조건을 최종 검증 계획에도 포함한다. 정규식은 literal/span 보조에만 사용한다. 정상 이름/동의어가 조건 처리로 떨어지지 않아야 한다. 부정·복합·기준 없는 조건은 typed 계약에서 지원 전까지 전송 0건 거부하며 임의 센서를 고르지 않는다.

기존 fresh 단위 검증 및 직전 상태 읽기 개선은 유지한다. 비교 경계(<,<=,>,>=), 장면/벽면/화면 등의 이름, aliases, 부정/복합/누락 센서, 정책/상태 변화의 회귀와 실제 모델 두 종류의 시험을 추가한다. 정규식 목록만 늘린 보정을 이 항목 완료로 판정하지 않는다.

## 7. R6 [P2] 진단 익명화와 검증 범위의 잔여 사항

- export에 추가한 decisions.choice가 실제 select 옵션 등의 임의 원문을 그대로 포함한다. 합성 PRIVATE_ENUM_NAME은 **기본 익명화 다운로드에도 남음**. metadata 필드라고 모든 문자열이 비민감한 것은 아니다. 안전 enum/action ID와 사용자가 만든 option/이름/본문을 구분하고 default/raw의 비밀 보호를 일관되게 적용한다.
- 새 raw password 보호는 ID substring에만 의존한다(R1). 기존 journal/삭제 엔티티/이름 변경 상태에서도 안전한 DTO 계약이 필요하다.
- provider 실패 trace에 error/HTTP code가 생긴 점은 개선이다. 단계별 실패 소요 시간·질문/배치 수도 남겨야 지연/실패 분석이 가능하다. 안전하지 않은 raw prompt/body는 저장하지 않는다.
- 평가 harness의 reset 예외 pass와 상대 밝기 expected={}는 FIX_04 뒤에도 그대로다. reset 상태 fresh 확인, setup_failed 분리, 상대 밝기 실제 변화량 assert를 구현하고 B/C corpus를 추가한다.
- 이번 보고서는 VM stopped 유지 및 단위시험만 기록한다. B/C 실제 설치·값 변경·응답·실패 검증을 수행했다는 증거가 없다. 이전 A 모델 평가와 설치/export 결과를 새 B/C 구현의 실기동 증거로 확대하지 않는다. Microsoft/Jev는 같은 초기 상태·정답/버전으로 평가하고 성공/거부/잘못된 실행과 지연을 분리한다.

## 8. 다음 실행 순서와 완료 기준

1. 민감 상태/정책/secondary target(R1~R3)을 먼저 보정한다. 이 공통 계약에 C payload 및 typed 조건(R4/R5)을 연결하고, 분석 가능한 안전 export(R6)와 실제 VM 검증을 진행한다. 새 범용 플랫폼이나 별도 사용자 수동 매핑은 필요 없다.
2. 기존 B 복수 속성/정책/저널/다운로드/조명·공조 회귀를 유지한다. 남은 기능과 실제 미지원/보류는 FIX_02 B/C 표에 대응해 기록한다. choices/서비스명만 존재하는 기능을 완료로 표시하지 않는다.
3. 프로젝트 소유 VM에서 실제 서비스 스키마와 효과/응답을 확인한다. 다음 설치는 이미 설치된 dev.7보다 높은 Dev 버전을 사용하고 config/package/Docker/UI 표기를 맞춘다. API 키·HA 토큰은 로그/보고서에 남기지 않는다.
4. B/C 묶음이 준비될 때까지 사용자 운영 시험을 요청하지 않는다. VM/fixture로 진행하고 자원 소유·격리 및 정리를 유지한다. **엄격한 초 단위 속도 기준을 추가하지 않는다.**
5. Microsoft Decision-1과 TypeSafe Jev 1.13의 비교 검증 지시는 계속 유효하다. 다른 모델을 임의 호출하거나 운영 기본을 자동 교체하지 않는다. Azure mock/live를 구분한다.
6. FIX_05_REPORT에 각 항목의 변경·명령·결과와 실기동/모의 구분, 남은 blocker, 최종 Git/자원 상태를 남긴다. Dev 개발은 자율 진행하며 다음 수정의 선행 조건으로 사용자 재승인을 요구하지 않는다. Main/안정 릴리스는 별도 승인 전까지 변경하지 않는다.
