# FIX_07 — 실제 자연어 경로 복구·설치 검증 및 잔여 값 누락

작성일: 2026-10-14 · 역할: Reviewer · 판정: **수정 필요. FIX_06의 backend 보정은 대체로 인정하되 B/C 완료·배포 검증은 미완료**

## 1. 범위와 확인한 진전

기준 HEAD dev `5301737`, 이후 작업 트리의 20개 변경 파일, 미추적 FIX_02~06_REPORT 및 scripts/verify_live_bc.py를 포함해 검토했다. PLAN 및 기존 FIX/보고서의 요구를 계속 적용한다. 이번 Reviewer는 제품 코드·VM·운영 설정·Main·릴리스를 변경하지 않았다.

재실행: pytest **109 passed**, 기존 Starlette warning 1개. Ruff check/format(20 files), JS syntax, git diff --check 통과. `.local/fix06-live*.json`의 결과/모드/레이어를 대조했다. 비밀 파일 원문은 출력하지 않았다.

FIX_06 R1~R4의 주요 보정은 인정한다: 실제 calendar events dict/ISO 문자열 처리, 시간 일정 start/end pair, 임의 duration 삭제, todo UID의 첫 write 전 preflight 해석 및 환경 재검사, 3-way condition_class와 단위 모호성 거부. 기존 password/read 정책/TTS secondary/저널/rename 보정도 유지한다.

실제 HA 서비스 계약 검증도 이전보다 실질적이다. 저장 증거는 **service_contract 8개 + safety_negative 1개**, 총 9개 assertion 통과다. 보고서의 “service_contract 9/9” 표현은 두 레이어를 합친 것이므로 다음 보고서에서 구분한다. 모의 모델을 사용한 서비스 실행과 실모델 자연어 성공을 분리한 방향은 맞다.

## 2. R1 [P1] 정상 B/C 자연어 경로의 실패를 단순 후속 튜닝으로 미루지 않는다

위치: `engine.py` scope/actions/verification, `actions.py:options_for`, `scripts/verify_live_bc.py:run_model`, FIX_06_REPORT §6~8.

최신 실모델 evidence의 Microsoft 2/7, Jev 1/7을 직접 확인했다. 통과 사례는 TTS 모호 거부 및 todo 부재 거부뿐이다. 정상 5개(조건 false, TTS 지정, 달력, 날씨, 공조)는 **두 모델 모두 성공 0/5**다. 동작 계약이 실제 HA에서 통과했다고 자연어 리모컨 기능이 완료된 것은 아니다. 이번 결과만으로 기존 A 전체가 깨졌다고 단정하지는 않는다.

확인을 위해 Reviewer가 기존 허용 키로 두 모델을 추가 시험했다. **실제 OpenRouter + FakeHA**(물리/VM 호출 없음), 합성 이름·영역의 기존 A fixture에서 `거실불 꺼줘` 1개씩, 3 HTTP calls/model:

| 모델 | 반환 snapshot | 결과 | 관측 total |
| --- | --- | --- | --- |
| microsoft/microsoft-decision-1 | microsoft/microsoft-decision-1-20261009 | succeeded, FakeHA light.living turn_off 1건 | 3697ms |
| typesafe/jev-1.13 | typesafe/jev-1.13-20260917 | rejected / plan_not_verified, 전송 0건 | 1870ms |

이 단일 smoke test는 API/기존 조명 경로 확인이며 실제 HAOS 검증이나 광범위 정확도 보장이 아니다. 엄격한 시간 합격선도 아니다.

다음 Executor 작업:

- 정상 B/C 명령의 단계별 질문/선택/확신도/최종 계획을 안전한 진단으로 조사한다. query_state와 get_events/get_forecasts를 독립 선택시켜 같은 조회에서 conflicting_actions를 만들고 있는 구조를 보정한다. 상호 배타적 의미는 하나의 선택으로 표현하거나 동등한 단순 구조로 정리하되 실제 상충/추가 대상은 계속 거부한다.
- 관련 동작 및 필요한 속성이 scope/choices/verification에 일관되게 설명되는지 확인한다. 조건/출력 장치 등 보조 대상도 전체 허용 metadata의 의미 판단을 유지한다. 정규식/단어/top-K로 대상 후보를 제거하거나 모델 임계값을 낮춰 억지 통과시키지 않는다.
- 영문 demo 이름 때문에 모호하면 테스트 VM에 명확한 한국어 이름/별칭/영역을 제공한다. 이는 테스트 fixture 작업이며 운영 사용자의 수동 매핑을 요구하는 것이 아니다. 정상 단일 대상/복수 속성 명령에서 실제 모델→HA 실행/응답의 경로를 먼저 성립시킨다.
- Microsoft를 기본으로 기존 조명·공조 및 확장 대표 명령을 실제 HA에서 성공시키고, Jev는 동일 정답으로 비교 결과를 기록한다. Jev의 모든 정상 사례 통과나 100% 한국어 정확도를 새 배포 기준으로 요구하지 않는다. 안전 거부와 잘못된 실행은 별개로 보고한다.
- 테스트 double만 성공하는 기능을 “구현 완료, 모델 튜닝은 후속”으로 계속 인계하지 않는다. 사용자 목표는 모델을 붙여 명령을 실제 실행하는 MVP다. 몇 초가 걸려도 기능이 작동하면 된다는 기존 방침을 유지한다.

## 3. R2 [P2] 설치 검증을 막고 있는 승인 해석을 바로잡는다

FIX_06_REPORT §7은 dev 소스 commit/push를 “사용자 승인 행위”로 보고 dev.8 설치를 수행하지 않았다. 그러나 사용자는 초기 프로젝트에서 **Dev의 코드 변경·커밋·Push·테스트 VM 구성·Dev 릴리스**를 이미 명시적으로 자율 승인했고, 계획도 승인했다. Main/안정 릴리스만 별도 승인이 필요하다. 새로운 Dev commit/push 확인을 사용자에게 다시 요청할 이유가 없다.

다음 Executor는:

- 자신의 구현·보고서·시험 파일을 점검하고 비밀 검사/필수 CI를 거쳐 **Dev에 커밋·Push**한다. 공개되어야 하는 fixture/자동화/검증 문서도 함께 정리한다. Reviewer가 문서만 커밋한 것은 Executor의 Dev 코드 커밋 금지를 뜻하지 않는다.
- 프로젝트 소유 HAOS에서 공식 저장소 업데이트 경로로 실제 addon을 설치/업데이트한다. 현재 VM dev.7, 미설치 dev.8이므로 dev.8 또는 실제 설치 상태보다 높은 버전을 선택하고 모든 표기를 맞춘다. 이미 게시된 tag를 덮어쓰지 않는다.
- Ingress의 사용자 실행, 관리자 읽기/쓰기 토글·세부 entity 정책, 실제 ZIP 다운로드/파싱·권한·비밀 제거, 재시작·정책 보존을 설치된 앱에서 확인한다. 호스트 Engine→HA 시험을 addon 설치 검증과 구분한다.
- 필요한 Dev prerelease는 기존 승인 범위에서 진행할 수 있다. Main/안정 릴리스/운영 HA 자동 업데이트는 하지 않는다. 비문서적 Supervisor 저장소 수술이나 기존 운영 VM 변경은 필요 없다.

현재 미설치 사실을 blocker로 반복 기록하며 멈추는 대신, 이 승인 범위에서 설치 검증까지 진행한다.

## 4. R3 [P2] 시간·날짜 literal의 일부만 파싱하여 다른 값으로 쓴다

위치: `actions.py:TIME_RE/CLOCK_RE/MONTH_DAY_RE`, `temporal_tokens`, input_datetime binding.

Reviewer 직접 재현(고정 now=2026-10-14 12:00 Asia/Seoul, has_date+has_time helper; 실제 HA 전송 없음):

