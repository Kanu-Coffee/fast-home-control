# FIX_02 — A단계 재리뷰 및 B/C 구현으로 진행하는 인계

- 작성일: 2026-10-13
- 역할: Reviewer
- 검토 대상: `PLAN.md`, `REPORT.md`, `FIX_01.md`, `FIX_01_REPORT.md`, Git 코드/테스트/공개 검증 결과.
- 기준: `dev` / `20c28d70108a03e9be0d25827914855a0f163aec`, 앱 `0.2.0-dev.6`. 리뷰 시작 시 작업 트리는 clean.
- 사용자 최신 피드백: 운영 테스트에서 전체적으로 정상 작동. B/C까지 구현해야 실운영 시험이 원활하므로 그전까지 프로젝트 VM으로 개발·검증. 관리자 UI에 분석용 로그 다운로드 추가.
- 기존 문서는 덮어쓰지 않는다. Executor는 이 문서를 읽고 실제 Git 상태를 다시 확인한 후 작업하며 **`FIX_02_REPORT.md`**에 결과를 남긴다.

## 1. 판정과 다음 작업의 목적

**A단계의 기본 구조는 B/C 개발 기반으로 사용할 수 있다. A단계를 처음부터 다시 구현하거나 정상 문장의 거부율을 완전히 없앤 뒤에야 확장할 필요는 없다.** 사용자 운영 피드백과 실제 HAOS·모델 증거, 회귀 테스트가 이를 뒷받침한다.

다만 아래 F1은 재현된 정책 유실 결함이므로 새 B/C 빌드를 배포하기 전에 수정해야 한다. F2는 로그 다운로드 및 C의 텍스트 작업 전에 해결한다. 두 보정을 B/C의 공통 기반 착수 작업에 묶어 진행한다. F3~F4는 현재 표시 문제와 새 요구사항이며 같은 확장 작업에 포함한다. 이를 이유로 B/C를 계속 별도 “다음에”로 미루지 않는다.

이번 인수는 **B/C 진행 가능 판단**이다. 모든 결함이 없다는 보증, Main 반영 승인, 안정 릴리스 승인이 아니다. 현재 Reviewer 턴에서는 제품 코드·VM·앱 버전을 변경하지 않는다.

## 2. 재검증한 증거

| 검증 | 이번 Reviewer 결과 |
| --- | --- |
| `uv run pytest -q` | **71 passed**, 1 Starlette deprecation warning, 1.63s |
| `uv run ruff check addon/app tests scripts` | 통과 |
| `uv run ruff format --check addon/app tests scripts` | 통과, 19 files |
| `node --check addon/app/fhc/static/app.js` | 통과 |
| `git diff --check` | 통과 |
| GitHub Checks `38356687010` / HEAD `20c28d7` | success |
| GitHub Checks `38355927298` / 앱 소스 `0b0330b` | success; Executor 기록의 amd64/aarch64 빌드 증거와 대조 |
| 추가 읽기 전용 재현 | 임시 SQLite Store로 F1/F2 확인. 저장소 소스는 수정하지 않음 |

관리자 권한 검사, Supervisor 단일 옵션 원본, capability 기반 후보, 실제 값/단위 연결, 복합 속성, 새 도메인의 보수적 migration, 공식 서비스 호출·저널을 코드에서 확인했다. `docs/verification.md`, `docs/evidence/0.2.0-dev.5.json` 및 FIX_01_REPORT의 mock/live 구분을 검토했다.

기존 실제 모델 고정 시험의 13/15는 정상 8/10, 음성 5/5라는 제한된 결과다. 정상 거부 2건과 그룹 별칭 거부는 후속 정확도 개선 대상으로 유지한다. 이번 턴에는 VM을 재기동하거나 유료 API를 다시 호출하지 않았다. 기존 증거와 사용자 피드백을 이번에 새로 수행한 실기동 시험으로 포장하지 않는다.

## 3. F1 [P1] 여러 rename이 한 snapshot에 반영되면 제외 정책이 유실됨

위치: `addon/app/fhc/store.py:120–140`, `reconcile_registry()`.

현재 코드가 원본 override를 순회하면서 같은 대상 dict에 이동/삭제한다. 서로 이름을 교환한 안정 ID 두 개가 한 레지스트리 snapshot에 나타나면 앞서 이동한 항목을 다음 반복에서 지운다.

