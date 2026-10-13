# FIX_01 — 단계 A 리뷰: 수정 후 재검토 필요

- 작성일: 2026-10-13
- 역할: Reviewer
- 대상: 같은 디렉터리의 `PLAN.md`, `REPORT.md`와 현재 작업 트리
- 기준 브랜치/HEAD: `dev` / `e13c4502049ddb35cd6b9ded31b1368df2d74804`
- 검토 빌드: 미커밋 `0.2.0-dev.1` 변경 23개 추적 파일. PLAN/REPORT는 현재 미추적 상태다.
- 기존 FIX 산출물: 없음. PLAN/REPORT를 보존하고 이 문서를 추가한다.
- 판정: **단계 A 완료로 인수하기 어렵다. 아래 수정을 수행하고 `FIX_01_REPORT.md`로 재검토를 요청한다.**

## 1. 리뷰 범위와 확인한 개선

REPORT가 명시한 단계 A를 검토했다. B/C의 모든 도메인이 이번 빌드에 없다는 사실 자체를 결함으로 판정하지 않는다. 반면 단계 A에 명시된 색온도, 안전한 설정 적용, 엔티티 정책, 상세 진단, 실제 기동 검증은 후속 B/C로 넘길 수 없다. 지연시간의 엄격한 합격 기준은 추가하지 않는다.

기본 options에 API/모델 항목을 추가한 방향, 사용자/관리자 화면 분리, 최근 성공 명령을 원문으로 재해석하는 카드, HA WebSocket service_data 지원은 타당하다. 기존 peer/origin 방어와 요청 ID 저널도 유지됐다.

검증 결과:

| 검증 | Reviewer 결과 |
| --- | --- |
| `uv run pytest -q` | 44 passed, 1 Starlette deprecation warning, 2.42s |
| `uv run ruff check addon/app tests scripts` | All checks passed |
| `uv run ruff format --check addon/app tests scripts` | 16 files already formatted |
| `node --check addon/app/fhc/static/app.js` | 통과 |
| `git diff --check` | CHANGELOG/DOCS/config.yaml/architecture.md의 EOF 빈 줄 경고 4건 |
| 추가 모의 실행 및 API 재현 | 아래 R1~R6 참조. 실제 HA/유료 API 호출 없음 |
| 브라우저 | 설치된 Playwright 1.63.0 / Chromium / localhost 일반 HTTP / API 모의 응답 |
| 이번 변경의 실제 HAOS/모델 호출 | Reviewer는 수행하지 않음. REPORT에도 이번 변경의 수행 증거 없음 |

컨테이너 빌드는 Executor 보고만 확인했으며 Reviewer가 재빌드하지 않았다. 기존 `docs/verification.md`의 0.1 결과를 이번 변경의 검증 결과로 인정하지 않는다.

## 2. R1 [P1] 관리자 모드는 화면만 분리되고 관리 API 권한 검사가 없다

위치: `addon/app/fhc/main.py:84`, `:147`, `:152`, `:214`, `:287`, `:292`.

middleware는 Ingress peer만 확인한다. 설정 조회/교체, 정책 변경, 상세 이력 조회/삭제 라우트에 HA 사용자 식별·관리 권한 검사가 없다. `panel_admin: true`는 유지되어 있으나 PLAN 7.2가 요구한 backend 권한 검증을 대체하지 않는다.

재현: 임시 Store, `TestClient(app, client=('172.30.32.2', 12345))`, standalone token 없음.

- 사용자 헤더가 전혀 없는 `GET /api/config` → **200**.
- `X-FHC-Request: 1`, 임의 `X-Remote-User-Id: unverified-user`로 `PUT /api/policy {"light": false}` → **200**, 정책 변경.

이는 인터넷에서 peer를 위조할 수 있다는 주장이 아니다. 신뢰된 프록시 경로를 지난 요청에서 backend가 브라우저 사용자의 관리 권한을 확인하지 않는다는 검증이다.

수정:

- 실제 Ingress가 덮어쓰는 사용자 식별 헤더와 HA 사용자 관리 권한의 연결을 테스트 HAOS에서 검증한다. 앱의 Supervisor 토큰 소유자 권한과 브라우저 사용자를 혼동하지 않는다.
- 모든 관리 API에 공통 backend 권한 검사를 적용한다. 헤더 누락/위조/알 수 없는 사용자/비관리자/권한 회수는 거부한다. 검증이 불가능하면 관리 API는 닫고 native Configuration을 안내한다.
- 사용자 모드 토글은 UI 상태로 유지한다. 새로운 필수 PIN이나 로그인 플랫폼은 도입하지 않는다.
- 실제 프록시 경로와 mock 양쪽에서 음성 사례를 검증한다.