| 원문 | 생성 token/쓰기 payload |
| --- | --- |
| `오후 8:30으로 설정` | '8:30'만 읽어 **time='08:30:00'**, 오후 정보 누락 |
| `2028년 10월 20일로 설정` | '10월 20일'만 읽어 **date='2026-10-20'**, 명시 연도 누락 |
| `오후 8시 75분으로 설정` | 잘못된 분을 버리고 '오후 8시'만 읽어 **time='20:00:00'** |

부분 파싱 값에 모델이 최종 거부할 수도 있지만, backend가 원문과 다른 값을 유효 후보/계획으로 만들면 안 된다. typed literal ID만 사용한다고 전체 시각·날짜가 보존되는 것은 아니다.

수정/검증: 오전/오후+HH:MM, 명시 연도/월/일, 잘못된 분·날짜를 하나의 literal span으로 검증한다. 지원하지 않는 표현은 값을 잘라 쓰지 말고 전송 전 거부한다. 날짜+시간 helper, 경계(오전/오후12시, 연말), 유효하지 않은 날짜/시간 및 explicit year 회귀를 추가하고 실제 helper 값을 read-back한다. 로컬 문자 추출 보조는 허용하지만 대상·동작 의미 판단을 regex로 되돌리지 않는다.

## 5. R4 [P2] 전원 켜기와 속성 변경을 함께 선택하면 전원이 누락된다

위치: `actions.py:make_actions` fan/humidifier/media_player의 `if not actions and power` 분기.

직접 action 생성 재현:

- fan power=turn_on + oscillate_on → **oscillate만**.
- humidifier power=turn_on + mode=auto → **set_mode만**.
- media_player power=turn_on + volume=20% → **volume_set만**.

다른 속성 action이 생기면 명시적으로 선택한 turn_on을 버린다. 각 속성 서비스에 전원 켜짐이 항상 보장되는 계약도 없다. 이전 복수 속성 보정(fan percentage+oscillate)은 개선됐지만 explicit power와의 조합은 남았다.

수정/검증: 공식 서비스 하나가 두 효과를 보장하면 묶고, 아니면 순서가 명시된 turn_on+속성 actions를 보존한다. 환경/기능에 맞는 실행 순서와 no-op을 적용하고 상충 turn_off 요청은 계속 전송 전 거부한다. 선택된 모든 속성이 계획 effect에 포함됨을 backend에서 확인한다. OFF 상태 fixture에 `켜고 회전`, `켜고 자동 모드`, `켜고 볼륨`을 주어 실제 전원과 속성이 모두 달라지는지 검증한다. final model이 누락을 잡아 주기만 기대하지 않는다.

## 6. 검증·보고 및 다음 인계

- 다음 문서는 **FIX_07_REPORT.md**다. 기존 문서/보고서는 덮어쓰지 않는다. FIX_06의 인정된 보정과 실패 예시를 반복 수정하지 말고 R1~R4 및 설치 검증에 집중한다.
- 실제 service_contract 8건/safety_negative 1건, real model 정상 성공/안전 거부를 분리 집계한다. 실모델 2/7·1/7을 정상 기능 성공률로 표현하지 않는다. 유형별 분모, requested/returned model, 코드/fixture/프롬프트 버전, 단계·호출·지연을 기록한다.
- B/C 필수 표 대비 남은 legacy notify/time/미검증 도메인 등은 지원 UI/문서/CHANGELOG와 일치시킨다. 미완 기능을 등록 개수나 scripted 실행만으로 완료라고 표시하지 않는다. 이번 리뷰는 새로운 대규모 기능 범위나 엄격한 지연 목표를 추가하지 않는다.
- B/C 묶음이 실제 설치형 앱에서 검증되기 전 사용자 운영 시험을 요청하지 않는다. 프로젝트 소유 VM과 가상 엔티티로 계속 진행하고 소유·격리·자원 정리를 유지한다.
- 개발·Dev Push/시험·prerelease는 기존 승인 범위로 자율 진행한다. Main/안정 릴리스는 사용자 별도 명시 승인 이후다.