실제 실행한 최소 재현:

```python
store.set_entity_policy('light.a', False, 'id-a')
store.set_entity_policy('light.b', True, 'id-b')
ha.registry = [
    {'entity_id': 'light.b', 'id': 'id-a'},
    {'entity_id': 'light.a', 'id': 'id-b'},
]
store.reconcile_registry(ha)
```

결과:

```text
overrides = {"light.a": {"enabled": true, "identity": "id-b"}}
is_allowed('light', 'light.b', 'id-a') == True
```

원래 차단된 `id-a`의 override가 사라져 도메인 기본 허용으로 복귀한다. HA에서 임시 이름을 거쳐 여러 rename을 수행하고 앱이 마지막 snapshot을 처리하는 경우와 연결되는 서버 로직 결함이다. 실제 운영 환경에서 이 사고가 발생했다고 주장하지 않는다. 기존 단일 rename 테스트는 이 경우를 검증하지 않는다.

필수 수정/검증:

- 원본 snapshot에서 안정 identity 기준으로 전체 목적지 매핑을 계산한 뒤 새 정책을 한 번에 구성·저장한다. 순회 중 이동한 항목을 다시 삭제하지 않는다.
- 허용/제외의 충돌, 중복 identity, 임시 이름을 거친 교환·순환 rename, 삭제/재사용 ID를 명시적으로 처리한다. 충돌 때 기존 제외를 조용히 허용으로 바꾸지 않는다.
- rename 순서/iteration 순서를 바꿔도 같은 결과가 나와야 한다. 정책 revision과 실행 직전 재검증을 유지한다.
- 두 ID 교환, 세 ID 순환, 모두 제외, 허용/제외 혼합, 기존 override 없는 새 엔티티, legacy identity 없는 override의 회귀 테스트를 추가한다.
- 테스트 VM에서 여러 rename 후 최종 snapshot을 한 번 동기화해 제외 유지와 실제 최종 target을 확인한다. 운영 기기로 시험하지 않는다.

## 4. F2 [P2] 이력 삭제가 새 계획 필드를 남김

위치: `addon/app/fhc/store.py:212–220`, `clear_history()`.

현재 삭제는 `text=''`, `actions=[]`, `hidden=True`만 적용한다. 다음 재현에서 삭제 뒤에도 `proposed_plan`의 기기명/ID/매개변수가 남았다.

```python
record = store.insert('review-only-id', '검토용 명령')
record['proposed_plan'] = [
    {'name': 'REVIEW-PRIVATE-ROOM', 'entity_id': 'light.private_room',
     'service_data': {'brightness_pct': 30}}
]
record['status'] = 'rejected'
store.save('review-only-id', record)
store.clear_history()
# text/actions는 비지만 proposed_plan은 그대로 남음
```

현재 history API가 hidden 기록을 숨기므로 이를 공개 API에서 즉시 유출된 사건으로 표현하지 않는다. 그러나 삭제의 내용 제거 의미와 다르고, C의 메시지/일정/텍스트 계획 및 다운로드를 추가하면 실제 개인정보 잔존으로 이어진다.

필수 수정/검증:

- 삭제 후 남길 dedup 필드를 whitelist로 정의한다. 요청 ID/생성 시각/최종 상태 등 필요한 최소 저널만 보존하고, 원문·기기명·계획·읽기 결과·메시지·literal span 등 내용 필드를 제거한다.
- hidden/삭제된 기록을 다운로드·바로가기·상세 이력에 재노출하지 않는다. 기존 DB의 hidden 기록에도 같은 내용 제거 규칙을 적용한다.
- 삭제 후 UUID 재전송 방지의 기존 의미를 유지한다. 내용을 삭제했으므로 같은 ID의 본문 충돌이 날 수 있다는 기존 계약을 임의 재실행으로 바꾸지 않는다.
- 기존 A 계획과 C의 텍스트/조회 결과를 포함한 records로 DB 논리 내용, export, shortcut을 검사한다. 디스크 전체의 암호학적 삭제를 구현했다고 주장할 필요는 없다.

## 5. F3 [P2] 발견 수와 지원/허용 수를 분리

위치: `main.py:202–234`, `catalog.py`, `static/app.js`의 도메인 표시.

