# FIX_03 — B/C 구현 리뷰 및 Microsoft/Jev 비교 검증

작성일: 2026-10-13 · 역할: Reviewer · 판정: **수정 필요, B/C 완료 및 운영 인계 승인 보류**

## 1. 검토 기준과 현재 상태

PLAN, REPORT, FIX_01/FIX_01_REPORT, FIX_02/FIX_02_REPORT 및 현재 구현을 대조했다. 기준 HEAD는 dev `f364c8c`; 이번 Executor의 dev.7 구현 15개 파일과 FIX_02_REPORT는 아직 작업 트리 변경/미추적 상태다. 이번 리뷰는 그 변경을 포함한다. Reviewer는 제품 코드, VM, 기존 문서, Main, 릴리스를 변경하지 않았다.

좋아진 부분: rename을 새 매핑으로 계산하는 F1 방향, 이력 삭제 시 본문 화이트리스트 제거, 발견 수와 지원 수 분리, export backend 관리자 검사, button unknown 허용, 기본 B/C 실행 경로 추가. 이 개선을 유지하고 아래 결함을 보정하면서 B/C를 완성한다. A를 처음부터 재작성하거나 사용자 운영 시험을 선행 조건으로 삼지 않는다.

재검증: `uv run pytest -q` **77 passed**, FastAPI/Starlette deprecation warning 1개. `uv run ruff check addon/app tests scripts`, `uv run ruff format --check addon/app tests scripts`, `node --check addon/app/fhc/static/app.js`, `git diff --check` 통과. 새 테스트 6개는 유용하지만 scripted model/FakeHA 중심이며 실제 한국어 판단이나 HA 서비스 스키마/실기동을 증명하지 않는다. 보고서도 이번 변경에 실제 HAOS 검증이 없음을 명시한다. Docker 빌드는 보고서의 증거이며 이번 Reviewer가 재실행하지 않았다.

## 2. R1 [P1] 조건 해석 실패가 무조건 실행으로 이어진다

위치: `engine.py:36-92`, `:313-324`, 최종 검증 질문.

`_evaluate_condition()`은 정규식과 이름/영역 부분 문자열로 첫 엔티티를 선택한다. 센서 없음, unknown, 해석 실패 모두 None이고 실행부는 None을 무조건 실행과 똑같이 취급한다. 이름 유사성이 낮으면 모델이 정확히 대상을 이해했어도 조건이 사라진다. 사용자에게 금지된 로컬 정규식 대상 해석이 조건 경로에 재도입됐다. 단위 변환·ambiguous 검증·조건 freshness 재확인도 없다. final verification은 여전히 질문/미지원 조건을 false로 설명하므로 query/조건 지원 선언과도 불일치한다.

Reviewer 재현(임시 Store + FakeHA + ScriptedProvider; 실제 모델 정확도 시험 아님):

- 센서 없는 기본 fixture, `거실 온도가 28도 이상이면 거실불 꺼줘` → succeeded, condition_result 없음, **light.turn_off 1건**.
- 온도 센서가 unknown인 동일 명령 → succeeded, condition_result 없음, **1건 전송**.
- 온도 센서 70°F, `거실 온도가 28도 이상이면 거실불 꺼줘` → condition_result=True, **1건 전송**. 원문의 도가 °C인지 °F인지 검증하지 않고 비교한다. `28℃` 표현은 아예 정규식에서 빠져 None이 된다.

요구 수정:

- 모델이 허용 카탈로그에서 조건 source/ref, 실제 읽을 속성, comparator, 원문 literal ID, 단위를 typed 선택하도록 한다. 정규식은 literal span 추출에 한정하고 센서/조건 의미를 결정하지 않는다.
- 조건 없음/조건 true/false/판단 불가를 별도로 표현한다. 조건이 명시되었지만 완전한 typed 계획이 없으면 **전송 0건으로 거부**한다. 모델 exact=true도 이 backend 검증을 우회하지 못한다.
- 허용 여부/identity, 센서 단위·device_class, 값 가용성/유한수, 모호한 복수 센서, 부정·범위·지원하지 않는 복합 조건을 검증한다. source를 계획에 포함하고 상태를 실행 직전 다시 읽는다. 28과 목표 25를 별개 literal로 유지한다.
- 모델 요청과 final verification에 조건 및 query 의미를 일관되게 전달한다. 관측 시각/사용 값/단위/평가 결과를 안전한 진단 DTO에 남긴다.
- true/false/unknown/unavailable/센서 없음/제외/동명/동의어/부정/°C·°F/실행 직전 변화 시험을 추가한다. unknown 등의 경우 항상 HA 전송 0건을 확인한다.

## 3. R2 [P1] 실제 API 키가 설정되면 로그 다운로드가 실패한다

위치: `main.py:416-445`, Options의 SecretStr 필드.

known_secrets에 Options.openrouter_api_key/azure_api_key의 **SecretStr 객체**를 넣고 문자열 포함/치환 연산에 사용한다. 임시 Options(openrouter_api_key='synthetic-review-key')와 기록 1개로 export_history 호출 시:

`TypeError: 'in <string>' requires string as left operand, not SecretStr`

운영 기본 조건인 API 키 설정 상태에서 다운로드 기능이 작동하지 않는다. 기존 export 테스트는 실제 provider Options 키가 비어 있어 놓쳤다.

수정: backend에서 `.get_secret_value()`로 문자열을 추출해 마스킹용 집합을 구성하되 출력/저장하지 않는다. OpenRouter 단독/Azure 단독/둘 다 설정된 실제 Options 타입으로 default/raw export를 테스트하고, 비밀 marker가 중첩 값과 문자열 어디에도 남지 않는지 확인한다. ZIP 다운로드를 실제 Ingress에서도 검증한다.

## 4. R3 [P1] 기본 공유 로그가 상태와 임의 쓰기 값을 그대로 노출한다

위치: `main.py:437-511` export redact.

현재 full journal을 재귀 순회하는 denylist다. text/message/name 등을 일부 가려도 previous_state, query_results.state, service_data.value 등은 그대로 남는다. 알려진 API 키 치환만으로 password input_text, 일정/할일/위치성 상태, 임의 메시지의 민감 값 전체를 보호할 수 없다.

Reviewer 재현: 키 없는 임시 provider, proposed_plan에 previous_state='PRIVATE_STATE_MARKER', service_data.value='PRIVATE_VALUE_MARKER', query_results.state='PRIVATE_STATE_MARKER'를 저장한 뒤 기본 export. **두 marker 모두 requests.jsonl에 남음**. 실제 사용자 정보 대신 합성 marker만 사용했다.

수정:

- journal 원본을 export하지 말고 명시적인 진단 DTO allowlist를 만든다. 기본 모드는 명령 원문/불투명 텍스트·개인 상태를 제외하고 안정적인 가명으로 target/name/area를 연결한다. entity/name 매핑을 같은 dict에 혼합하지 않는다. 자유 문자열 안에 이름·ID가 재등장해도 처리한다.
- include_text=true도 모든 임의 상태/비밀 데이터 공개 허가가 아니다. password-mode input_text, 인증 URL/키/토큰/쿠키/좌표 및 민감 응답 필드를 계속 제외한다. 온도 같은 허용된 진단 측정값과 불투명 텍스트를 구분한다.
- 삭제 이력 제외 및 관리자 backend 검사 유지. known-secret 치환은 allowlist에 추가하는 방어로 둔다.
- 현재 쿼리는 LIMIT 후 hidden/status/request_id 필터를 적용하므로 일치하는 과거 기록이 있어도 빈 결과가 나올 수 있다. limit=-1은 SQLite 무제한이며 limit>5000의 truncated 계산도 잘못된다. FastAPI 범위 검증, 필터 적용 순서, 실제 선택/제외/잘림 수를 수정한다.
- manifest에 필터/status/request ID, architecture/timezone 등 FIX_02 요구 메타데이터를 연결하고 provider 실패 phase/elapsed/HTTP code/배치 수를 안전하게 남긴다. 현재 provider.py는 변경되지 않아 실패 trace 누락이 해결되지 않았다.

