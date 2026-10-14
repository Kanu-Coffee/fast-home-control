# 0.2.0-dev.10 — UI/UX 편의성 개선, 동작 교정 및 공식 브랜드 아이콘 통일 (2026-10-14)
- 자동 테스트 116개 통과. Ruff check/format (21 files), JS 구문 (`node --check`), `git diff --check`, `actionlint` (.github/workflows/check.yml), `hadolint` (addon/Dockerfile) 통과.
- **UI/UX 개선 및 브라우저 동작 검증 (`tests/test_browser_ui.py`)**:
  - **스위치 정렬 및 터치 영역 (R6)**: `.domain-summary` 및 `.entity-row`에서 제어와 조회 스위치를 각각 독립된 78px 폭의 `.toggle-group`으로 패키징. `.toggle`의 bounding box를 측정하여 가로 44px, 세로 44px의 터치 영역을 확보하고 내부 `::before` 가상 요소로 44×24px 시각 디자인을 유지. 제어 열과 조회 열의 X 좌표가 일치함을 확인.
  - **정책 저장 생명주기 및 경합 방어 (FIX_02 R2, R1)**: 도메인 정책 요청 세대 카운터(`domainsRequestSeq`)를 적용하여 느린 이전 GET 응답이 최신 정책 상태를 덮어쓰지 않도록 폐기. 정책 PUT 실행부터 후속 최신 GET 로드 완료 시점(`finally`)까지 `isPolicySaving = true`를 유지하여 토글 연타나 경합 중 비정상 토글 상태 방지. 특수문자 따옴표/대괄호가 포함된 기기 이름에서도 `[data-entity-id]` 기반으로 포커스를 복원함을 확인.
  - **엔티티 검색 중 아코디언 조작 및 포커스 (R5)**: 검색어 입력 시 일치 항목을 자동 표시하되, 검색 중 사용자가 '목록 닫기'를 누르면 아코디언이 `aria-expanded="false"`로 닫히고 키보드 포커스가 `#toggle-btn-{domain}`에 유지됨을 확인. Space/Enter 키보드 토글 및 검색어 초기화 시 기본 펼침 상태 복원을 검증.
  - **OpenRouter 모델 드롭다운 및 직접 입력 초안 보존 (R4)**: `cfg-openrouter-model-select` 네이티브 셀렉트에서 '직접 입력' 선택 후 작성한 초안 문자열(`customModelDraft`)이 후보 프리셋(Microsoft, Jev 1.13)을 오가는 동안 덮어씌워지지 않고 보존됨을 확인. 실제 POST 저장 및 재로드 시 저장값 반영 검증.
  - **상세 실행 기록 변경 감지 및 열람 위치 보존 (FIX_02 R1, R3)**: `/api/history` 50건 렌더링. 진단 지문(fingerprint)에 `providers`, `phase`, `model_trace`, `timings_ms`, `actions`를 포함하여 동일 상태 코드 내 진단 및 공급자 상태 갱신을 누락 없이 감지. 갱신 시 `<details>` 열림 상태와 `<pre>` 내부 스크롤 유지. `getBoundingClientRect()` 기반 컨테이너-자식 상대 좌표 계산으로 선행 행 확장 또는 상단 새 항목 추가 시에도 뷰포트 내 기준 카드의 상대 위치 안정 유지 및 `focus({ preventScroll: true })` 적용.
  - **실제 명령 실패 처리 및 대기 중 입력 보존 (Section 3 & 4)**: `page.evaluate()` 편법 없이 실제 route hold와 사용자 타이핑 상호작용으로 대기 중 입력 문장 보존 검증. 실패 시(503) 오류 피드백 노출 및 사용자가 새로 입력 중이지 않은 경우에만 원래 명령문 자동 복구 확인.
  - **모바일 뷰포트**: 320/360/390/430px 모바일 뷰포트에서 가로 스크롤 넘침 없음(`scrollWidth <= clientWidth`) 및 바로가기 2열 그리드 배치 확인.
- **브랜드 자산**:
  - `image-generator` 원본 기반 1024×1024 마스터 아이콘과 파생 자산(`docs/branding/master-icon.png`, `docs/branding/social-preview.png`, `addon/icon.png`, `addon/logo.png`, `addon/app/fhc/static/` 파비콘 및 PWA 아이콘) 배치.
  - 헤더 이미지 및 파비콘 링크의 로컬 200 OK 응답 확인.
