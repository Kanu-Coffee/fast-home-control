# Fast Home Control: 설정·사용자 UX 개선 및 공식 도메인 확장

작성일: 2026-10-13 · 역할: Planner · 상태: 구현 인계용 계획

## 1. 목적과 작업 경계

사용자는 첫 Dev가 전체적으로 정상 작동한다고 보고했다. 다음 개발에서는 숨겨진 API 설정을 바로잡고, 사용자용 리모컨 화면과 관리자용 설정·진단 화면을 분리하며, 실제 HA가 제공하는 일반 가전 기능과 유용한 도메인을 확장한다.

**이번 요청은 PLAN 작성이다.** 이 문서 작성 단계에서 애플리케이션 코드·설정·운영 HA·VM을 변경하거나 새 릴리스를 만들지 않는다. Executor 역할을 맡은 작업자는 이 문서와 현재 Git·적용되는 AGENTS.md/GEMINI.md를 다시 읽고 구현한다. 특정 에이전트나 모델에 역할을 고정하지 않는다.

구현 시 유지할 원칙:

- HA 내부 프록시와 Supervisor 토큰을 이용한 Zero-Config. HA URL, LLAT, 기기 등록, 사용자 YAML 편집을 요구하지 않는다.
- **로컬 단어·정규식·top-K 검색으로 자연어 대상 후보를 누락시키지 않는다.** 허용 카탈로그 전체를 모델의 의미 판단에 먼저 제공한다.
- 공식 도메인/서비스와 엔티티별 기능을 활용한다. 기기별 커스텀 드라이버나 범용 에이전트 플랫폼을 만들지 않는다.
- 실행할 수 있는 다음 Dev를 단계적으로 배포한다. 지연은 측정·개선하되 1초/P95 같은 엄격한 출시 문턱을 만들지 않는다.
- 일반 가전과 최근 명령은 빠르게 실행한다. 모호한 대상, 잘못된 매개변수, 정책 위반은 실행하지 않는다.
- 개발·시험·릴리스는 Dev에서 진행한다. 이번 정상 동작 피드백을 Main 승격 승인으로 해석하지 않는다. Main/안정 릴리스는 별도의 명시 승인을 받는다.
- 기존 운영 VM과 사용자 환경을 수정하지 않는다. 실기동은 프로젝트 전용 HAOS와 가상 엔티티에서 수행한다.

## 2. 조사한 저장소 상태

계획 기준 Git 상태:

- 저장소: `/home/lee/projects/fast-home-control`
- 브랜치: `dev`
- HEAD: `e13c4502049ddb35cd6b9ded31b1368df2d74804`
- 배포 버전: `0.1.0-dev.1` / 태그 `v0.1.0-dev.1`
- 계획 작성 전 working tree는 깨끗했고 `.handoff/` 이력은 없었다. 따라서 신규 작업 번호는 `001`이다.
- 본 작업의 산출물은 이 `PLAN.md` 한 개다. `REPORT.md`나 기존 이력을 대신 작성하지 않는다.

현재 구현의 제약은 기능 위치와 함께 다음과 같다.

| 위치 | 현재 상태 / 변경 이유 |
|---|---|
| `addon/config.yaml`, `addon/translations/ko.yaml` | API 키가 optional schema에만 있고 기본 `options`에 없어 기본 폼에서 숨겨짐. 모델 설정 없음 |
| `addon/app/fhc/config.py` | 공급자 우선순위·Azure 오류 격리는 존재. 모델 선택·관리자 설정 저장/재적용은 없음 |
| `addon/app/fhc/provider.py` | OpenRouter 모델 ID가 Microsoft-Decision-1로 하드코딩. Decisions API와 확률 검증·질문 분할은 재사용 가능 |
| `addon/app/fhc/catalog.py` | `SUPPORTED`가 light/switch이고 양쪽 turn_on/turn_off를 모두 요구. 엔티티별 도구·기능·매개변수 메타데이터 없음 |
| `addon/app/fhc/engine.py` | 지원 여부 질문, 동작 선택, 최종 검증이 ON/OFF 전용. 상태 on/off 가정, 서비스 매개변수 없음 |
| `addon/app/fhc/ha.py` | `call()`이 domain/service/entity_id만 전송. light/switch에 한해 일부 메타데이터 변경으로 카탈로그 버전 갱신 |
| `addon/app/fhc/main.py` | Policy가 light/switch 두 bool. 엔티티 정책·조회 결과·바로가기·설정 편집 API 없음. 현재 인증은 Ingress peer 중심 |
| `addon/app/fhc/store.py` | SQLite `user_version=1`, 도메인 정책·요청 저널·이력 보관. 정책/이력 마이그레이션 필요 |
| `addon/app/fhc/static/{index.html,app.js,style.css}` | 연결 문구·진단·도메인 목록이 기본 화면에 노출. 예시는 정적이며 입력만 채움. 별도 실행 함수/모드/동적 바로가기 없음 |
| `tests/`, `scripts/evaluate_ha.py` | 기존 37개 테스트와 light/switch용 실제 모델 평가 fixture. 확장된 도구·정책·UI·계약을 추가 검증해야 함 |
| `docs/{architecture,testing,verification,releases}.md`, `.github/workflows/check.yml` | 기존 설계·실기동 기록·Dev 정책·amd64/aarch64 빌드를 유지하면서 갱신 |

Executor는 구현 시점의 diff를 기준으로 판단한다. 이 표가 이후 변경된 소스를 덮어쓸 근거가 되지 않는다.

## 3. 사용자 관측과 첨부 자료의 해석

사용자 로그의 중요 사례:

- “거실 조명 켜줘”가 low confidence로 거부된 후 “거실 불켜줘”는 실행됨: 표현에 따른 판단 차이를 재현할 회귀 사례다. 사용자 환경의 실제 엔티티 수와 같은 fixture에서 비교한다.
- “에어컨 켜줘 송풍모드” 거부: 현재 ON/OFF 전용 지원 여부 질문에 의한 미지원 거부와 부합한다. 새 climate 지원에서 반드시 포함할 사례다.
- 집 전체 조명 명령에 이미 요청한 상태와 실제 전송이 섞임: no-op 유지 및 사용자 결과 요약을 개선할 사례다.
- 제시된 성공 처리 시간은 약 3.8–5.5초, 미지원 거부 2.1초, 불확실 거부 3.2초였다. 참고 관측이며 통계적인 속도 기준이나 공급자 추론 시간으로 단정하지 않는다.
- 같은 영역에 개별 회로와 대표 조명처럼 보이는 이름이 함께 있다. 이름만 보고 중복 기기라고 판단하지 않는다. 실제 HA 그룹 멤버십이 있을 때만 그룹 전개와 중복 제거를 검토한다.

첨부 파일: `/home/lee/.codex/attachments/c7bf8f26-dd8b-4136-be2a-fff542cd23cc/activity.csv`.