## 3. R2 [P1] 그룹으로 엔티티 제외를 우회하고 rename 시 제외가 사라진다

위치: `catalog.py:60`, `:93`, `store.py:19`, `:114`, `main.py:235`, `engine.py:366`.

정책은 entity_id 문자열에만 묶이고, HA가 제공한 그룹 멤버십은 수집/전개하지 않는다. 따라서 그룹 엔티티는 허용된 채 제외된 멤버를 간접 조작한다.

모의 재현:

1. `light.group.attributes.entity_id = ['light.living', 'light.bedroom']`인 HA 조명 그룹을 추가한다.
2. `light.bedroom`을 정책에서 제외한다.
3. 모델 응답을 `light.group: turn_off`와 최종 승인으로 지정한다.
4. 결과는 **succeeded**, 호출은 **`light.turn_off(target=light.group)`**이다. 제외된 멤버가 포함된 그룹을 그대로 HA에 전달한다.

최종 검증 모델에도 멤버십/제외 관계가 제공되지 않아 이 우회를 판단할 자료가 없다. 또한 제외된 엔티티의 ID가 바뀌면 새 ID에 override가 없어 기본 허용된다.

수정:

- 알려진 HA 그룹은 cycle/중첩을 처리하며 leaf로 전개하고, 각 leaf에 도메인/엔티티 정책을 적용한다. 제외 멤버를 포함한 그룹 target을 직접 보내지 않는다. 동일 leaf 동일 동작은 중복 전송하지 않는다.
- 멤버십을 안전하게 확인할 수 없는 그룹의 실행은 보수적으로 제한한다. 이름으로 그룹/중복을 추측하지 않는다.
- 레지스트리의 안정 식별자 또는 검증된 rename 이벤트로 override를 유지한다. 삭제/ID 재사용으로 다른 엔티티에 권한을 잘못 이전하지 않는다.
- 정책 DTO의 entity override를 타입 검증하고 명시적 revision을 도입한다. 전체 계획과 실행 직전에 동일 revision/identity/허용 범위를 검증한다.
- 그룹 제외/중첩/순환/전체 조명/rename/delete/ID 재사용 테스트를 추가한다.

## 4. R3 [P1] 로컬 키워드가 동작 후보를 차단하고 복수 값을 첫 값으로 덮는다

위치: `engine.py:39–57`, `:109–143`, `:202–212`, `:265–300`.

전체 엔티티 전달은 유지했지만, **새 동작의 선택지는 로컬 한국어 키워드에 종속**됐다. 예를 들어 fan_only/dry/auto가 있는 climate에 다음 요청의 선택지를 조사했다.

- `에어컨 바람만 나오게 해줘` → fan_only 선택지 없음.
- `에어컨 제습으로 바꿔`, `에어컨 자동 모드로` → dry/auto 선택지 없음. 모두 none/on/off/mode_cool만 남음.
- `50프로`를 숫자 extractor는 읽지만 밝기 후보 gate에는 `프로`가 없어 해당 표현만으로는 밝기 선택지가 빠질 수 있다.

모델이 뜻을 이해해도 없는 선택지를 선택할 수 없다. 임계값을 낮추거나 동의어만 계속 추가해서 해결하지 않는다.

또한 extractor는 원문 전체의 첫 숫자/사전 순서 첫 색만 반환한다. 모의 최종 승인으로 `거실 에어컨 25도, 침실 에어컨 24도`를 실행하면 **두 기기에 모두 25.0**을 전달한다. `-25도`, `-20%`는 부호를 버려 **25.0, 20**으로 바뀐다. 한 엔티티당 choice 하나여서 `냉방 25도`, `빨간색 밝기 30%` 같은 복합 속성도 완전한 계획을 만들 수 없다.

이 재현은 ScriptedProvider가 최종 승인을 고정한 서버 경로 검사다. 실제 모델의 오실행률을 의미하지 않는다. 실제 모델이 잘못된 계획을 거부할 수 있지만, 잘못 추출된 값을 복구하거나 없는 동작을 만들어 줄 수는 없다.

수정:

- 지원 동작/enum 선택지는 HA capability와 adapter에서 구성한다. 문구 키워드가 없다는 이유로 지원 동작을 제거하지 않는다.
- literal은 부호·소수·단위·원문 위치를 보존해 후보 ID로 제공하고 모델이 대상/절/속성과 값을 연결하도록 한다. 전역 첫 값을 모든 기기에 적용하지 않는다.
- 한 대상에 필요한 여러 속성/순서를 표현하는 실행계획을 지원한다. 각 요청 절을 빠짐없이 검증하고 일부 속성만 실행하지 않는다.
- 정해진 7색 단어만 통과시키는 gate를 없애고 검증 가능한 색 후보를 의미 선택하게 한다. 미지원 값은 명확히 거부한다.
- 다중 온도/밝기/색, 반대 방향 상대 밝기, 부호/소수/단위, 여러 속성, held-out 한국어 표현의 mock 및 실제 Microsoft 모델 평가를 수행한다. 실패한 요청에 물리 호출이 없는지 확인한다.

## 5. R4 [P1] 엔티티별 기능 및 최신 매개변수 검증이 불충분하다

위치: `catalog.py:82–107`, `engine.py:115–120`, `:132–142`, `:291–300`, `:366–377`.

- `has_brightness`는 비어 있지 않은 color_modes 전체를 truthy로 취급한다. `supported_color_modes=['onoff']`만 있어도 밝기 선택지가 생성된다. 모의 실행에서 실제 `brightness_pct: 50` 호출까지 도달했다.
- climate의 domain service가 하나라도 있으면 catalog에 들어가며, on/off/temperature 후보에는 개별 `supported_features`나 해당 서비스 존재 여부의 교집합 검사가 없다.
- 온도는 min/max만 확인한다. `temperature_unit`, step, TARGET_TEMPERATURE와 RANGE, 현재 heat_cool 모드 차이를 처리하지 않는다. UI는 무조건 °C로 표시한다.
- fresh_state는 availability/state만 확인한다. 최신 feature/range/enum이 계획과 일치하는지 첫 전송 전에 다시 검증하지 않는다. version 이벤트만으로 fresh state와의 경쟁을 대신하지 않는다.