- **검증 한계 및 경계**:
  - 본 검증은 로컬 Playwright Chromium 및 mock HA(`FakeHA`) 환경에서 수행되었으며, 실제 운영 Home Assistant 및 실제 유료 모델 API 호출은 포함하지 않음.
  - Ingress 경로 프록시 하에서의 실제 터치스크린 조작, 애드온 스토어 실제 렌더링, GitHub 웹 UI의 social preview 반영은 추후 실제 환경 배포 시 확인 필요.

# 0.2.0-dev.9 — FIX_08 단위 모델 응답 검증 보정 및 수치 정정 (2026-10-14)

- 자동 테스트 115개 통과. Ruff check/format, JS 구문, `git diff --check` 통과.
- **R1 조건 단위 검증 보정**: `condition_unit` 응답의 `choice()` 예외 처리에서 fallback 대상을 `low_confidence`로 엄격히 한정. malformed type, label 불일치, 비숫자/NaN 확률, 합계 불일치 등 `invalid_model_response`는 정상 단위 파생으로 삼키지 않고 fail-closed(HA 전송 0건) 거부. 확신도가 낮은 유효 응답은 literal/native 단위 안전 파생으로 처리되는 기존 성공 회귀 검증.
- **R2 결과 표 및 검증 범위 명확화**: 아래 dev.8 절의 서비스 계약 및 모델별 단발 평가 수치를 레이어별/분모별로 정정.
- **V1 설치형 앱 검증(프로젝트 전용 HAOS Core 2026.10.1)**:
  - 공식 GitHub `#dev` 저장소 reload 후 Supervisor를 통해 **dev.8→dev.9(0.2.0-dev.9)** 업그레이드 및 기동 확인 (`state=started`, `version=0.2.0-dev.9`).
  - Ingress 관리자 세션: `api/status`에서 version `0.2.0-dev.9`, `ha_ready: true`, `execution_ready: true` 확인.
  - Ingress 조명 명령(`거실불 꺼줘`): status `succeeded`, 2×turn_off sent, read-back으로 거실 조명(천장등/RGBWW)만 off되고 주방/서재 조명 유지 확인.
  - Ingress B/C 대표 명령(`거실 날씨 어때`): 모델 확신도 부족 시 0전송 fail-closed(`rejected`, `low_confidence`).
  - Ingress 조건부 명령(`거실 온도가 28도 이상이면 거실불 꺼줘`): 센서 조건 미충족/평가 단계 안전 거부(`rejected`, `condition_evaluation_failed`, 0전송).
  - 관리자 정책 PUT(200) 후 Supervisor 애드온 재시작: 재시작 후 `0.2.0-dev.9` 버전 유지 및 `read_domains: {'switch': false}` 정책 보존 확인.
  - 진단 내역 내보내기(`GET /api/history/export`): 200, application/zip, `manifest.json`/`summary.json`/`requests.jsonl` 무결성 검증, 기본 내보내기 시 원문 명령 텍스트 및 비밀번호/토큰 미포함 확인.
  - 검증 완료 후 테스트 정책 원복, VM 정상 종료(stopped), 자원 증거는 `.local/fix09-install-verification.json` 및 `.local/test-resources.json`에 기록.

# 0.2.0-dev.8 — FIX_05~07 민감/정책/타입 매개변수·설치형 검증 (2026-10-14)

기준 커밋 `cb6a248`(dev). 상세 라운드 증거는 `.handoff/001_domain-expansion-and-ux/FIX_05~07_REPORT.md`와 Git 제외 `.local/fix06-live-*.json`, `.local/fix07-install-verification.json`에 있다(키·토큰 원문 미기록).