`/api/domains`의 `discovered`에는 sensor/vacuum/button 도메인도 있을 수 있지만 `count`는 세 도메인만 들어가는 실행 Catalog에서 센다. 따라서 미지원 도메인을 실제 “0개 기기”로 표시한다. 사용자 문의와 코드가 일치한다.

- HA registry/state에서 **발견한 엔티티 수**, 지원하는 **제어/조회 수**, 정책상 **허용 수**를 구분한다. 전부 같은 숫자로 돌려주지 않는다.
- 최소 DTO: `discovered_count`, `controllable_count`, `queryable_count`, `allowed_control_count`, `allowed_query_count`, 지원 상태/제외 이유. registry만 있고 state가 없는 경우도 발견 사실과 비활성 사유를 표시한다.
- UI 예: `센서 · 발견 12개 · 조회 가능 10개 · 허용 8개`, `카메라 · 발견 2개 · 상태 조회만 지원`. 미지원은 `발견 N개 · 현재 미지원`으로 표시한다.
- legacy `count`를 유지할 경우 의미를 문서화하고 새 UI가 이를 전체 발견 수로 쓰지 않게 한다. 조회 전용·정책 OFF·미지원·unavailable을 구분한다.
- count를 높이려고 미지원 엔티티를 실행 후보로 무조건 노출하지 않는다. 사용자가 개별 기기를 수동 등록하는 절차는 만들지 않는다.

## 6. F4 [필수 신규 요구] 관리자 진단 로그 다운로드

UI의 관리자 상세 실행 이력 옆에 **`진단 로그 다운로드`** 버튼을 둔다. 사용자가 운영 시험 뒤 파일을 전달하면 다른 세션의 Codex도 분석할 수 있어야 한다. 이번에는 인계 요구사항을 명시하며 버튼 자체는 아직 구현하지 않았다.

### 6.1 파일과 선택 범위

- 범용 도구 없이 읽을 수 있는 UTF-8 JSON/JSONL을 사용한다. 권장 단일 ZIP: `manifest.json`, `requests.jsonl`, `summary.json`. 작은 데이터면 단일 JSON도 허용한다. 표준 라이브러리를 우선하며 불필요한 의존성은 추가하지 않는다.
- 기본 최근 24시간 + 전체 결과 상태. 관리자에서 기간/상태/특정 요청 ID를 선택할 수 있게 한다. 화면의 최근 8건 또는 `Store.recent()`의 50건만을 전체 로그처럼 내보내지 않는다.
- 보존 범위 안에서 bounded query/크기 한도를 적용한다. 제한에 걸리면 포함/제외 건수와 `truncated` 및 범위를 명시하거나 범위 축소를 안내한다. 조용히 로그를 누락하지 않는다.
- 다운로드는 읽기 작업이다. 이력 삭제나 새 HA 호출/모델 호출을 유발하지 않는다. 원본 DB 파일, SQLite settings, options 파일, 전체 home state 덤프를 내려주지 않는다.
- 파일명은 앱 버전/UTC 생성 시각을 기반으로 서버가 정한다. 사용자가 파일 경로나 서버 파일명을 지정하는 API는 만들지 않는다.

### 6.2 분석에 필요한 내용

- `export_schema_version`, 앱 버전, HA Core 버전(확인 가능한 경우), 아키텍처, 시간대, 생성 시각과 선택 범위, 익명화/원문 포함 여부, 누락/제한 정보.
- 요청별 ID, 시각, status/reason/실패 phase, 공급자/요청 모델/반환 모델, 실제 API 호출 수·분할/batch 정보, 단계별 왕복/내부/preflight/첫 전달/HA ACK 시간.
- scope/choice/final 점수, 후보와 값의 연결을 해석할 최소 메타데이터, 검증된 동작/값, no-op/sent/not_sent/partial/uncertain, 정책 revision 및 capability 거부 사유. C에서는 조건의 실제 평가 결과와 사용한 조회 값의 허용된 요약.
- HTTP 실패·타임아웃·잘못된 응답도 phase별 시간과 **안전한 오류 코드/HTTP status/budget/질문 개수**를 남긴다. 현재 engine의 stage 시간과 provider trace는 성공 반환 뒤 기록하므로 실패 회차의 진단이 불충분하다. 실패를 total 시간만 보고 추정하게 두지 않는다.
- 원본 provider 오류 본문/인증 헤더/전체 프롬프트를 그대로 저장·내보내지 않는다. 필요하면 allowlist로 검증 오류의 안전한 분류/필드 경로만 추출한다.