HA 공식 근거: [Climate entity](https://developers.home-assistant.io/docs/core/entity/climate/)의 단위·step·기능 구분, [Light entity](https://developers.home-assistant.io/docs/core/entity/light/)의 color mode별 기능 구분.

수정:

- 실행 가능한 서비스 ∩ 엔티티 capability ∩ 정책으로 후보를 만들고 최종 전송 전에 재검증한다. brightness용 onoff를 제외하고 hs/xy/rgb/color_temp 등은 공식 지원 규칙으로 구분한다.
- 온도 단위 변환, 명시적 단위 부재 처리, 범위/step, 단일/상하한 기능을 검증한다. 임의 반올림/clamp/기본 범위로 기능을 만들어내지 않는다.
- 모든 대상의 최신 상태/기능/값 검증을 마친 뒤 첫 부작용을 발생시킨다. 새 속성도 capability signature에 반영한다.
- 전체 매개변수가 같을 때만 no-op으로 판정한다. 현재 함수는 첫 brightness/rgb 일치만으로 반환하므로 복합 속성 지원 시 그대로 재사용하면 안 된다.
- unsupported light/climate, 서비스 누락, Fahrenheit, step 위반, RANGE-only, fresh capability 변경, 복합 no-op 테스트를 추가한다. FakeHA가 모든 서비스를 on/off 상태로만 갱신하는 현재 동작은 실제 매개변수 적용 증거가 아니다.

## 6. R5 [P1] 설정 원본·실패 처리·적용 경계가 계획과 다르다

위치: `config.py:104–182`, `main.py:152–170`.

- Supervisor 최신 옵션을 읽지 않고 runtime snapshot 전체로 options를 덮는다. native Configuration에서 먼저 수정한 키/옵션이 나중의 웹 UI 부분 저장으로 되돌아갈 수 있다.
- Supervisor 저장 뒤 `/data/options.json`까지 직접 덮어쓴다. PLAN 5.3에서 금지한 저장 방식이다. standalone의 파일 쓰기 실패도 삼킨다.
- 모의 `Path.write_text → PermissionError` 재현에서 `save_options`는 정상 변경 결과를 반환했으며 파일은 생성되지 않았다. 지속되지 않은 설정을 성공으로 표시한다.
- 설정 변경은 status=executing만 막는다. planning 중에는 공급자/모델을 바꿀 수 있고 동일 명령의 논리 단계/분할 batch가 서로 다른 설정으로 실행될 수 있다.
- API가 받는 rescan/history 옵션은 Provider에만 반영된다. HA의 rescan_hours와 Store.days/limit는 기존 값이어서 저장값과 실제 동작이 달라진다.

수정:

- 운영 모드에서는 Supervisor 자기 옵션을 읽어 변경 필드만 병합하고 공식 API로 저장한다. 앱 옵션 파일 직접 쓰기를 제거한다. standalone 파일 경로와 실패 처리는 명시적으로 분리한다.
- Supervisor/파일 저장 실패 시 실패를 반환하고 이전 runtime을 유지한다. 테스트 경로 환경변수만 있다는 이유로 운영 API 실패를 무시하지 않는다.
- 전체 active job과 설정 저장/적용을 공통 경계로 보호하거나 요청별 immutable 옵션 snapshot을 사용한다. 실행 중 모델이 바뀌지 않게 한다. 동시 저장의 lost update도 방지한다.
- 모든 변경 옵션을 해당 runtime 구성 요소에 일관되게 적용하거나 재시작 필요를 명시한다. 유효하지 않은 입력을 무시하고 200으로 성공 처리하지 않는다.
- Supervisor 오류/동시 수정/native 변경/키 교체·삭제·유지/Azure 단독/fallback/재시작 후 지속성/활성 planning 중 변경 테스트를 수행한다.

## 7. R6 [P1] 업그레이드가 새 도메인을 자동 허용한다

위치: `store.py:59–89`.

기존 DB 정책이 `light=false, switch=false`여도 migration에서 climate=true를 추가한다. 재현 결과는 `{'light': False, 'switch': False, 'climate': True}`였다. 기존 설치의 제어 범위를 새 버전 설치만으로 넓히지 말라는 PLAN 12절과 충돌한다.

또한 migration JSON 오류를 `except Exception: pass`로 무시한 뒤 버전을 2로 확정하며, 알 수 없는 미래 user_version을 명시적으로 거부하지 않는다. REPORT의 migration 검증 주장에 대응하는 테스트는 현재 tests에서 찾을 수 없다.

수정:

- 기존 설치의 신규 도메인은 기본 OFF로 이관하고 사용자가 명시적으로 허용하게 한다. 새 설치의 일반 도메인 기본값과 구별한다.
- migration을 검증/transaction으로 보호하고 실패 시 DB와 버전을 보존한다. 지원하지 않는 미래 버전은 명확하게 중단한다.
- 실제 이전 버전 DB fixture, 전체 차단 정책, 손상 정책, 실패 rollback, 미래 버전, 기존 request ID/저널 유지 테스트를 추가한다. REPORT의 주장과 증거를 맞춘다.

## 8. R7 [P2] 단계 A 필수 기능과 관리자 UX의 누락

- **색온도 실행이 없다.** `color_temp_kelvin`은 읽기만 하며 후보/변환/범위 검증/호출이 없다. PLAN 13/14의 단계 A 최소 범위에 포함된다. 공식 단위/범위와 supported_color_modes에 맞게 구현하고 실제 가상 light로 검증한다.
- `loadHistory()` (`static/app.js:341`)는 최근 8건의 총시간/서비스만 표시한다. reason, 단계별 지연, 모델/공급자, 판단·거부 단계 등의 상세 진단이 없다. 서버에도 판단 점수/모델 식별 기록이 빠져 있다. 관리자가 낮은 확신과 미지원 기능을 구분할 수 있도록 안전한 DTO로 제공한다. 키/전체 프롬프트/개인정보는 제외한다.
- API에는 키 삭제 flag가 있으나 UI에 삭제 컨트롤이 없으며 Azure endpoint/deployment는 빈 값 전송을 생략해 비울 수 없다. 유지/교체/명시적 삭제를 구별한다.
- `index.html:104–105`는 우선 공급자를 'OpenRouter 단독/Azure 단독'으로 표시하지만 `Options.configured()`는 다른 설정 공급자로 fallback한다. 실제 동작에 맞게 '우선'으로 표기한다.
- 공급자 탭 변경 후 `aria-checked`가 갱신되지 않는다. Playwright에서 Azure 패널이 보이는 상태에도 OpenRouter=true/Azure=false였다. 라디오의 키보드/선택 상태를 실제 화면과 일치시킨다.

위 누락은 동작하는 기본 사용자 화면을 다시 복잡하게 만드는 방식으로 해결하지 않는다. 관리자 화면에 배치한다. 엔티티 세부 목록에는 수백 개 환경의 이름/영역 검색을 추가한다.

## 9. R8 [P1 / 인수 검증] 실제 HAOS 업데이트와 모델 검증이 빠져 있다

REPORT 마지막의 '사용자 피드백에 따라 ... 실기동 확인 가능합니다'는 승인된 작업의 필수 검증을 사용자 피드백 이후로 미룬 것이다. 자동 테스트 44개와 docker build만으로 이번 단계 A를 완료했다고 할 수 없다.

수정 후 필수 검증:

1. 프로젝트 전용 HAOS에서 이전 Dev 설치 + 실제 기존 DB/옵션을 구성하고 새 빌드로 업그레이드한다. 새 설치도 별도로 확인한다. 운영 VM/기기는 건드리지 않는다.
2. native Configuration에서 API/모델 노출, 이전 키 유지, Azure 단독 mock 계약, 동적 관리자 폼과 Supervisor 옵션 일치, 권한 거부, 저장 후 재시작 지속성을 확인한다.
3. 가상 climate/light에서 HVAC 송풍/다른 지원 모드/온도/밝기/색/색온도를 실행하고 **HA attributes의 실제 변화**를 확인한다. 서비스 수락만으로 속성 적용을 주장하지 않는다.
4. 그룹 제외/rename/unsupported capability/잘못된 값/환경 변경 시 전송 없음, 중복 요청·네트워크 오류·HA 재시작 후 재전송 없음, 현재 정책으로 카드 재실행을 검증한다.
5. 사용자가 허용한 `microsoft/microsoft-decision-1`만 실제 호출해 한국어 정상/모호/미지원/복수 속성·값 사례를 평가한다. 다른 모델은 mock만 사용한다. 키가 만료됐으면 실패 이유와 mock/live 구분을 기록하고 실측한 것처럼 보고하지 않는다.
6. AI/내부/preflight/HA 전달 시간을 구분해 기록한다. **1초/특정 지연시간을 배포 합격 기준으로 삼지 않는다.** 정확한 명령 실행과 안전한 실패를 우선한다.
7. amd64/aarch64 빌드 결과를 각각 기록하고 ARM 실기동 여부는 별도로 명시한다. 기존 증거와 이번 증거를 구별한다.
8. `docs/testing.md`, `docs/verification.md` 등을 실제 결과로 갱신한다. REPORT를 덮어쓰지 않고 `FIX_01_REPORT.md`에 증거, 남은 미검증 항목, 최종 Git 상태, 임시 자원 정리를 기록한다.

## 10. 브라우저 QA 증거와 범위

Browser plugin not available. 기존 설치 Playwright를 사용했다. 모의 API를 갖춘 일시 localhost HTTP 서버로 **기본 진입 → 성공 바로가기 클릭 → 관리자 전환 → Azure 폼 전환**을 검사했고 서버/브라우저를 종료했다. 제품 소스는 수정하지 않았다.

- 페이지 URL: `http://127.0.0.1:39959/` (검증 종료 후 종료된 임시 서버).
- 뷰포트: desktop 1280×900, mobile 390×844.
- title `Fast Home Control`, 비어 있지 않은 화면, 프레임워크 오류 overlay 없음.
- 수집한 `pageerror` 없음. 별도 모든 console warning/network error 검사는 수행하지 않았으므로 완전 무오류로 확대 해석하지 않는다.
- 기본 진입 시 관리자 view 숨김 확인.
- 바로가기 1회 클릭으로 commands POST 1회 발생 확인.
- Azure 클릭 시 Azure 표시/OpenRouter 숨김 확인. aria-checked 불일치는 R7에 기록.
- 모바일 가로 overflow 없음. 스크린샷으로 폼 배치 확인.
- 실제 Ingress 인증, 실제 저장/실행, network retry, 모바일 실기기는 이 모의 QA의 검증 범위 밖이다.

Reviewer의 임시 스크린샷 (Git 밖, 장기 보관은 보장하지 않음):

- `/tmp/fhc-review-user-desktop.png`
- `/tmp/fhc-review-admin-desktop.png`
- `/tmp/fhc-review-admin-mobile.png`

## 11. Executor 작업 및 재검토 조건

R1~R6의 안전성/정확성 수정을 우선하고 R7의 단계 A 누락을 완성한 뒤 R8을 수행한다. 세부 구현 방법은 실제 코드/HA 계약에 맞춰 조정할 수 있으나 후보의 의미 해석을 로컬 키워드 gate로 대체하지 않는다. 모든 도메인을 이번 correction에 한꺼번에 넣을 필요는 없다.

`FIX_01_REPORT.md`에는 각 R 번호별 해결 파일/테스트/실기동 결과를 연결한다. 미해결 항목을 명시한다. git diff의 EOF 경고도 정리한다. 비밀키/토큰/원본 개인 CSV는 커밋하지 않는다. 이 리뷰는 Main 반영 또는 안정 릴리스 승인이 아니며, 이번 턴에는 코드 수정·push·release·VM 변경을 하지 않았다.