- 자동 테스트 114개 통과. Ruff check/format(20 files), JS 구문, `git diff --check` 통과. GitHub Checks(run 38489605884) test+arm-build success.
- 공식 GitHub `#dev` 저장소 갱신→Supervisor 소스 빌드로 dev.6→**dev.8 설치·기동**을 프로젝트 전용 HAOS(Core 2026.10.1)에서 수행했다. 설치 앱 Ingress에서 관리자 세션으로 `거실불 꺼줘`를 실행, 실제 조명 2개 off·타 영역 조명 유지·2×turn_off sent를 read-back으로 확인했다. 설치 앱에서 직접 확인한 범위는 조명 실행/정책·재시작/다운로드이며, 달력·TTS 등의 깊은 계약 검증은 호스트 Engine→동일 테스트 HA 경로를 사용했다.
- 설치 앱 관리자 정책 토글(read_domains·개별 entity read_enabled)이 저장·조회·**addon 재시작 후 보존**됐다. 진단 ZIP 다운로드는 200/zip 파싱 성공, 기본 익명화에서 명령 원문이 제외됐고 토큰 조각이 본문에 없었다. 검증 후 잔여 테스트 정책은 기본값으로 되돌렸다.
- **서비스 계약(호스트 Engine → 동일 테스트 HA, 모의 모델 라벨 + 실제 HA 서비스)**:
  - **service_contract 8개 통과**: 달력 start/end 생성(`calendar_create_typed_window`), 달력 이벤트 제목 read-back(`calendar_readback`), get_events 실제 `{"events":[...]}` 응답 표시(`calendar_events_nonempty_display`), weather 지원 예보 유형 실응답(`weather_forecast_daily`), TTS speak의 media_player_entity_id=선택 스피커(`tts_speak_target_payload`), input_datetime 값 설정(`input_datetime_value`), input_datetime 20:30 read-back(`input_datetime_readback`), climate 목표온도 24도 설정 및 read-back(`climate_set_temperature_24`).
  - **safety_negative 1개 통과**: todo 동명 항목에 대한 쓰기 전 사전 검증 거부(`todo_duplicate_refused_before_write`, 사유: `todo_item_ambiguous`, 전송 0건).
  - 총 9개 assertion 통과. (별도 password 시험은 `.local/fix06-live-r1-password.json`의 증거로 분리)
- **실모델 왕복(정상 요청 6건 + 음성 사례 2건, 합계 8건, 코드 cb6a248, fixture 한글 이름/배타 정책 정리)**:
  - **Microsoft Decision-1**(응답 `…-20261009`) **전체 기대 결과 일치 6/8**:
    - 정상 요청 6개 중 5개 성공 (조명 off, typed 조건 false(0전송), TTS 출력 지정 전송, 일정 조회, 예보 조회).
    - 공조 온도 설정 1건은 `plan_not_verified`로 거부.
    - 음성 사례 2개 중 1개 기대 사유 일치(TTS 모호 거부).
    - todo 부재 사례는 기대 사유 `todo_item_not_found`와 달리 `plan_not_verified`로 거부(불일치, 0전송).
    - 거부 사례의 실제 물리 전송은 모두 0건.
  - **TypeSafe Jev 1.13** **전체 기대 결과 일치 2/8**:
    - 정상 요청 6개 중 1개 공조 온도 설정 실전송 성공(나머지 5건은 거부).
    - 음성 사례 2개 중 1개 기대 사유 일치(TTS 모호 거부).
    - 거부 사례의 실제 물리 전송은 모두 0건.
  - 위 결과는 고정 단발 평가이며 일반 한국어 정확도 보장이 아니다.
- 이전 0.2.0-dev.6 기록은 아래에 보존한다.

# 0.2.0-dev.6 — 단계 A 리뷰 수정 검증 (2026-10-13)

기준 앱 소스는 `0b0330b`이며 이전 0.1 검증 기록은 아래에 보존한다. 자세한 수정별 증거는 `.handoff/001_domain-expansion-and-ux/FIX_01_REPORT.md`, 실제 모델 사례별 결과는 [evidence/0.2.0-dev.5.json](evidence/0.2.0-dev.5.json)에 기록한다.