### 6.3 원문과 비밀정보

- 기본 공유 파일에서는 사용자·기기·영역 이름/ID를 일관된 별칭으로 가리고 원문 및 전체 상태를 제외한다. 파일 안에서 ID 연결이 가능해야 하며 역매핑/원래 이름 표를 같이 넣지 않는다. 이를 완전한 익명성 보증으로 홍보하지 않는다.
- 의미 해석 분석을 위해 별도 **`명령 원문·기기 이름 포함`** 선택을 제공한다(기본 OFF). 선택하면 파일에 포함되는 내용이 보이도록 짧은 설명을 둔다. 각 다운로드마다 복잡한 승인 대화는 요구하지 않는다.
- 어느 모드에서도 OpenRouter/Azure/Supervisor/HA 토큰, 키, 쿠키/Ingress session, password input_text, GPS 좌표·인증 URL은 제외한다. C의 notify/tts/일정/할일 텍스트와 재실 정보는 민감 필드로 다룬다. 원문 포함 선택이 API 키나 임의 민감 상태 전체를 포함하는 허가는 아니다.
- redaction을 record DTO에 재귀 적용하고 현재 설정의 알려진 비밀 값도 검사한다. 키 이름 몇 개를 지우는 방식이나 frontend에서만 마스킹하는 방식으로 끝내지 않는다.
- 삭제된 기록은 원문 포함 모드에서도 복구되지 않아야 한다. 로그 파일을 자동 업로드/전송하지 않는다.

### 6.4 권한과 실제 다운로드 검증

- export 라우트도 실제 HA 관리자 권한을 backend에서 검사한다. 현재 middleware의 management set은 **경로 열거**이므로 `/api/history/export`를 새로 만들면 `/api/history` 보호가 자동 적용된다고 가정하지 않는다. 공통 dependency 또는 검증한 경로 정책으로 보호한다.
- `Cache-Control: no-store`, 안전한 Content-Disposition/Content-Type, 기존 Ingress prefix/origin 방어를 유지한다. 읽기 전용 export라면 불필요하게 전역 실행 lock을 오래 점유하지 않도록 consistent snapshot을 사용한다.
- 실제 Ingress와 모바일에서 파일 다운로드→압축 해제/JSON 파싱→요청 ID 추적을 검증한다. 기존 `api()` helper는 JSON 응답 전용이므로 binary/Blob 다운로드 경로를 적절히 분리한다. 기존 CSP와 object URL 정리도 확인한다.
- 누락/위조 사용자·비관리자·권한 회수의 403, 비밀 marker와 중첩 필드 redaction, 삭제 이력 제외, 범위/한도, 이전 버전 기록·실행 중 snapshot, 파일명이 안전함을 테스트한다.

## 7. B/C 작업 순서와 완료 범위

순서는 **공통 보정/진단 → B 일반 가전 → B helpers/명시 실행 → C 조회 → C 제한 쓰기·단순 조건 → 묶음 VM 검증**으로 진행한다. F1/F2와 export를 독립적인 장기 A 재개발 단계로 만들지 않는다.

공통 구조:

- `SUPPORTED`에 도메인명만 추가하는 구현은 완료가 아니다. discovery/지원 상태/정책, capability 기반 동작, scope 질문, 값 연결, 전체 계획 검증, preflight, no-op/저널, 결과 DTO/UI까지 연결한다.
- `engine.VALID`, supported_actions, 최종 검증, `make_action`, `validate_fresh`는 현재 세 도메인 전용이다. 새 도메인/조회/조건을 adapter 메타데이터로 설명하게 바꾸고 서로 다른 하드코딩 목록이 어긋나지 않게 한다. 작은 도메인별 함수/adapter로 충분하며 범용 에이전트 플랫폼은 만들지 않는다.
- `unknown` 상태는 모든 도메인에서 사용 불가와 같지 않다. 예를 들어 처음 누르기 전 button 상태와 unavailable을 구분한다. 도메인별 유효 상태와 지원 기능으로 확인한다.
- read/query와 write/control 권한을 분리한다. entity override는 도메인 master를 우회하지 않는다. 기존 설정을 보존하고 새 제어 도메인을 업데이트만으로 자동 허용하지 않는다.
- button/script/automation/scene/helper/notify/tts는 간접 효과/외부 전송을 고려해 명시 opt-in을 유지한다. 숨김/설정/진단 항목을 도메인 추가만으로 자동 승격하지 말고 발견/보호 사유를 표시한다. 이름만으로 안전성을 추측하지 않는다.
- 대상·동작을 로컬 키워드로 제거하지 않는다. 큰 catalog는 허용된 모든 metadata를 빠짐없이 의미 검토할 수 있게 압축/분할한다. 40KB 초과가 많아지면 paging을 개선하되 silent top-K/truncation으로 해결하지 않는다.