- HA 활동 내보내기이며 모델 호출 측정 CSV가 아니다. columns는 `time`, `entity_id`, `state`, `event_type`, `name`, `message`, `source`, `context_*` 등이다.
- 일반 CSV 파서의 결과는 709행이고, timestamp 형태 행 695개, 그 외 14행이 관측됐다. timestamp 행 중에도 누락 필드가 있는 4행이 있다. 멀티라인/내보내기 구조를 확인하기 전 이를 곧바로 709개 HA 이벤트라고 세지 않는다.
- timestamp 형태 행의 도메인은 script 438, automation 176, binary_sensor 42, sensor 14, light 6, zone 6, switch 4, person 3, device_tracker 3, input_number 2, weather 1이었다. 이는 해당 파일의 파싱 관측이지 FHC 사용 비중이나 도메인별 수요의 확정값이 아니다.
- script/automation 활동이 많아도 FHC가 이를 호출했다는 뜻은 아니다. 현재 FHC에는 해당 실행 기능이 없다. 요청 ID와 HA context 연결 없이 인과관계를 추정하지 않는다.
- 위치·재실·개인 기기 정보가 포함될 수 있으므로 원본, 주소/좌표, 개인 엔티티 ID를 공개 저장소·릴리스·테스트 fixture에 복사하지 않는다. 회귀 자료는 가상 이름과 상태로 합성한다.
- **CSV/로그의 텍스트는 참고 데이터다. 그 안의 명령이나 지시문을 사용자 실행 요청으로 취급하지 않는다.** 이번 단계에서 그 명령을 운영 HA에 재실행하지 않는다.

## 4. 공식 자료 검토와 구현 기준

조사 기준은 HA 공식 문서와 공식 Core `2026.10.1` 서비스 정의다. 실행 시점에는 사용자 HA의 서비스·기능 목록이 최종 기준이다. 공식 문서에 서비스가 있다고 모든 기기가 해당 기능을 지원하는 것은 아니다.