- 자동 테스트 71개 통과. Ruff check/format, JS 구문, diff whitespace 검사가 통과했다. staged Gitleaks에서 비밀정보 발견 없음.
- 실제 HAOS 18.3 / Core 2026.10.1 / amd64 / 프로젝트 전용 2 vCPU·4GiB VM에서 공식 저장소 갱신·Dev 업데이트를 수행했다. 0.1.0-dev.1에서 dev.2, dev.3, dev.4, dev.5, dev.6까지 설치 버전보다 식별자를 높였다. 새 설치는 별도 로컬 테스트 slug로 검증하고 제거했다.
- native Configuration은 optional 표시를 클릭하지 않고 API 키·모델 입력이 보였다. 기존 키 보존, Supervisor 자기 옵션 저장·재시작 후 rescan_hours=6 유지, 이전 설치의 climate 기본 OFF 및 새 설치의 일반 도메인 기본값을 확인했다.
- 실제 Ingress에서 비관리자=403, owner 헤더 위조=403, 관리자 부여=200, 권한 회수=403을 확인했다. 추가 Supervisor/Docker 권한을 요청하지 않았다.
- 실제 그룹·template onoff 조명 fixture를 추가했다. 제외 엔티티 rename 후에도 OFF 정책이 유지됐다. 실제 모델의 그룹 별칭 명령은 보수적으로 거부됐다. 별도 **모의 모델 + 실제 HA** 시험에서 허용 leaf만 전송하여 ceiling=off, 제외 bed=on을 확인했다. 이를 실제 모델의 그룹 의미 해석 성공으로 주장하지 않는다.
- 실제 Microsoft 모델(응답 모델 `microsoft/microsoft-decision-1-20261009`)과 가상 기기로 송풍/제습/냉방+온도/색+밝기/색온도/상대 밝기를 확인했다. 최종 고정 세트 15건 중 13건이 기대 결과와 일치했다: 정상 10건 중 8건 실행, 음성 5건 모두 무전송. 거실전등 켜기와 복수 온도 사례는 낮은 확신으로 거부됐다. 앞선 시험에서 해당 기능이 성공한 것과 이 결과를 혼합하지 않는다. 관측 세트에서 잘못된 대상/값 전송은 없었으나 일반 정확도 보증은 아니다.
- 해당 고정 세트에서 성공한 실제 전송의 첫 dispatch는 3.620–4.811초였다. scope 약 1.80–2.99초, action 약 0.89–1.00초, verify 약 0.83–0.89초, preflight 2–9ms. 3개 논리 단계가 4개 HTTP 모델 호출로 분할됐다. 성능은 기록 항목이며 엄격한 출시 통과 기준으로 삼지 않았다.
- 최종 dev.6 추가 명령 “천장등 색온도 4000K로 맞춰줘”는 실제 4000K 적용에 성공했다(첫 dispatch 5.131초). 공개 명령 응답에 판단 진단이 없고 관리자 history에만 해당 진단이 있음을 확인했다.
- Core 재시작 후 앱 자동 복구, 앱 재시작 후 옵션/저널 유지, 과거 UUID 재전송 시 실제 기기 재조작 없음(반대 상태로 seed 후 확인)을 시험했다. 네트워크 ACK 유실 및 실패/손상 DB는 자동화의 fault injection이며 실네트워크 단절 시험과 구분한다.
- 실제 Ingress Playwright Chromium에서 사용자/관리자 분리, 공급자 라디오 키보드/ARIA, 빈 비밀 입력, FHC 검색의 펼쳐진 일치 결과, desktop 1280×900 / mobile 390×844, 가로 넘침 없음, page/console 오류 없음, 원클릭/연타 POST 1회와 UUID fallback을 확인했다. 최종 dev.6 카드 재실행은 이미 요청한 상태로 정상 종료됐다. 앞선 카드 시험에서는 확신 부족 거부도 있어 클릭 전달 성공과 가전 실행 성공을 구분한다.
- CI의 amd64 및 aarch64 컨테이너 빌드가 통과했다. ARM 실제 실행과 Azure live는 미검증이며 Azure는 mock 계약으로 검증했다. 다른 모델은 호출하지 않았다. 일반 색 팔레트 밖 표현, 조건/예약, heat_cool 범위 온도와 B/C 도메인은 후속 범위다.

- 검증 후 별도 새 설치 앱·로컬 설치 디렉터리·임시 HTTP 전송 서버·임시 tar·호스트 테스트 이미지·인증 시험용 사용자를 제거했다. 테스트 VM은 ACPI로 정상 종료하고 새 fixture와 baseline 디스크만 재사용 목적으로 보존했다. 기존 운영 VM/호스트 방화벽/다른 Docker 서비스는 변경하지 않았다.