### 7.1 B — 실제 일반 가전과 명시 실행

| 도메인 | 필수 대표 동작/검증 범위 |
| --- | --- |
| vacuum | start/pause/stop/return_to_base, 지원 fan speed. 단순 on/off만 제공하지 않음. platform별 send_command/params는 제외. 영역 청소는 HA가 이미 제공한 공식 mapping이 있을 때만 후속 지원하며 FHC 설치 사용자에게 segment ID/YAML 매핑을 요구하지 않음 |
| button | 명시한 기존 엔티티 press. 첫 press의 unknown/timestamp 상태 처리, 비멱등 명령의 timeout 재전송 방지, opt-in |
| fan | 전원, percentage, 제공 preset/oscillation/direction. 단계/enum 검증 |
| cover | open/close/stop/position, 지원 tilt. 차고문 등 민감 device_class 기본 보호 |
| humidifier | 전원, 목표 습도, 실제 mode. 단위/범위/기능 검증 |
| media_player | 전원, 재생/일시정지/정지, volume/mute, source, next/previous, 제공 sound mode. 임의 URL 재생·그룹 join·삭제 제외 |
| input_boolean | 전원. 간접 automation 효과의 opt-in |
| number/input_number | set_value, input_number increment/decrement. entity별 min/max/step/단위 검증 |
| select/input_select | 실제 options 선택, 제공 next/previous/first/last. set_options/reload 같은 구조 변경 제외 |
| counter | increment/decrement/reset/set_value 중 실제 서비스. reset은 명시 요청, configure 제외 |
| script | 기존 script 명시 실행/중단. 임의 variables/스크립트 생성·편집 제외 |
| automation | enable/disable 및 명시 trigger. skip_condition=false 고정, stop_actions 의미와 부작용 보존 |
| scene | 기존 scene 명시 활성화. apply/create/delete 제외 |
| 기존 light/climate | 기존 기능 회귀 유지. light effect, climate fan/preset/swing 등 실제 제공 enum 확장도 같은 adapter 방식으로 구현 |

### 7.2 C — 조회, 의미 판단, 제한 쓰기

| 도메인 | 실제 제공할 범위 |
| --- | --- |
| sensor/binary_sensor | fresh state·단위·device_class 기반 조회. 모델이 값을 생성하지 않고 backend의 실제 값을 결과로 반환. 센서 set_state/강제 켜기 동작을 만들지 않음 |
| weather | 현재 상태 + 지원 get_forecasts 응답. 예보가 없으면 생성하지 않음 |
| calendar | get_events 및 지원하는 명시 일정 생성. HA 시간대/종일/시작·종료와 대상 검증 |
| todo | get_items, 명시 add/update/complete/remove. 중복 이름은 UID로 판단, 무분별한 일괄 삭제 제외 |
| input_text/input_datetime/time | 원문 span/정확한 날짜·시간 기반 set_value 등 공식 동작. password mode 제외, 날짜 설정과 명령 예약 구분 |
| notify/tts | 원문에 있는 명시 메시지만 전송/speak. 발견된 대상만 사용. legacy notify service-only 대상도 자동 발견하되 entity 수와 서비스 수를 혼동하지 않음. 별도 기본 OFF |
| person/device_tracker/zone | opt-in 재실/허용된 상태 조회. 위치 조작/전체 좌표 노출/편집 제외 |
| sun/event | 실제 속성·최근 이벤트/시각 조회. 센서/이벤트 재발행을 실행 기능처럼 만들지 않음 |
| camera/image | 상태·갱신 정보 조회. camera는 실제 지원 on/off/motion detection만 opt-in. 임의 snapshot/record 파일경로·외부 스트림/이미지 분석은 제외 |
| update | 현재/사용 가능 버전 조회만. install/skip/clear_skipped는 일반 가전 제어로 공개하지 않음 |
| ai_task/conversation | 일반 가전 실행에 필요한 도메인이 아니므로 원래 PLAN의 보류 유지. 발견 수/보류 이유를 표시. 별도 AI 재호출/자유 생성으로 우회하지 않음 |