## 5. R4 [P1] automation.trigger가 HA의 조건을 건너뛴다

위치: `actions.py:511-516` automation make_action 분기.

trigger의 service_data가 {}다. HA Core 2026.10.1은 skip_condition 기본값 True이므로 명시적인 false 없이 호출하면 기존 automation 조건을 생략한다. FIX_02가 명시한 skip_condition=false 고정을 구현하지 않았다. 실제 서비스 생성 함수를 직접 호출해 빈 dict를 확인했다.

수정: trigger에 `skip_condition: false`를 서버에서 고정한다. turn_off의 stop_actions 의미도 명시적으로 보존하고 final effect에 설명한다. 이미 automation off라는 이유만으로 실행 중 작업 중단까지 no-op 처리하지 않는다. 조건이 false인 automation을 실제 테스트 HAOS에서 trigger하고 부수효과 counter가 증가하지 않는지 검증한다.

근거: [Core 2026.10.1 automation source](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/automation/__init__.py), 서비스 등록의 CONF_SKIP_CONDITION default=True 및 CONF_STOP_ACTIONS.

## 6. R5 [P1] 도메인 서비스 존재를 엔티티 지원 능력으로 오인한다

위치: `actions.py:125-369`, `:569-598`, `main.py:228-270`.

B의 많은 choices가 도메인 전체 서비스 이름만 확인하고 entity supported_features를 확인하지 않는다. fan supported_features=0인데도 domain에 서비스가 있으면 percentage/oscillate/power 선택지가 나온다(직접 재현). 다른 integration이 서비스를 등록했다고 모든 엔티티가 지원하는 것은 아니다. number step/unit, humidifier 실제 min/max, fan 속도 간격도 실행 검증에 연결되지 않았다. cover garage/gate 검사는 pass라서 보호 동작이 없다.

수정:

- 도메인별 runtime services ∩ entity feature flags ∩ enum/range/step/unit을 공통 capability 근거로 choices, validate_fresh, 지원 count에 적용한다. static 서비스만 보고 기능을 승인하지 않는다.
- 민감 cover device_class는 일반 cover 도메인을 켜도 기본 보호하고 세부 opt-in을 명확히 한다. password-mode input_text는 제외한다. 새 제어 도메인의 기존 설정 자동 허용 금지는 유지한다.
- UI controllable/queryable_count는 실제 가능한 기능에서 계산한다. 현재 camera는 query만 구현했는데 controllable로, input_datetime는 실행 후보가 없는데 supported로 집계된다.
- read/query와 write/control 정책을 분리한다. 현재 하나의 domain bool에 둘을 묶었으며 vacuum 등의 상태 조회도 QUERY_DOMAINS 목록에 없어 제공되지 않는다.
- [HA Fan entity 공식 문서](https://developers.home-assistant.io/docs/core/entity/fan/)의 feature enum처럼 실제 Core의 공식 규약을 확인한다. 기능 0/일부/전체인 엔티티들을 같은 domain fixture에 함께 두고 음성 시험한다.

## 7. R6 [P2] 복수 속성, 본문 쓰기, 선택 목록, 사용자 결과가 미완성이다

위치: `actions.py:457-539`, `:322`, `engine.py:337-346`, `static/app.js:97-133`, `store.py:195-208`.

- fan power=turn_off + percentage=v0를 make_action에 주면 **set_percentage만 반환**한다(재현). humidifier/media도 elif 우선순위로 추가 요청을 버린다. final 모델이 발견할 수도 있으나 backend는 유실된 계획을 생성해서는 안 된다. 필요 시 검증된 여러 action으로 분리하고 상충 요청은 전송 0건 거부한다.
- input_text/notify/tts는 원문 span 본문이 아니라 전체 지시문을 text.strip()으로 전송한다. input_text min/max/password, 정확한 메시지 경계가 없고 tts에는 허용 media_player target도 없다. 원문의 명시 본문 span을 typed 선택하고 backend에서 검증해야 한다. 임의로 전체 명령문을 메시지로 치환하지 않는다.
- select options[:20]은 21번째 옵션 이후를 모델에서 조용히 제거한다. 전체 enum을 제공하거나 누락 없는 분할을 구현한다.
- query_result는 actions에 있어도 사용자 UI는 query_succeeded를 표시하지 않아 **“0개 기기에 요청을 전달했어요.”**가 된다. 조건 false도 같은 문구다. 실제 측정값·단위/조건 미충족을 간결하게 표시한다.
- Store.shortcuts는 모든 succeeded 원문을 수집하므로 조회·메시지/개인정보·조건 false까지 바로가기 후보가 된다. 허용된 제어 실행만 추천하고 기존 새 UUID/현재 정책 재검증은 유지한다.
- script.turn_on은 script의 restart/queued 등 모드를 고려해야 하므로 단순 current=on만으로 무조건 생략하지 않는다. domain별 no-op을 검토한다.

## 8. R7 [P2] B/C 필수 범위 및 실제 HAOS 검증을 완료해야 한다

FIX_02의 범위를 축소 승인한 적 없다. 현재 다음은 미구현/부분 구현이므로 B/C 전체 완료로 인계하지 않는다:

- B: vacuum fan speed; fan preset/direction; cover tilt; media source/sound mode; input_number increment/decrement; select next/previous/first/last; counter set_value; light effect; climate fan/preset/swing.
- C: weather.get_forecasts, calendar.get_events/create_event, todo.get_items/명시 CRUD; input_datetime/time; legacy notify service-only discovery; tts 대상 연결; camera 실제 지원 power/motion; update 버전 속성 등 typed 조회. 지금 대부분 query_state로 state 문자열만 읽어 응답 서비스/속성 기반 기능을 대체했다.
- “청소기 상태 어때” 등 제어 도메인의 query 경로, query/write 정책 구분, 사용자 결과/UI까지 연결.

FIX_02의 B/C 표를 기준으로 구현/실제 미지원/보류/검증 결과를 도메인·동작별로 작성한다. 실제 blocker는 증거와 함께 기록하고 다른 독립 작업은 계속한다. ai_task/conversation, 업데이트 설치, 장기 예약 등 기존 보류 범위는 유지한다.

다음 Executor는 프로젝트 소유 HAOS VM에서 dev.7 변경과 보정을 설치하고 검증한다. 기동 가능한 빌드만으로 끝내지 않는다. HA의 실제 feature/enum/응답 스키마로 B/C 대표 명령, 혼합 명령, 조건 true/false/unknown, 정책/rename, 재시작/중복/실패, 관리자 export 다운로드/압축 해제/JSON 파싱, 모바일 결과 표시를 확인한다. 없는 demo 기능은 테스트 integration/helper로 보충하며 운영 사용자에게 YAML/수동 매핑을 요구하지 않는다. VM 소유·격리 확인 및 자원 정리는 기존 지침을 따른다.

이미 설치했던 Dev보다 버전을 올려 HAOS 업데이트로 시험하고 config/package/Docker/UI 버전을 맞춘다. 이번 Reviewer는 VM을 변경하지 않았으며 dev.7 실기동을 인증하지 않는다. B/C 묶음 검증 전 사용자 운영 테스트 요청은 하지 않는다. 특정 초 이내를 엄격한 통과 기준으로 삼지 않고 기능·잘못된 실행 방지와 실제 측정 결과를 우선한다.

## 9. 사용자 신규 지시: TypeSafe Jev 1.13을 비교 검증에 추가

사용자가 OpenRouter를 통한 Jev 1.13 검증/테스트를 명시적으로 요청했다. 따라서 FIX_02의 Microsoft-only 제한은 **Microsoft Decision-1 및 TypeSafe Jev 1.13 두 모델에 한해** 확장한다. 다른 모델/공급자 자격이 자동 승인된 것은 아니다. 운영 기본 모델을 자동 교체하지 않는다.

- 정확한 ID: **`typesafe/jev-1.13`**. `jev-latest`나 router alias 대신 지정 버전을 사용한다.
- [OpenRouter 모델 페이지](https://openrouter.ai/typesafe/jev-1.13/) 및 [공식 Decisions API 예제](https://openrouter.ai/blog/insights/what-is-jev/) 확인. POST `https://openrouter.ai/api/alpha/decisions`, model/state/questions 및 choice/noul 구조를 지원한다. 현재 Provider와 공통 계약으로 시험할 수 있다.
- Reviewer 실제 API 계약 확인 **1 HTTP 호출**: 기존 ignored 개발 키를 메모리에서 사용, HA/물리 기기 호출 없음. command='거실불 켜줘', 거실/침실 조명 2개 합성 후보, noul+choice 두 질문(현재 코드처럼 instructions object 포함)을 전송했다. requested_model=`typesafe/jev-1.13`, returned_model=`typesafe/jev-1.13-20260917`, valid=0.98, target=e0, 기존 noul()/choice() 검증 통과, 관측 roundtrip **959ms**. 키/원시 인증 응답은 저장하거나 출력하지 않았다.
- 이는 API 및 단일 의미 선택 smoke test다. 전체 파이프라인, B/C 정확도, 한국어 일반 성능, 장기 지연 비교를 증명하지 않는다.

Executor 작업:

1. `scripts/evaluate_stage_a.py`의 Microsoft-only guard를 두 정확한 model ID allowlist로 확장하거나 공통 비교 harness로 정리한다. localhost 프로젝트 VM 제한, 비밀 비출력, Azure 임의 호출 방지는 유지한다. ephemeral Options로 model만 바꾸고 운영 저장 설정을 덮어쓰지 않는다.
2. 같은 fixture 초기 상태·정책·카탈로그와 동일한 A/B/C 정답 표로 **두 모델 모두** 평가한다. 매 case 상태를 초기화하여 앞 모델의 실행이 뒤 모델의 no-op 결과/속도를 바꾸지 않게 한다. 동의어, 복수 영역/속성, 명시 조건, query/본문 경계, 제외/미지원/모호/부정 사례를 포함한다.
3. requested/returned model, prompt/fixture 버전, 단계별/전체/첫 전송 시간, logical stage와 실제 HTTP call 수, 정상 성공/안전 거부/잘못된 target·value·execution을 분리 기록한다. 모델별 calibration 차이는 결과로 검토하되 통과를 위해 안전 임계값을 임의로 낮추거나 다른 모델에 재질문하지 않는다.
4. 유효 키가 없거나 API 장애면 원시 body/키 없이 오류 코드로 보고하고 mock/HAOS 시험을 계속한다. 성공/실패한 live 범위와 모델별 검증 상태를 명확히 구분한다.

## 10. 다음 인계

다음 Executor는 가장 높은 미보고 교정인 **FIX_03**을 수행하고 `FIX_03_REPORT.md`를 새로 작성한다. 기존 문서/보고서를 덮어쓰지 않는다. R1~R7 및 두 모델 시험을 실제 변경·테스트·HAOS 증거와 연결하고 완료/미완료를 구분한다. F1/F2 보정도 회귀 유지한다. 결과 문서/지원표/CHANGELOG에 실제 범위를 반영한다.

Reviewer가 기록한 API 단일 성공을 자체 HAOS/모델 평가 증거로 확대 인용하지 않는다. Dev 개발·테스트는 자율 진행하되 Main 및 안정 릴리스는 사용자 별도 승인 전까지 변경하지 않는다.