---

# 0.1.0-dev.1 검증 기록

검증일: 2026-10-13. 운영 VM이나 기존 사용자 HA를 사용하지 않았다. 아래는 첫 실험적 MVP의 검증이며 전체 요구사항 개발 완료를 뜻하지 않는다.

## 자동 검사

- Python 3.13, pytest **37개 통과**. 전체 카탈로그 전달, 모의 공급자 계약(OpenRouter/Azure 단독), 잘못된 확률/응답 거부, 요청 중복/충돌, 정책 변경, 전체 대상 사전 조회, 응답 유실 시 재전송 금지, 재시작 저널 복구, Ingress 헤더 위조 거부를 확인했다.
- 실제 localhost WebSocket 서버를 사용한 초기 snapshot/event 경합, 연결 종료 후 재접속, 엔티티 추가·삭제 동기화를 확인했다.
- 잘못된 설정의 startup traceback에 원본 API 키가 포함되지 않는 회귀 검사를 추가했다.
- Ruff lint/format, actionlint, hadolint, JavaScript 문법 검사, Git diff 공백 검사, staged Git gitleaks 검사를 수행했다.
- FastAPI TestClient의 upstream Starlette/httpx 사용 중단 예고 경고 1개가 있다. 실패는 아니며 현재 테스트는 통과한다.

## 실제 HAOS 설치와 실행

| 항목 | 결과 |
|---|---|
| 환경 | 공식 HAOS 18.3 / Core 2026.10.1, amd64 QEMU/KVM, 2 vCPU / 4GiB |
| 설치 | 공개 GitHub `#dev` 저장소 등록 → Supervisor 소스 빌드 → 설치·시작 성공 |
| 인증 | 앱이 주입받은 Supervisor 토큰 사용. 설치 사용자용 HA URL/LLAT 설정 없음 |
| 자동 탐색 | 초기 전체 125개 엔티티(앱 상태 엔티티 추가 등에 따라 변동), 지원 대상 조명 6개 / 스위치 2개 |
| Ingress | 실제 Supervisor Ingress 세션으로 앱 접근. 브라우저에서 자연어 명령 실행 성공 |
| 물리 실행 대체 | 공식 demo integration의 가상 light 상태가 실제 HA 서비스 호출 후 변경됨 |
| 환경 변경 | REST로 테스트 light 추가·삭제 시 카운트 자동 변경. 레지스트리 이름 변경·복구 후 자동 재탐색 확인 |
| 수동 탐색 / 정책 | Ingress UI에서 재탐색, switch 허용 해제·복구 확인 |
| HA 재시작 | 연결 중단 관측 후 앱 재시작 없이 자동 재접속·전체 재탐색. 시험에서 약 15.8초 |
| 브라우저 | Chromium, 1505px 데스크톱 / 390px 모바일. 가로 넘침 없음 |

설치된 앱의 Ingress에서 “거실불 꺼줘”를 실행하고 거실 조명 두 개에 대한 전송 결과를 확인했다. 성공 표시와 기기 완료를 구분한다. HA 서비스 수락은 물리 기기 완료 보장이 아니다. 실제 스마트 전구·스위치 하드웨어는 사용하지 않았다.