C의 센서 활용:

- 먼저 “거실 온도 알려줘”, “청소기 상태 어때”, “창문 열렸어?”를 실제 값으로 반환하는 경로를 완성한다. 성공 표시는 write ACK와 구분한다.
- 이어 단순한 명시 조건을 C 후반 범위에 포함해 검증한다. 예: **“거실 온도가 28도 이상이면 에어컨 냉방 25도로”**. 모델은 센서/대상/비교 연산/원문 값 ID를 선택하고 backend가 typed 조건을 계산한다.
- 센서 입력 28과 목표 온도 25를 구분한다. 조건 true/false/판단 불가를 별개 결과로 기록하며 false일 때 서비스 호출은 0건이다.
- 실제 최신 센서 state를 읽어 모델에 제공하고, 실행 직전 다시 읽어 조건·단위·가용성·정책을 검증한다. 모델이 조건을 true라고 판단했다는 이유만으로 실행하지 않는다.
- unknown/unavailable·stale 값·범위/단위 모호·제외 센서라면 수치를 추측하지 않는다. “덥네”만으로 임의 센서/기준/기기를 선택하지 않는다.
- 장기 감시·미래 예약·복잡한 중첩/루프는 이번 C 기본 조건과 구별해 계속 보류할 수 있다. 자동화 플랫폼을 새로 만들지 않는다.
- 조회/개인정보/불투명 메시지 작업을 무조건 최근 실행 shortcut으로 추천하지 않는다. 기존 제어 카드의 원문 재검증·새 UUID·연타 방지를 유지한다.

## 8. 공식 자료와 실제 지원 판정

이번 리뷰에서 확인한 공식 자료:

- [Vacuum](https://www.home-assistant.io/integrations/vacuum/): start/pause/return_to_base 등 공식 동작과 영역 mapping 제약.
- [Button](https://www.home-assistant.io/integrations/button/), [Sensor](https://www.home-assistant.io/integrations/sensor/): press 동작과 측정 상태의 구분.
- [Fan](https://www.home-assistant.io/integrations/fan/), [Cover](https://www.home-assistant.io/integrations/cover/), [Humidifier](https://www.home-assistant.io/integrations/humidifier/), [Media player](https://www.home-assistant.io/integrations/media_player/): 공식 기본 동작. 모든 엔티티가 모든 동작을 지원한다고 가정하지 않음.
- [Calendar](https://www.home-assistant.io/integrations/calendar/), [To-do](https://www.home-assistant.io/integrations/todo/), [Weather](https://www.home-assistant.io/integrations/weather/), [Service response data](https://developers.home-assistant.io/docs/dev_101_services/#response-data): 조회 응답을 실제로 읽어 반환하는 구조.

문서에 있다는 이유만으로 해당 테스트 Core/사용자 integration에 동작이 있다고 가정하지 않는다. Executor는 구현 시 지원 Core의 공식 소스/API와 runtime get_services/features/enum을 확인한다. 외부 payload/자유 문자열을 코드나 명령으로 실행하지 않는다.

## 9. VM 검증과 운영 인계 조건

**B/C까지 기본 기능이 연결되기 전에는 사용자에게 중간 빌드를 운영 HA에 설치해 달라고 요구하지 않는다.** 프로젝트 전용 VM과 가상 엔티티로 진행한다. 새 연결 정보/수동 매핑/YAML을 운영 사용자에게 요구하지 않는다. 테스트 VM에 개발 fixture YAML을 쓰는 것은 별개다.

- 기존 baseline과 `.local/test-resources.json`의 소유·포트·디스크를 확인한다. 기존 운영 VM은 기동/변경하지 않는다. 테스트 guest의 격리·임시 프로세스를 관리한다.
- B 각 도메인과 C query/response/text/condition을 제공하는 공식 demo/template/helper fixture를 준비한다. 기능이 부족한 경우 별도 테스트 integration을 **테스트 VM에서만** 사용하고 mock과 구분한다. 테스트용 action counter로 중복/비멱등 호출을 검증한다.
- 단순 단위 테스트 통과만으로 완료하지 않는다. 실제 HAOS 설치/업데이트, 실제 상태·attributes/조회 응답, discovery 변경, 정책/rename, 재시작, 중복 ID, timeout/실패를 확인한다.
- API는 실제 유효한 Microsoft Decision-1 키로만 호출한다. 만료·통신 문제면 mock/live를 구분해 가능한 VM 시험을 계속한다. Azure/다른 모델은 별도 자격/승인 없으면 mock으로 유지한다.
- 새 도메인 하나씩의 유효 명령, 미지원 기능/잘못된 값/제외 대상, 혼합 도메인 명령의 부분 지원 무전송, 단순 조건 true/false/판단 불가, 개인 상태 redaction, 다운로드 권한/파싱을 확인한다.
- 한 도메인에 여러 capability 조합을 두고, template 버튼의 첫 unknown, vacuum docked/paused, 미디어 idle/paused, 센서 문자열/단위 등 on/off와 다른 상태를 실제로 검사한다.
- 기존 A 동의어/색·온도/정책/저널/shortcut 회귀를 유지한다. 정상 거부는 별도로 기록하며 모델의 임계값을 낮춰 강제 통과시키지 않는다.
- AI/내부/HA 지연·호출 수·정상 거부·잘못된 실행을 분리해 보고한다. **특정 초 이내 실행을 엄격한 합격 기준으로 두지 않는다.**
- 실제 설치마다 HAOS가 업데이트를 인식하도록 이전 설치보다 높은 Dev 버전 식별자를 사용한다. 코드/config/package/Docker label/UI 버전을 일치시키고 기존 태그를 덮어쓰지 않는다.
- 중간 Dev 커밋/VM용 빌드는 자율적으로 가능하다. B/C 필수 범위를 갖춘 VM 검증 빌드와 로그 다운로드가 준비된 뒤 한 묶음으로 사용자 운영 시험을 지원한다. 운영 HA에 자동 배포하지 않는다.
- 검증 후 임시 VM/앱/이미지/전송 서버를 정리하고 재사용 baseline 상태를 기록한다. Main/안정 릴리스는 별도 명시 승인 전까지 변경하지 않는다.

## 10. 다음 Executor의 보고 및 인수 체크리스트

`FIX_02_REPORT.md`에는 F1~F4 및 B/C 도메인별 구현/테스트/실기동/보류 이유를 연결한다. F1만 고치거나 vacuum 하나만 추가하고 B/C 전체 완료로 보고하지 않는다. 실제 blocker가 있으면 완료하지 않은 기능을 명확히 표시하고 가능한 다른 구현/VM 검증을 계속한다.

- [ ] F1 swap/cycle rename 후 제외 유지; 실제 VM 최종 target 검증.
- [ ] F2 기존 hidden 기록까지 내용 제거, dedup 유지, export/shortcut 재노출 없음.
- [ ] 발견/지원/조회/허용 수와 미지원 사유가 실제 HA 환경과 일치.
- [ ] B 일반 가전 및 명시 실행 도메인의 실제 기능/부작용/정책 검증.
- [ ] C 센서 조회·응답 서비스·원문 제한 쓰기 및 단순 명시 조건의 실제 값 검증.
- [ ] 보류(ai_task/conversation/시스템 업데이트/위험 파일·외부 주소 동작)의 표시가 정직함.
- [ ] 다운로드 파일을 사용자 방식으로 받아 파싱하고 요청별 분석·redaction·관리 권한 검증.
- [ ] HAOS 설치/업데이트·회귀·재시작·API 오류·중복 요청·B/C 혼합 명령 검증.
- [ ] amd64/aarch64 build와 실제 실행 여부, Azure/mock/live 구분.
- [ ] 문서/지원표/CHANGELOG/버전/최종 Git 상태/자원 정리를 실제 결과로 갱신.
- [ ] B/C 묶음 전 사용자 운영 시험을 개발 검증의 필수 선행 조건으로 삼지 않음.

기존 PLAN, FIX_01 및 FIX_01_REPORT는 역사로 보존한다. 새 결과는 이 FIX_02의 보고서에 작성하고, 후속 Reviewer는 모든 문서와 실제 코드를 다시 대조한다.