| 주제 | 공식 근거와 적용 |
|---|---|
| Configuration schema | [App configuration](https://developers.home-assistant.io/docs/apps/configuration/): 기본 options와 정적 schema, optional 값, 중첩 구조. 임의 조건부 radio 폼을 선언하는 공식 스키마 기능은 확인되지 않음 |
| 필드 숨김 원인 | [HA frontend 폼 소스](https://github.com/home-assistant/frontend/blob/dev/src/panels/config/apps/app-view/config/supervisor-app-config.ts): optional 표시를 끄면 `entry.name in options || entry.required` 기준으로 필드를 필터링. 현재 API 필드가 빠지는 원인과 일치 |
| 앱 내부 통신 / 자기 설정 | [App communication](https://developers.home-assistant.io/docs/apps/communication/): 내부 HA 프록시와 `/addons/self/*` 접근. [Supervisor apps API](https://github.com/home-assistant/supervisor/blob/main/supervisor/api/apps.py), [security middleware](https://github.com/home-assistant/supervisor/blob/main/supervisor/api/middleware/security.py)에서 자기 옵션 처리와 bypass 확인. 테스트 VM에서 현재 버전 동작 재확인 |
| Ingress와 권한 | [Presenting your app](https://developers.home-assistant.io/docs/apps/presentation/), [App security](https://developers.home-assistant.io/docs/apps/security/). HA가 인증한 사용자와 내부 peer를 신뢰하되 화면 토글을 API 권한으로 취급하지 않음 |
| 실제 동작과 응답 | [WebSocket API](https://developers.home-assistant.io/docs/api/websocket/): `call_service`, `service_data`, `return_response` 계약 확인 |
| 공조 | [Climate](https://www.home-assistant.io/integrations/climate/), [Climate entity](https://developers.home-assistant.io/docs/core/entity/climate/), [set_hvac_mode](https://www.home-assistant.io/actions/climate.set_hvac_mode/): 엔티티별 HVAC 모드와 기능 사용 |
| 조명 | [Light](https://www.home-assistant.io/integrations/light/), [Light entity](https://developers.home-assistant.io/docs/core/entity/light/): `supported_color_modes`, 밝기·색·색온도 기능 구분 |
| Decision 모델 선택 | [OpenRouter Decisions SDK 계약](https://openrouter.ai/docs/client-sdks/python/sdks/decisions/README.md), [모델 목록 API](https://openrouter.ai/docs/api/api-reference/models/get-models), [Microsoft 모델](https://openrouter.ai/microsoft/microsoft-decision-1): 모델 ID는 요청 필드지만 일반 chat 모델이 동일한 Decisions 계약을 지원한다고 가정하지 않음 |
| 도메인별 동작 정의 | [공식 Core components](https://github.com/home-assistant/core/tree/2026.10.1/homeassistant/components)의 각 `<domain>/services.yaml`을 조회함. 아래 지원표는 이를 바탕으로 선정한 앱의 지원 범위이지 HA 전체 기능의 복제 목록이 아님 |

HA frontend/Supervisor `dev`/`main` 소스는 움직이는 참고 자료다. 구현 보고서에는 확인한 버전/commit과 실제 HAOS 결과를 남긴다. 404인 서비스 정의만으로 도메인 전체가 무용하다고 결론내리지 않는다.

## 5. 공급자 설정 UX와 설정 저장

### 5.1 기본 Configuration 탭: API 입력 숨김 해결

1. 기본 options에 API 입력 관련 키를 빈 기본값과 함께 명시하여 별도 “사용하지 않는 선택적 구성 옵션 표시” 없이 보이게 한다. OpenRouter 모델 필드도 기본 노출한다.
2. 빈 값은 “아직 이 공급자 미설정”으로 처리한다. OpenRouter 키를 필수로 만들거나 Azure 사용자가 OpenRouter 값을 채워야 앱을 시작할 수 있게 만들지 않는다.
3. Azure endpoint의 빈 기본값과 native `url` schema가 충돌하면 해당 입력은 `str`로 받고 애플리케이션에서 기존 HTTPS origin 검증을 유지한다. 빈 값과 잘못된 비어 있지 않은 값은 구분한다.
4. 기존 사용자 옵션이 새 기본값과 어떻게 병합되는지 실제 업그레이드로 검증한다. 새 설치만 필드가 보이고 기존 설치는 계속 숨겨지는 변경은 불충분하다.
5. 기존 키 이름과 기존 Azure 단독/양쪽 공급자 fallback 설정을 유지한다. 기본값 적용 시 기존 키를 빈 문자열로 덮어쓰지 않는다.

### 5.2 라디오/버튼 선택에 따른 동적 입력

요청한 “OpenRouter를 선택하면 키 입력, Azure를 선택하면 그 아래 Azure 입력”은 **관리자 모드의 공급자 설정 폼**에서 구현한다. 현재의 HA 기본 Configuration 탭에 없는 조건부 폼 기능을 지원하는 것처럼 약속하거나, 이를 위해 사용자 HA 프런트엔드를 패치하지 않는다.

- OpenRouter/Azure 선택 컨트롤은 라디오 또는 접근성 있는 segmented 버튼으로 제공한다. 선택된 공급자의 키·endpoint·배포·모델 입력을 그 아래에 보여준다.
- 우선 공급자 선택과 보조 공급자 설정을 구별한다. 선택하지 않은 공급자의 저장된 자격 증명을 삭제하지 않고 기존 fallback 의미를 유지한다. 양쪽을 설정한 경우 어느 공급자가 우선이고 보조인지 한눈에 알 수 있게 한다.
- 초기에는 OpenRouter를 추천 표시하고, Azure 선택만으로 설정·저장을 완료할 수 있게 한다.
- API가 전혀 없으면 첫 웹 접속에서 공급자 설정 진입을 바로 제공한다. 일반 사용자 화면에 상시 진단문을 붙이는 방식으로 대신하지 않는다.
- native Configuration은 계속 유효한 기본 설정 경로다. 동적 관리자 폼과 값이 엇갈리는 별도의 숨은 키 저장소를 만들지 않는다.

### 5.3 단일 설정 원본과 비밀정보 처리

- 공급자·모델·재탐색/보관 옵션의 원본은 **Supervisor 앱 옵션**으로 유지한다. 관리자 API가 서버에서 자기 앱 옵션을 읽고 변경할 필드만 병합해 자기 옵션 API에 저장한다.
- 공식 자기 앱 API를 우선 사용한다. 본 기능만을 위해 `manager/admin`, Docker API, host network 권한을 추가하지 않는다. 지원 버전에서 자기 API 동작을 POC로 확인하고 제한이 있으면 native Configuration 경로를 유지하며 사유를 보고한다. 무통보로 이중 저장소를 도입하지 않는다.
- 설정 API GET은 키 원문 대신 `configured` 여부를 반환한다. 관리자 입력에서 키 미입력은 기존 값 유지, 명시적 삭제는 별도 동작, 새 키 입력은 교체로 구분한다. 마스킹된 별표를 실제 키로 저장하지 않는다.
- 저장 실패 시 이전 설정을 유지한다. 실행 중의 설정 변경은 거부하거나 안전한 적용 경계까지 기다린다. 모델/공급자를 실행 도중 바꾸지 않는다.
- 저장 후 backend 옵션·공급자 클라이언트를 일관되게 재적용하고 UI에 적용 결과를 표시한다. native에서 바뀐 값은 앱 재시작 또는 검증된 감지 방식으로 재반영한다. 새 SDK가 필요하지 않으면 기존 httpx를 유지한다.
- 앱 옵션 파일을 임의로 덮어써서 Supervisor 화면과 분리하지 않는다. API 키·Bearer 토큰·원본 옵션을 오류/로그/내보내기에 넣지 않는다. 기존 설정 오류 redaction과 공급자별 오류 격리를 회귀 검증한다.

## 6. OpenRouter 모델 선택

- `openrouter_model`을 추가하고 기본값은 `microsoft/microsoft-decision-1`로 한다. 기존 설정에서 필드가 없으면 같은 기본값으로 동작한다.
- 관리자 UI에 모델 선택란을 제공한다. Microsoft 기본 항목과 고급 사용자용 모델 ID 입력을 우선 구현한다. 검증된 Decision 모델 목록은 나중에 확장 가능하게 한다.
- 모델 목록 API에 일반 chat 모델이 섞인다는 점을 고려한다. 공식적으로 확인된 Decisions 호환 속성/목록이 없으면 모델 전체를 Decision 드롭다운에 무작정 나열하지 않는다.
- 모델 변경은 명시적으로 저장한 경우에만 적용한다. 자동으로 다른 모델로 바꾸거나 chat completions/generative 도구 호출로 전환하지 않는다.
- 호환성 확인은 물리 동작 없는 작은 `noul`/`choice` 요청과 동일한 확률·응답 검증으로 수행한다. 스키마 불일치 모델은 실행에 사용하지 않는다. 모델 선택이 곧 모든 Decision 모델의 정확성 보증은 아니다.
- 선택 모델에 따라 질문/본문 budget이 다를 수 있다. 현재 8개 분할/40KB 제한을 공급자 전체의 보장 사양으로 간주하지 않는다. 검증한 기본 모델 정책을 유지하며 호환 모델별 차이를 작은 프로필로 관리한다.
- Azure는 기존 배포 이름이 모델 선택에 해당한다. OpenRouter 모델 ID를 Azure 요청에 섞지 않는다.
- 관리자 진단에 요청한 모델 ID와 응답에 있는 실제 모델 식별자, 사용 공급자를 안전하게 기록한다. 다른 모델의 성능을 Microsoft 실측으로 대체하지 않는다.
- 기존 임시 OpenRouter 키의 호출 승인은 **Microsoft-Decision-1에 한정**되어 있다. 이번 모델 선택 UI 요청을 다른 유료 모델의 실호출 승인으로 확대하지 않는다. 다른 모델은 모의 계약 검증을 하고 별도 승인/자격이 있을 때 실제 확인한다. 기본 모델도 키의 유효성을 확인하고 mock/live 결과를 구분한다.

## 7. 사용자 모드와 관리자 모드

### 7.1 사용자 모드: 기본 리모컨

일반 진입은 사용자 모드로 한다. 화면에는 다음만 둔다.

1. 짧은 제목, 자연어 입력창, 실행 버튼.
2. 간단한 진행/결과 영역. 성공 시 “거실 조명 2개에 요청했어요”, 조회 시 “거실 온도 25°C” 같은 짧은 값 중심 결과.
3. 실제 최근 성공 명령을 바탕으로 한 버튼 카드형 바로가기.
4. 눈에 띄되 과하지 않은 `사용자 / 관리자` 전환 컨트롤.

우측 상단 `Home Assistant 연결됨`, 입력 하단 `조명·스위치 ON/OFF 명령을 입력하세요`, 공급자 연결 표, 엔티티 수, API/카탈로그 안내, 세부 타이밍, 발견된 미지원 도메인 목록과 개발 버전 설명은 기본 화면에서 제거한다. 실제 문제로 실행할 수 없을 때만 “연결을 확인할 수 없어요”처럼 필요한 안내를 보여준다. 상시 안내를 없애는 것과 오류를 숨기는 것은 다르다.

- “요청 전달”과 “기기 동작 완료”를 동일시하지 않는다. 간결한 문구라도 물리 완료를 확인하지 않았으면 완료를 확정해 말하지 않는다.
- 전체 조명에서 12개 중 1개 전송/11개 no-op이면 일반 결과는 한두 줄로 요약한다. 엔티티별 상세는 관리자 모드에서 본다.
- 성공/미실행/부분 실행/실행 여부 미확정/조회 실패를 구별한다. 정상 on/off 가전 조작마다 확인 대화를 추가하지 않는다.
- 상태 조회 결과는 HA 데이터로 짧게 포맷한다. 장문의 설명 생성을 위한 추가 모델 호출을 기본으로 넣지 않는다.
- 데스크톱/모바일, 키보드, 터치, 스크린리더에서 실행과 모드 전환이 가능하게 한다. Ingress 상대 경로와 일반 HTTP 요청 ID fallback을 유지한다.
- 작은 UI를 위해 React·새 디자인 시스템·번들러 도입을 필수로 삼지 않는다. 다만 현재 긴 한 줄 JS는 변경 범위를 읽고 검증하기 쉽게 정리한다.

### 7.2 동적 최근 명령 바로가기

- 초기 6개 정도의 카드로 시작한다. 최근 성공한 실행 명령을 정확한 정규화 문자열 단위로 중복 제거하고 최신순으로 보여준다. 임의의 의미 병합으로 서로 다른 명령을 하나로 묶지 않는다.
- 정적 예시나 미지원 가전 명령을 실제 실행 가능한 바로가기인 것처럼 만들지 않는다. 이력이 없으면 간단한 빈 상태를 표시한다.
- 카드를 누르면 입력창 채우기나 별도 실행 버튼 없이 **같은 명령 실행 경로**로 즉시 요청한다. 폼과 카드가 공통 `executeCommand(text, requestId)` 흐름을 사용하게 한다.
- 이전 서비스 호출 결과나 entity ref를 재실행하지 않는다. 원문을 현재 환경·현재 정책으로 다시 해석하고 검증한다. 제거된 엔티티·바뀐 모드·허용 해제된 대상으로 과거 권한을 재사용하지 않는다.
- 카드 클릭은 새 사용자 요청이므로 새 UUID를 사용한다. 더블클릭/연타/통신 재시도는 하나의 진행 요청 ID를 공유하거나 busy guard로 막는다. 실패/미확정 요청을 자동 재전송하지 않는다.
- `rejected/failed/partial/uncertain`은 자동 추천에서 제외한다. no-op 성공은 사용자가 원하는 상태를 설정한 성공 이력으로 포함 가능하다. 조회, 임의 텍스트 전송, 고위험/불투명 실행은 초기 자동 추천에서 제외하고 별도 opt-in 여부를 후속으로 판단한다.
- 이력 삭제/보관 기간 만료는 추천에도 반영한다. 공유 HA에서 사용자 식별이 가능하면 사용자별로 추천을 분리하며, 이전 익명 이력의 처리 방식을 명시한다. 개인정보·위치 질의가 다른 사용자 카드로 섞이지 않게 한다.
- 후속 단계에서 고정/숨김을 추가할 수 있으나, 최근 명령을 자동 카드로 만들기 위해 사용자의 수동 등록을 요구하지 않는다.

### 7.3 관리자 모드: 설정과 진단

관리자 모드에는 공급자·모델 설정, 연결 상태, 전체/수동 재탐색, 제어 범위, 엔티티 상세 정책, 실행 상세 로그와 내보내기/이력 삭제를 모은다. 디버그 기능은 기본 사용자 화면에서 분리한다.

진단에는 요청 ID, 원문/요약, 선택 공급자·모델, 단계별 지연, 모델 호출 수, 지원 여부/후보/계획 검증 점수, 거부 단계와 이유, 대상·서비스·검증된 매개변수, no-op/전송/미확정, 가능하면 HA 서비스 응답의 context ID를 제공한다. 원문과 민감한 메시지/텍스트 값은 노출·보관 범위를 명시하고, 공유용 내보내기는 비밀정보와 개인 식별·위치 데이터를 제외한다. 전체 프롬프트와 전체 상태를 무조건 로그로 남기지 않는다.

**모드 전환은 UI 상태이며 인증 수단이 아니다.** 설정/정책 변경·상세 로그/내보내기 API는 backend에서 관리 권한을 확인한다. trusted Ingress의 사용자 식별 헤더와 실제 HA 사용자 권한의 연결을 POC로 검증한다. [HA config/auth 구현](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/config/auth.py)의 `config/auth/list` 등을 검토하되, Supervisor 토큰으로 조회한 `auth/current_user`를 브라우저 사용자의 관리자 여부로 착각하지 않는다. 사용자 헤더 위조/누락, 비관리자, 권한 회수에 대한 거부를 확인한다. 기존 `panel_admin: true`와 Ingress peer·요청 origin 방어를 유지하며, 권한 증명이 안 되면 관리 API를 열지 않는다. 새 로그인 플랫폼이나 별도 필수 PIN을 만들 필요는 없다.

## 8. 도메인·엔티티별 제어 범위

- 기본 관리자 화면은 도메인 단위 스위치를 유지한다. 각 도메인에 사용 가능한 기능과 허용 엔티티 수를 표시한다. 미지원, 조회 전용, 사용자가 비활성화한 상태를 한꺼번에 “미지원”으로 표기하지 않는다.
- 도메인 행의 `세부 설정`에서 이름/영역 검색, 엔티티별 제외/복원, 사용 가능한 동작과 조회 전용 여부를 조정한다. 일반 사용에 개별 등록은 요구하지 않는다.
- 최소 정책은 도메인 master 허용과 엔티티별 제외다. 조회/제어 권한을 나눌 경우 entity override는 상위 도메인의 허용 범위를 좁힐 수만 있게 한다. 도메인 OFF를 엔티티 ON으로 우회하지 않는다.
- 숨김·비활성·진단/설정 엔티티의 기본 제외를 유지한다. 진단 엔티티를 표시할 필요가 있으면 고급 화면에서 조회용으로 명시하고 기본 제어 후보로 자동 승격하지 않는다.
- entity_id 변경에도 정책을 유지하도록 HA 레지스트리 안정 식별자를 우선 사용한다. 제공되지 않는 환경은 검증된 레지스트리 정보/rename 이벤트로 이동을 처리한다. 삭제된 ID가 다른 엔티티에 재사용될 때 과거 허용을 잘못 이전하지 않는다. 이름으로 정책을 저장하지 않는다.
- 정책은 카탈로그 생성 전에 적용하고 실행 직전에도 재검증한다. 제거한 엔티티는 모델 입력·영역/전체 제어·바로가기·HA 최종 target에서 모두 제외한다.
- 정책 revision을 명시하고 계획 중 변경 시 실행을 중단한다. 실행 중 변경의 적용 경계도 일관되게 처리한다.
- HA가 멤버십을 제공하는 그룹은 재귀적으로 전개해 제외 멤버를 적용하고, 같은 명령에서 동일 leaf 동작이 중복되지 않게 한다. 서로 다른 매개변수나 상충 동작은 단순 dedup하지 않는다. 이름이 비슷하다는 이유로 가상의 그룹/중복을 만들지 않는다.
- script/scene/automation/button/helper가 내부적으로 다른 기기를 조작하는 경우 일반 target 정책만으로 전체 간접 효과를 보장할 수 없다. 이런 도메인은 기본 OFF/명시적 허용으로 처리하고 관리자에게 불투명한 간접 효과를 알려준다. 사용자가 요청하지 않은 스크립트/자동화를 모델이 우회 실행하게 만들지 않는다.

## 9. 공식 도메인 지원 범위와 우선순위

`A`: 다음 첫 확장 Dev의 핵심. `B`: 같은 확장 작업의 후속 Dev로 실제 제공. `C`: 가치가 있는 조회/구조화 작업으로 단계적 제공. `보류`: 지원 버튼을 가장해 노출하지 않으며 이유를 관리자 화면에 표시.

각 row의 동작은 HA에 실제 등록되고 엔티티가 지원할 때만 제공한다. 다음 표는 사용자 목록 33개를 모두 다루며, 기존 목표에 필요한 light/switch/fan/cover/scene도 포함한다.

| 도메인 | 범위 / 우선순위 | 제공할 동작·조회와 제한 |
|---|---|---|
| light | A 제어 | on/off 유지, 밝기·상대 밝기·RGB 계열 색·색온도, 지원 effect 선택. 지원 색 모드·범위가 없는 기능은 제외 |
| switch | A 제어 | on/off 유지. 재시도에 취약한 toggle을 자연어 켜기/끄기의 대체로 쓰지 않음 |
| climate | A 제어 | HVAC 모드, 온도, 전원. 이어서 fan/preset/swing/습도 중 제공되는 기능. 송풍은 HVAC `fan_only`와 fan speed를 구분 |
| fan | B 제어 | on/off, percentage, preset, oscillate, direction 중 지원 기능 |
| cover | B 제어 | open/close/stop/position, 지원 시 tilt. 차고문 등 민감한 device_class는 기본 제외하고 별도 보호 |
| humidifier | B 제어 | on/off, set_humidity, set_mode. 엔티티의 모드/습도 범위 검증 |
| vacuum | B 제어 | start/pause/stop/return_to_base, 지원 fan speed. 임의 send_command/params는 제외 |
| media_player | B 제어 | 전원, 재생/일시정지/정지, 볼륨/음소거, source, next/previous, sound mode 중 지원 기능. 임의 URL·playlist 삭제·join은 초기 제외 |
| input_boolean | B 제어 | on/off. 자동화 간접 효과가 있을 수 있으므로 helper 도메인은 기본 OFF, 관리자 도메인 허용 후 사용 |
| number / input_number | B 제어 | set_value, input_number의 increment/decrement. min/max/step/단위와 entity별 writable 여부 검증 |
| select / input_select | B 제어 | 실제 `options`에서 선택, next/previous/first/last. input_select.set_options/reload 등 구조 변경은 제외 |
| counter | B 제어 | increment/decrement/reset/set_value. 중복 방지 필수, reset은 명시 요청만. 임의 configure는 제공하지 않음 |
| button | B 제한 제어 | 명확히 지목한 `press`. 기본 OFF. update/reboot 등 부작용을 이름만으로 안전하다고 분류하지 않음 |
| script | B 제한 제어 | 명시한 기존 script 실행/중단. 기본 OFF. script 자체 생성/수정/reload와 임의 variables 전달은 초기 제외 |
| automation | B 제한 제어 | enable/disable, 명시적 기존 automation 실행. 기본 OFF. trigger의 `skip_condition`은 서버에서 false로 제한하며 건너뛰기 우회는 제공하지 않음. disable의 stop_actions 의미도 명시 |
| scene | B 제한 제어 | 기존 scene 활성화. 기본 OFF. 임의 scene.apply/create/delete는 제외 |
| sensor | C 조회 | 상태·단위·선정한 속성 조회. 일반 sensor에 set_state로 가짜 값을 쓰지 않음 |
| binary_sensor | C 조회 | 열린/닫힌, 감지/미감지 등을 device_class로 표시. 센서 자체를 켜거나 끄는 제어를 만들지 않음 |
| weather | C 조회 | 현재 상태와 지원하는 예보. get_forecasts 응답 사용, 없는 예보를 추정 생성하지 않음 |
| calendar | C 조회/제한 쓰기 | 우선 get_events, 이후 명시적 일정 생성. writable 지원 확인, 날짜/시간대/종일 일정/종료 조건과 모호한 일정 대상 처리 |
| todo | C 조회/제한 쓰기 | get_items, add/update/complete/remove 중 명시 요청. 중복 이름 항목은 UID로 식별하고 불명확하면 중단. 일괄 완료 항목 삭제는 초기 제외 |
| notify | C 제한 쓰기 | notify entity의 send_message 및 발견된 기존 notify 서비스 대상의 명시 메시지 전송. entity 없는 legacy 서비스는 별도 서비스 대상으로 모델링. 임의 data/외부 주소는 제외 |
| tts | C 제한 쓰기 | 발견된 TTS 엔진과 미디어 대상에 명시한 원문을 speak. 번역/문장 생성은 하지 않음. 외부 비용 가능성 때문에 기본 OFF, 임의 options/URL 전달 제외 |
| input_text | C 제한 쓰기 | 명시한 텍스트 set_value, 길이와 mode 검증. password 모드 엔티티는 AI 노출/로그에서 기본 제외 |
| input_datetime | C 제한 쓰기 | 지원하는 date/time/datetime/timestamp 중 정확한 값 설정. has_date/has_time과 HA 시간대 확인. 예약 실행 기능과 혼동하지 않음 |
| time | C 제한 쓰기 | 실제 writable time entity의 set_value. time 도메인 전체가 읽기 전용이라고 오분류하지 않음 |
| camera | C 조회/제한 제어 | 우선 상태 조회. 실제 지원하는 on/off·motion detection은 명시 opt-in 후 지원. 임의 파일경로 snapshot/record와 스트림 외부 전달은 초기 보류 |
| image | C 조회 / 파일 동작 보류 | 이미지 엔티티의 상태/갱신 정보 조회. 초기에는 snapshot 파일 생성·외부 분석을 제어 기능처럼 노출하지 않음 |
| device_tracker | C 조회 | 재실/위치명 조회만. 기본 OFF, 좌표는 필요한 경우에만 접근. `see`로 위치 조작하지 않음 |
| person | C 조회 | 재실 상태 조회만, 기본 OFF. person.reload를 생활 가전 제어로 노출하지 않음 |
| zone | C 조회 | 상태/인원 등 사용 가능한 정보 조회만, 위치 개인정보 기본 OFF. zone.reload/구역 편집은 제외 |
| sun | C 조회 | 현재 태양 상태/다음 일출·일몰 등 속성 조회. 강제로 상태 변경하지 않음 |
| event | C 조회 | 최근 이벤트와 시각 조회, 시점과 event_type 의미를 보존. 이벤트를 재발행하거나 button처럼 누르는 동작은 만들지 않음 |
| update | 보류 / 상태 조회만 C | 설치 가능 버전 등의 상태는 조회 가능. install/skip/clear_skipped는 시스템 유지보수로 자연어 일반 제어에 노출하지 않음 |
| ai_task | 보류 | 실제 generate_data/generate_image 서비스는 존재하지만 AI 재호출·추가 비용·개방형 생성은 빠른 가전 실행기의 현재 범위 밖. 필요 시 별도 명시 기능으로 설계 |
| conversation | 보류 | process/reload는 존재하지만 명령을 다른 conversation agent로 넘겨 본 앱의 허용 범위와 검증을 우회하지 않음 |

일반 가전의 새 도메인도 업그레이드 시 조용히 모두 ON으로 만들지 않는다. 기존 light/switch 정책을 보존하고, 신규 도메인은 관리자에게 발견·기능을 표시해 도메인 단위로 간편하게 허용할 수 있게 한다. script/button/automation/scene/helper와 외부 전송/개인 위치 도메인은 명시 opt-in을 유지한다. 도어락·보안 장치와 시스템 유지보수는 이번 확장에도 기본 제어 대상으로 포함하지 않는다.

## 10. 도구 카탈로그와 실행 모델 확장

### 10.1 작은 공식 동작 어댑터

`catalog.py`의 두 도메인 상수와 전역 ON/OFF 조건을, 도메인별 작은 동작 어댑터로 확장한다. 새 모듈 분리 여부와 이름은 Executor가 결정한다. 전체 HA SDK나 플러그인 플랫폼을 도입할 필요는 없다.

도구는 최소 다음을 표현한다: 서버 생성 ref, 안정 엔티티 식별, 이름/별칭/영역, 조회 또는 제어, domain/service, 허용 매개변수 schema, 지원 조건, no-op 판단 기준, 재시도 특성, 결과 표시 방식.

실제 제공 동작은 **앱의 지원 목록 ∩ 현재 HA 서비스 ∩ 엔티티 기능 ∩ 관리자 정책**이다. get_services에 이름이 있다는 이유로 전체 서비스/관리 작업/임의 payload를 AI에 실행 도구로 제공하지 않는다. 반대로 on/off 둘 다 없다는 이유로 button/number/select를 버리지 않는다. 동작 하나씩 가용성을 계산한다.

### 10.2 capability 동기화

- climate의 hvac_modes/fan_modes/preset_modes/swing_modes, min/max/step/단위, light의 supported_color_modes/색온도 범위/effect_list, select의 options, number의 min/max/step, 다른 도메인의 supported_features 등을 수집한다.
- 상태 값 변화와 기능 메타데이터 변화를 구별한다. 현재 `ha.py`의 light/switch 전용 version 변경을 확장하여 기능·선택지 변화도 계획을 무효화할 수 있게 한다. 일반 센서 업데이트마다 전체 카탈로그를 재구축하는 방식은 피한다.
- 전체 allowed metadata를 처음 의미 판단에 전달하되, 모든 센서 값·GPS·메시지 본문을 매번 전체 전송하지 않는다. 상세 기능과 현재 값은 선택된 관련 도구/질의에 한해 전달한다.
- 큰 카탈로그는 그룹/페이지를 모두 검사하는 분할을 사용하고 후보 누락을 피한다. 임의 top-K나 조용한 truncation으로 속도를 맞추지 않는다. 초과 시 실행하지 않고 관리자 진단에 이유를 남긴다.

### 10.3 상태/동작 결과의 타입화

- `ha.call()`은 검증된 `service_data`와 필요한 `return_response`를 지원하게 한다. WS 필드명과 반환 구조를 공식 계약에 맞춘다. 모델이 임의 URL·entity_id·service_data를 직접 실행하지 못하게 한다.
- state on/off 여부를 전역 preflight 조건으로 쓰지 않는다. 도메인별 유효 상태·availability·기능·매개변수 검증을 수행한다.
- 조회 전용 동작은 fresh HA state 또는 공식 읽기 서비스 응답을 사용한다. 상태 질의를 처리하기 위해 상태를 쓰거나 물리 조작을 하지 않는다.
- 응답을 제공하는 weather/calendar/todo 등의 서비스는 response를 읽어 실제 값으로 포맷한다. 임의 HA 템플릿 실행이나 생성형 대체 응답은 필요하지 않다.
- 현재 상태와 목표가 같으면 해당 **동작의 전체 매개변수** 기준으로 no-op을 판단한다. light가 이미 on이라도 색/밝기 변경은 실행해야 한다. climate가 이미 on이어도 HVAC 모드/온도 변경을 생략하지 않는다.
- press/increment/notify/script 실행은 일반적인 “이미 원하는 상태” 판정을 적용하지 않는다. 증분/외부 전송/불투명 작업의 타임아웃은 미확정으로 남기고 재전송하지 않는다.

## 11. Decision 모델로 매개변수와 복수 명령 처리

Microsoft-Decision-1은 자유 텍스트 실행계획·숫자·메시지를 생성하는 일반 LLM이 아니다. 다음 구조로 확장하고 실제 호출로 검증한다.

1. 허용된 전체 카탈로그와 원문으로 대상·동작 유형/지원 여부를 의미 판단한다. 기존 `VALID`와 최종 검증 프롬프트의 ON/OFF 하드코딩을 반드시 함께 바꾼다. 새 adapter만 추가하고 질문이 climate/color를 계속 거부하는 구현은 미완료다.
2. 모드는 엔티티가 보고한 enum, 색은 지원 색 표현/후보, 서비스는 adapter가 제공하는 동작에서 선택한다. `none/unsupported/ambiguous` 같은 기권 옵션을 둔다.
3. 숫자·단위·명시한 색 값·문자열은 작은 literal extractor로 원문의 값과 위치를 보존할 수 있다. 이 단계는 매개변수 후보 구성용이며 대상 기기/도메인을 제외하는 로컬 자연어 파서가 아니다. 자유형식 한국어의 대상·동작 의미 판단은 모델에 남긴다.
4. 값이 많으면 전체 숫자 범위를 choice로 거대하게 펼치지 않는다. 원문 literal 후보 + 실제 지원 enum/range를 결합하고 필요하면 제한된 계층 선택을 사용한다. 선택된 후보 ID를 서버가 정확한 값으로 변환한다. 숫자를 출력할 수 있다고 모델 특성을 가정하지 않는다.
5. 각 값과 대상/동작/절의 연결을 검증한다. “거실 25도, 침실 24도”의 값을 바꾸거나 한 기기 값을 모든 기기에 확장하지 않는다. 범위 밖 수치는 조용히 clamp/반올림하지 않고 처리 불가로 반환한다. 단위와 step 변환은 명시된 규칙으로 검증한다.
6. input_text/notify/tts/calendar/todo의 임의 텍스트는 원문에 실제 있는 span에서 가져온다. 모델이 새 문장을 생성한 것처럼 처리하지 않는다. 문구와 실행 절을 안전하게 나눌 수 없으면 그 요청을 실행하지 않고 간단한 입력 예시를 제공한다.
7. 실행계획은 동작·매개변수·순서·암묵적 부작용을 포함한 typed plan으로 구성한다. 최종 검증은 원문 전체와 대조하여 누락·추가 대상·잘못된 값·미지원 절을 확인한다.
8. 모든 대상의 정책·가용성·최신 기능/값을 조회한 뒤 첫 부작용을 발생시킨다. 부분 지원 요청은 기본적으로 실행 전에 전체 거부한다. 중간 실제 HA 실패로 일부만 전송되면 partial/uncertain을 정직하게 기록한다. HA 호출의 원자성을 가정하지 않는다.

중요한 구체 사례:

- **“에어컨 켜줘 송풍모드”**: 대상 climate의 hvac_modes에 `fan_only`가 있으면 `climate.set_hvac_mode(hvac_mode=fan_only)`로 처리할 수 있다. 불필요하게 전원을 켠 후 fan speed를 바꾸는 계획으로 만들지 않는다. 없으면 미지원이며 `fan_mode=fan_only`를 추정하지 않는다.
- “에어컨 25도로”: 실제 온도 단위/범위/step 및 단일/상하한 모드를 확인한다. heat_cool의 두 목표값을 임의로 생성하지 않는다.
- “거실 조명 빨간색”: color-capable light에 지원되는 색 매개변수를 넣는다. 색 없는 ON/OFF 조명까지 성공 처리하지 않는다. 영역 내 일부만 색을 지원할 때는 명시한 전체 요청의 미충족을 전송 전에 처리한다.
- “켜지 말고 색만 바꿔”: 표준 light.turn_on이 전원을 켜는 효과를 무시하지 않는다. 해당 엔티티에 실제 지원 방식이 없으면 거부한다.
- “조명 조금 어둡게”: 지원 밝기와 최신값을 사용해 문서화된 상대 변화(예: 기본 10%p)를 계획한다. 기존 on 상태라는 이유로 no-op 처리하지 않는다.
- “거실 불 끄고 에어컨 송풍모드”: 두 절을 모두 지원하는 계획을 만들고 한 절이 불가능하면 아무 것도 전송하지 않는다. 단순 접속사 regex 분할을 의미 해석의 대체로 쓰지 않는다.

성능은 기존 3개 논리 단계/질문 묶음을 출발점으로 측정한다. 실제 실험에서 호출 통합이 정확성을 유지하면 줄일 수 있으나, 단계 수나 내부 자료구조를 불필요하게 고정하지 않는다. 확신도 수치를 낮춰 몇 개 예시만 통과시키는 방식으로 회귀를 해결하지 않는다. 확률은 실제 가전 명령에 보정된 사고 확률이 아니며, 모델별 임계값 변경은 정상·모호·위험 음성 사례를 함께 평가하고 근거를 남긴다.

이번 작업은 무조건적인 도메인/매개변수 실행 확장에 집중한다. 조건부 제어는 기존 중기 목표로 유지하되, 준비되지 않은 조건·예약을 지원한 것처럼 일부만 실행하지 않는다. 필요하면 후속 별도 단계로 명시한다.

## 12. 저장소·API 마이그레이션

- SQLite migration은 실제 `user_version`을 읽고 순차적으로 수행한다. 현재처럼 항상 1로 설정하는 초기화 방식을 확장 버전에 그대로 사용하지 않는다. 실패 시 기존 DB를 보존하고 명확한 상태로 중단한다.
- 기존 light/switch bool 정책을 새 정책에 손실 없이 매핑한다. 신규 도메인의 자동 허용과 기존 명령 재전송이 발생하지 않게 한다.
- 기존 요청 ID, 저널, 미확정 상태, 이력 보관/삭제 의미를 유지한다. `succeeded`를 이유로 과거 요청을 startup에 재실행하지 않는다.
- 새 history 결과에 action kind, validated params, query result, no-op, provider/model과 phase diagnostics 등을 추가한다. 이전 결과에는 필드가 없을 수 있으므로 UI가 이를 허용한다.
- 기존 `/api/commands` UUID 기반 진입과 실행기 lock/busy 정책을 재사용한다. 엔티티 정책·설정·shortcut API는 별도 DTO로 비밀정보/원본 Supervisor 응답을 필터링한다.
- 새 정책 API가 필요하면 기존 Policy payload에 대한 호환 경로 또는 분명한 API version을 제공한다. UI와 backend가 다른 정책을 적용하는 중간 상태를 피한다.
- 조회와 제어 결과의 의미를 분리하고, 계획 전에 실패한 진단 정보도 누락 없이 남긴다. HA context를 반환받으면 FHC 요청과 연결하여 이후 활동 CSV를 근거 없이 추정하지 않게 한다.

## 13. 실행 단계와 Dev 배포 범위

### 단계 A — 설정/UX와 두 핵심 기능의 수직 구현

다음 확장 Dev(`0.2.0-dev.1`을 초기 후보로 하되 실제 범위에 따라 버전 조정)에 포함할 최소 묶음:

- 기본 Configuration에서 API/모델 입력이 처음부터 보임. 기존 키·Azure 단독·fallback 업그레이드 유지.
- 관리자 공급자 동적 폼과 안전한 자기 옵션 저장·적용, OpenRouter 모델 선택.
- 기본 사용자 화면 정리, 관리자 모드, 최근 성공 명령의 원클릭 카드.
- 도메인+엔티티 정책과 migration.
- 기존 ON/OFF 회귀 유지 + **climate 송풍/HVAC 모드·온도 + light 밝기·색·색온도**의 실제 실행.
- 상세 로그/짧은 결과/매개변수 검증, 실제 HAOS 설치/업데이트와 일반 HTTP 브라우저 시험.

이 묶음이 검증되면 전체 C 단계까지 기다리지 않고 Dev 배포 가능하다. 다만 UI만 바꾸고 climate/color를 계속 미지원으로 둔 빌드를 전체 개선 완료라고 보고하지 않는다.

### 단계 B — 일반 가전과 명시 실행 도메인

fan/cover/humidifier/vacuum/media_player, boolean/number/select 도우미, counter/button/script/automation/scene의 선정 동작을 추가한다. 도메인마다 runtime feature·정책·중복/불확실 처리 검증을 마친 순서대로 후속 Dev를 배포한다. 표의 B 도메인을 이유 없이 전부 “나중”으로 남기지 않는다.

### 단계 C — 조회와 원문 값 기반 작업

sensor/binary_sensor/weather, 개인 재실의 opt-in 조회, calendar/todo, input_text/input_datetime/time, notify/tts, 제한된 camera/image 상태/제어를 추가한다. 자유 텍스트·날짜 값의 원문 연결, response 서비스, 데이터 최소화·권한을 함께 검증한다. ai_task/conversation/update 설치 등 보류 기능은 일반 제어로 풀지 않는다.

각 Dev의 CHANGELOG와 지원 UI는 **그 버전에서 실제 검증한 기능**만 활성 지원으로 표시한다. phase 계획과 현재 구현 완료 범위를 혼동하지 않는다.

## 14. 검증 계획과 인수 기준

### 14.1 자동 검증

기존 테스트를 먼저 실행해 기준 상태를 확인한다. 구현 내용에 맞춰 의미 있는 검증을 추가한다.

```sh
uv run ruff check addon/app tests scripts
uv run ruff format --check addon/app tests scripts
uv run pytest -q
node --check addon/app/fhc/static/app.js
docker build -t fhc-check addon
```

가능하면 actionlint/hadolint, 변경 파일·커밋에 대한 redacted gitleaks 검사를 수행한다. 새 dependency가 필요하면 실제 필요성을 설명하고 lock과 Docker requirements 일치를 유지한다. 문서만 바뀐 이번 Planner 작업에 애플리케이션 테스트·VM 기동을 불필요하게 수행하지 않는다.

필수 테스트 묶음:

- 기존 키 숨김 재현 → native 기본 폼 노출, 새 설치/업그레이드/빈 키/Azure 단독/양쪽/한쪽 잘못된 설정.
- 자기 옵션 저장 병합, 저장 실패 복구, 빈 입력 유지/명시 삭제, masked 키 비노출, 모델 변경 적용과 비호환 응답 거부.
- 기본/관리자 화면 분리, 정상 사용자 화면 금지 문구 부재, API 권한 위조/비관리자 거부, 연결 오류의 간결한 안내.
- 바로가기 생성·정렬·중복 제거, 실제 원클릭 전송, 폼과 공통 경로, 연타·네트워크 중단·삭제·정책/엔티티 변경 후 재검증.
- 도메인 OFF 우선, 엔티티 제외/복원, rename/delete/ID 재사용, 그룹 leaf와 제외 정책, 조회 전용 도메인의 쓰기 차단.
- capability 조건부 도구 노출, 사라진 선택지/지원 기능의 실행 전 거부, 서비스/기능 변경 시 카탈로그 revision, 일반 상태 변화의 과도한 무효화 방지.
- 정확한 service_data/return_response, 색·모드·숫자·단위·범위·step·복수 값 binding. on 상태에서도 색/모드 변경 실행, 올바른 no-op.
- 일부 미지원 절이 있는 요청의 전송 전 전체 거부, 증분/press/메시지/스크립트의 응답 유실 시 재전송 금지, restart 저널 복구.
- 수십~수백 엔티티와 많은 read-only 상태 업데이트에서도 허용 카탈로그 누락/임의 top-K 없음. 큰 질문 분할과 명확한 크기 제한 처리.

### 14.2 실제 모델 평가

가상 fixture와 실제 OpenRouter Microsoft-Decision-1로 정상/미지원/모호/부정/조건/범위 위반을 함께 평가한다. ScriptedProvider 성공을 한국어 정확도 근거로 사용하지 않는다.

| 요청 | 확인할 결과 |
|---|---|
| 거실불 켜줘 / 거실 불켜줘 / 거실전등 켜줘 / 거실 조명 켜줘 | 같은 fixture에서 같은 의도·영역 light 대상. switch·다른 영역을 임의 추가하지 않음 |
| 화장실 복도등 켜줘 | 실제 표시명 “화장실 앞 복도등”과 의미/별칭 연결. 새 수동 mapping 불필요 |
| 집 전체 조명 꺼줘 | 엔티티 제외·그룹 중복·이미 off 상태를 반영. 일반 결과는 간단한 요약 |
| 에어컨 켜줘 송풍모드 | 단일 명확한 climate의 fan_only 실행. 해당 모드 없으면 전송 없음 |
| 거실 에어컨 냉방 25도로 / 거실 25도, 침실 24도 | 정확한 모드·단위·엔티티별 값 연결 |
| 거실 조명 빨간색으로 / 밝기 30% / 조금 어둡게 | 지원 기능만, 색 없는 기기와 범위 밖 값을 성공으로 처리하지 않음 |
| 거실 불 끄고 거실 에어컨 송풍으로 | 두 절 모두 검증한 뒤 실행. 한 절 미지원 시 무전송 |
| 커튼 반만 열어 / 청소기 충전대로 / 가습기 50% / 스피커 음소거 | 각 B adapter의 정확한 공식 서비스와 매개변수 |
| 조명 꺼져 있으면 켜 / 아무거나 실행 / 에어컨 100도 / 제외한 기기 켜 | 준비되지 않은 조건·모호·잘못된 값·정책 위반 거부 |
| 내일 오후 3시 일정 추가 / 스피커로 “퇴근했어요” 말해 | C 단계에서 원문·시간대·명시 대상 보존. 미완성 단계에서는 부분 실행 없음 |

부정문·인용문·카탈로그 이름의 지시문 삽입·중복 이름·능력 차이가 있는 같은 영역의 기기도 포함한다. 정상 거부율과 잘못된 실행을 구분해 기록한다. 수용할 오차율을 몇 개 기존 예시에 맞춰 임의로 정하지 않는다. 회귀나 미지원 항목이 남으면 재현 가능한 예시와 버전별 한계를 보고한다.

### 14.3 실제 HAOS와 브라우저

- `docs/testing.md`와 `.local/test-resources.json`을 참고해 프로젝트 전용 baseline을 사용한다. `.local`은 비밀 파일이 있을 수 있으므로 내용을 통째로 출력하지 않는다. 작업 시작 전 VM 소유·이름·디스크 경로를 확인한다.
- Supervisor 저장소 업데이트 → 설치/재빌드 → 기존 옵션·DB migration → Ingress 실제 화면을 검증한다. 기존 운영 VM은 기동/수정하지 않는다.
- climate/light 등 공식 demo 또는 가상 엔티티에서 실제 서비스 수락 **및 결과 상태/속성 변화**를 확인한다. mock만으로 동작 지원을 선언하지 않는다.
- 새로운 `fan_only`/select option 제공·제거, RGB 미지원 조명, number 범위/step 변경, 엔티티 이름/영역/허용 변경, HA 재시작/네트워크 오류를 재현한다.
- PC/390px 모바일/일반 HTTP origin에서 폼·모드 전환·비밀 설정·shortcut 클릭·간단한 결과·관리자 상세를 시험한다. 브라우저 콘솔 오류, 가로 넘침, 키보드/터치/접근성, Ingress prefix를 확인한다.
- 관리자/비관리자 identity 연결과 설정 API 거부를 실제 환경에서 검증한다. 확인 안 된 헤더를 보안 근거로 삼지 않는다.
- 다른 모델·Azure live 자격이 없으면 mock/live 검증을 구분한다. 사용자에게 운영 기기 시험을 요구해 개발 검증을 대체하지 않는다.
- model API 왕복/호출 수, 앱 처리, 사전 조회, 첫 HA 전송, HA 응답, UI 체감 시간을 구분해 기록한다. 이미 원하는 상태와 실제 전송 사례도 분리한다. **속도 수치는 출시를 막는 고정 기준이 아니다.**
- 필요한 테스트 뒤 프로젝트 임시 프로세스/VM을 종료하고 재사용 baseline과 삭제한 임시 자원을 기록한다.

### 14.4 단계 A 인수 체크리스트

- [ ] optional 표시를 켜지 않아도 API/모델 입력이 보이고, 기존 Azure 단독 설정이 업그레이드 후 동작한다.
- [ ] 관리자 공급자 선택에 따라 입력 폼이 바뀌며, native 옵션과 일관되게 저장·적용된다.
- [ ] 기본 사용자 화면에서 두 지적 시스템 문구와 상시 진단 영역이 사라진다.
- [ ] 최근 성공 명령 카드가 자동 생성되고 한 번 누르면 현재 정책으로 실행된다.
- [ ] 관리자 모드에서 설정·도메인·엔티티 정책·단계별 실행 진단을 사용할 수 있다.
- [ ] climate 송풍/HVAC 모드·온도, light 밝기·색·색온도를 실제 가상 HA 기기로 검증한다.
- [ ] capability 미지원/모호/제외/잘못된 값에는 전송이 없고, 기존 ON/OFF는 회귀하지 않는다.
- [ ] 새 설치와 기존 DB/옵션 업그레이드, 재시작/타임아웃/중복 요청을 검증한다.
- [ ] 실제 모델 평가와 mock 검증을 구분하고 정상 거부·오실행·지연을 정직하게 보고한다.
- [ ] amd64/aarch64 빌드가 통과하며 ARM 실기동 여부는 별도로 표시한다.
- [ ] 지원표와 CHANGELOG가 실제 제공 범위를 반영하고 사용자에게 개별 YAML/기기 mapping을 요구하지 않는다.

## 15. 변경 파일 가이드와 인계 산출물

Executor의 예상 변경 영역은 2절 표의 파일과 필요 시 작은 adapter/configuration/auth/shortcut 모듈이다. 내부 자료구조·모듈명을 본 계획으로 과도하게 제한하지 않는다. 변경 범위가 실제 저장소에 맞게 달라지면 목적·안전 조건을 유지하고 REPORT에 이유를 남긴다.

필수 문서/운영 반영:

- README / addon DOCS / CHANGELOG: 기본 API 설정, 관리자 동적 폼, 모델 선택, 새 지원 범위·제약, 원클릭 바로가기, 고급 엔티티 정책.
- architecture: ON/OFF 전용 설계를 실제 typed action/조회/매개변수·정책 revision 설계로 갱신.
- verification/testing: 실제 명령·HA 상태 변화·모델/환경 버전·지연·미검증 항목·운영 자원 정리 기록. 원본 사용자 CSV/개인정보 제외.
- version: 코드·config·패키지/문서의 버전을 일관되게 변경하고 기존 Dev 태그를 덮어쓰지 않음.
- Dev 릴리스: 검증된 변경을 단계별 prerelease로 배포 가능. 실제 사용자 운영 확인 전 Main으로 자동 승격하지 않음.

완료 시 같은 작업 디렉터리에 **`REPORT.md`**를 새로 작성한다. objective/구현 범위, 기준/최종 Git 상태, 주요 파일, 실행한 명령과 결과, mock/live/실기동 구분, 계획 변경 이유, 배포 정보, 남은 제약·위험·자원 상태를 포함한다. 본 PLAN을 결과에 맞춰 덮어쓰지 않는다.

Reviewer는 PLAN/REPORT와 실제 Git diff·실행 증거를 함께 검토한다. 수정이 필요하면 다음 `FIX_01.md`부터 순서대로 생성하고 Executor는 해당 `FIX_01_REPORT.md`로 결과를 남긴다. 이미 완료된 보고서를 덮어쓰거나 기존 task 번호/문서를 재사용하지 않는다.