앱 소스 `6e8262c`까지 HAOS에서 다시 빌드했다. “침실 조명 켜줘”의 실제 상태 변경, 이력 삭제, 한국어 실행 상태, 모바일 화면과 JavaScript 오류 없음을 확인했다. 인증 없는 Ingress 요청은 401이었다. amd64 검사·빌드와 aarch64 컨테이너 빌드가 [GitHub CI](https://github.com/Kanu-Coffee/fast-home-control/actions/runs/38341750734)에서 통과했다. 후속 문서·캡처 커밋은 이 앱 소스를 변경하지 않는다.

추가 실기동에서는 우선 공급자를 Azure로 지정하고 Azure endpoint를 잘못된 HTTP 주소로 설정한 뒤, 정상 OpenRouter로 “침실 조명 꺼줘”가 실행되는지 확인했다. 브라우저는 실제 `http://fhc.test` 테스트 origin으로 접속했으며 `isSecureContext=false`, `crypto.randomUUID=undefined` 환경에서도 요청 ID를 생성하고 명령을 전송했다. HTTPS 없는 HA 접속을 지원하기 위해 [randomUUID의 secure context 제약](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)을 처리하고 [getRandomValues](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/getRandomValues) 기반 UUID를 사용한다. 시험 후 정상 공급자 설정으로 복구했다.

## 실제 모델 평가

사용자가 승인한 임시 OpenRouter 키로 **microsoft/microsoft-decision-1만** 호출했다. 응답 모델 식별자는 최초 API 확인 시 `microsoft/microsoft-decision-1-20261009`였다. Azure 직접 호출은 키가 없어 모의 계약 검증만 수행했다. 잘못된 Azure endpoint와 정상 OpenRouter 키를 함께 설정한 실제 호출에서 Azure를 격리하고 OpenRouter Decision-1로 정상 판단하는 것도 확인했다.

[고정 15개 명령 결과](live-evaluation.json)는 실제 모델과 실제 HAOS의 가상 엔티티를 연결한 실행기 시험이다. 각 명령 전 대상 상태를 반대로 초기화하고, 예상 대상의 결과 상태와 나머지 기기가 변하지 않았는지 함께 확인했다.

| 분류 | 결과 |
|---|---|
| 정상 명령 7개 | 6개 정확 실행, 1개 보수적 거부 |
| 모호·미지원 명령 8개 | 8개 모두 거부, 서비스 실행 없음 |
| 동의어 | 거실불 / 거실전등 / 거실조명 모두 거실의 light 2개를 끔 |
| 영역 / 전체 | 침실 조명, 집 전체 light 6개 제어 성공 |
| 알려진 실패 | “거실 불 끄고 거실 콘센트 켜줘”: 정상 요청이나 최종 계획 검증에서 거부. 부분 실행 없음 |

이 작은 fixture의 14/15 결과를 일반적인 한국어 정확도로 해석하지 않는다. 다중 기기 영역 제어는 확인했지만 서로 다른 동작을 묶은 복합 명령은 아직 신뢰성이 부족하다. 구현 과정에서 여러 질문 구성과 계획 후보 임계값을 비교했고, 최종 실행에는 별도의 높은 계획 검증 문턱을 유지했다. 중간 후보 확률이 곧 실행 확신도가 아니다.

성공한 6개 명령에서 첫 HA 전송까지 **약 2.60–2.85초**, 모델 API는 보통 **3회**였다. 공급자 왕복은 질문 단계별 약 0.81–1.14초였다. 이는 네트워크 시간을 포함하며 모델 서버 내부 추론 시간과 분리할 수 없다. `/api/commands/{id}` 결과에는 범위/동작/검증 왕복, 사전 상태 조회, 첫 전송, 전체 시간, HA 수락 시간을 별도로 기록한다. 속도는 측정·개선 지표이며 출시 통과 기준으로 삼지 않았다.

## 규모 확인과 남은 범위

[503개 합성 엔티티의 실제 모델 범위 판단](scale-probe.json): 전체 압축 카탈로그 24,327 UTF-8 bytes를 생략 없이 전달했고 약 1.34초에 관련 그룹과 지원 여부 판단을 받았다. 이 시험은 범위 판단만 수행했으며 503개 전체 실행 정확도나 실제 HA 대규모 동기화 검증은 아니다. 자동 테스트에서는 500개 추가 엔티티와 별칭이 카탈로그에서 빠지지 않는지, 200개 질문 분할 시 질문이 소실되지 않는지 확인한다.

첫 Dev의 40KB 요청 한도, 전체 계획 검증에 따른 정상 명령 거부, 큰 영역/전체 제어 시 질문 분할 비용이 남아 있다. 실제 aarch64 HAOS 기동은 수행하지 않았고 CI 컨테이너 빌드로 구분한다. Azure 실제 호출, 다양한 기존 HA 버전, 실제 하드웨어, 조건·수치 매개변수·읽기 전용 센서·외부 브릿지는 후속 검증 범위다.

원본 키·테스트 인증정보는 Git 제외 로컬 파일에만 보관한다. 검증 후 프로젝트 테스트 VM과 임시 실행 서버를 중지하고, 재시험용 디스크는 사용자 전용 디렉터리에 보관한다. Main/안정 버전은 생성·승격하지 않는다.
