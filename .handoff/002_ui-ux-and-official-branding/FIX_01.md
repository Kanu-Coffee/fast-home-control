# Reviewer 교정 요청 — 정책 편집 중단 및 검증 공백

작성일: 2026-10-14 · 역할: Reviewer · 판정: **수정 필요, dev.10 릴리스 승인 보류**

## 1. 검토 기준

- 대상: 이 작업의 `PLAN.md`, `REPORT.md`, 현재 전체 tracked diff와 신규 `tests/test_browser_ui.py`, 브랜딩 자산/문서 및 화면 캡처.
- 기준 HEAD: `02dc9d0877378e95bf9710aa37a7b17579fef67e`, 브랜치 `dev`.
- 구현은 아직 working tree에 있으며 별도의 최종 구현 commit은 없다. 버전 문자열은 `0.2.0-dev.10`이다.
- 이 작업에는 기존 FIX가 없으므로 `FIX_01.md`를 신규 작성한다. 기존 PLAN/REPORT/001 이력을 변경하지 않는다.
- Reviewer는 제품 코드를 수정하지 않았다. 아래 사항을 Executor가 수정하고 `FIX_01_REPORT.md`를 작성한다.

## 2. 재실행 결과와 검토 한계

- `uv run pytest -q`: **116 passed**, 기존 Starlette deprecation warning 1개.
- Ruff check/format: 통과, 21 files. JavaScript syntax 및 `git diff --check`: 통과.
- Browser 플러그인/skill은 제공되지 않아 설치된 Python Playwright Chromium으로 추가 동작을 확인했다. 저장소 밖 `/tmp/fhc_review_002.py`에서 기존 `ui_server` fixture를 이용한 localhost 테스트를 수행했다. 운영 HA 및 실제 유료 모델 호출은 하지 않았다.
- 추가 probe의 출력은 아래와 같다. 이 probe의 `1 passed`는 관찰 스크립트가 완료됐다는 뜻이며 제품 수용 기준 통과를 의미하지 않는다.

```text
POLICY_AFTER_SAVE {"saving": false, "disabled": true}
CUSTOM_DRAFT_AFTER_SWITCH typesafe/jev-1.13
SEARCH_CLOSE_RESULT true
SAME_STATUS_PHASE_REFRESHED False
DIAGNOSTIC_SCROLL_AFTER_CHANGE 0
TOGGLE_HITBOX width=44, height=24
```

- 이미지 원본과 기존 모바일 관리자 캡처를 열어 확인했다. 아이콘 디자인과 파생 자산의 방향은 계획에 부합한다. 이미지 생성 도구/엔진 이력은 Executor 문서의 기록이며 Reviewer가 해당 외부 세션을 독립 재현한 것은 아니다.
- 이번 Reviewer는 컨테이너 빌드, 실제 HAOS dev.10 설치, Ingress, GitHub 공개 렌더링/설정 적용을 수행하지 않았다. 해당 증거는 기존 REPORT에도 없다.

## 3. 필수 교정

### R1 — [P1] 첫 정책 저장 후 모든 제어/조회 토글이 잠긴다

위치: `addon/app/fhc/static/app.js`의 `updatePolicy()` 485–515행 및 `renderDomains()`의 disabled 계산.

`isPolicySaving=true` 상태에서 `loadDomains(true)`가 새 버튼을 렌더링하므로 모든 토글에 disabled가 적용된다. finally에서 변수만 false로 바꾸고 DOM을 갱신하지 않아 저장 성공 후에도 버튼 전체가 잠긴다. 이후 검색·모드 왕복 등 다른 렌더링을 해야 편집을 계속할 수 있다. 실패 경로도 같은 순서다. 기존 테스트는 한 번 누른 뒤 펼침만 확인하므로 놓친다.

재현: 관리자 → 조명 펼침 → 개별 제어 변경 → PUT/GET 완료 대기 → 같은 기기 조회 또는 다른 기기 제어 변경. 추가 probe에서 `isPolicySaving=false`인데 `#domains .toggle`은 모두 disabled였다.

수정 요구:

- 저장 시작 때 실제 DOM에 busy/disabled를 반영하고, 성공·실패·후속 GET 실패까지 완료 시 가능한 토글을 다시 활성화한다.
- 서버 최신 값/집계와 펼침·검색·스크롤·포커스를 보존한다. 전체 DOM 재생성 여부는 구현 판단에 맡긴다.
- 포커스 복원에는 엔티티 ID/도메인/접근 종류 등 안정적인 키를 사용한다. 현재 aria-label 기반 CSS 선택자는 동일한 이름의 기기가 있거나 이름에 따옴표/대괄호가 들어가면 잘못된 대상을 고르거나 예외를 낼 수 있다.
- 여러 도메인을 펼친 뒤 제어 → 조회 → 다른 기기 제어를 연속 저장하는 테스트, PUT 실패 뒤 재시도, PUT 성공 후 GET 실패의 상태/오류 테스트를 추가한다. 고정 sleep 대신 응답/상태를 기다린다.

### R2 — [P1] 새 브라우저 테스트가 깨끗한 CI에서 실패한다

위치: `tests/test_browser_ui.py:111`, `.github/workflows/check.yml:13–16`.

`pytest -q`에 Chromium 실행을 요구하는 테스트가 포함됐지만 CI는 `uv sync` 뒤 곧바로 pytest를 실행한다. Playwright Python 패키지 설치는 브라우저 바이너리 설치가 아니다. 현재 개발 호스트의 기존 브라우저 캐시에 의존한다.

확인 명령:

```sh
PLAYWRIGHT_BROWSERS_PATH=/tmp/fhc-review-empty-browser-cache uv run pytest -q tests/test_browser_ui.py
```

결과: **1 failed**, `BrowserType.launch: Executable doesn't exist ... chromium_headless_shell-1243/...`.

수정 요구:

- 기존 CI에 프로젝트 Playwright 버전과 맞는 Chromium 및 필요한 OS 라이브러리를 준비하는 단계를 추가하거나, 브라우저 테스트를 명시적인 별도 CI job으로 분리한다.
- 단순 skip으로 회귀 검증을 없애지 않는다. 단위 검사와 브라우저 검사가 각각 실제로 실행되는 것을 보인다.
- 새 환경 실행 절차를 `docs/testing.md`에 기록한다. workflow 변경 시 사용 가능한 actionlint 등 적절한 검사와 실제 CI 결과를 보고한다.
- fixture 정리 시 서버 thread 종료를 기다리고 테스트가 바꾼 app 상태/환경을 종료 완료 후 복원한다. 고정 0.6초 기동 sleep 대신 서버 준비 상태를 기다려 느린 CI의 경합을 줄인다.

### R3 — [P2] 로그의 변경 내용과 읽는 위치가 보존되지 않는다

위치: `addon/app/fhc/static/app.js:540–601`.

두 문제를 추가 probe로 확인했다.

1. fingerprint가 ID/status/reason만 포함한다. 같은 상태에서 phase/model_trace/actions/timings 등이 바뀌면 갱신을 건너뛰어 관리자에게 오래된 진단을 보여준다. 응답의 phase를 `first`→`second`로 바꾼 뒤 `loadHistory()`를 호출했지만 화면에는 second가 없었다.
2. 변경 감지 시 전체 행을 교체하고 목록의 숫자 scrollTop만 복구한다. 진단 `<pre>`의 scrollTop 및 키보드 포커스는 사라진다. probe에서 내부 스크롤 120이 상태 변경 후 0으로 초기화됐다. 새 기록이 위에 추가되면 같은 숫자 scrollTop도 같은 읽던 항목을 보장하지 않는다.

수정 요구:

- 실제 렌더링 필드의 변경을 감지한다. UI에 필요한 데이터 전체 비교 또는 request ID 기반 행 갱신을 사용해도 된다.
- 기존 행을 유지하거나 request ID와 상대 위치로 현재 읽던 항목을 복구한다. 진단 펼침뿐 아니라 JSON 내부 스크롤·포커스를 보존한다.
- 50건/긴 JSON fixture에서 변경 없는 갱신, 같은 상태의 진단 내용 변경, 맨 위 새 항목 추가, 기존 상태 변경을 각각 검증한다. 동일 응답으로 `loadHistory()`만 호출해 DOM 교체를 건너뛴 테스트는 변경 시 보존의 증거가 아니다.

### R4 — [P2] 후보 모델 왕복 시 직접 입력 초안이 사라진다

위치: `addon/app/fhc/static/app.js:633–644`.

재현: 직접 입력 선택 → `my-org/my-model` 작성 → Jev 선택 → 직접 입력 선택. 결과가 `typesafe/jev-1.13`으로 바뀐다. 후보 선택 때 같은 text input을 덮어쓰기 때문이다. PLAN C의 작성 중인 값 보존과 REPORT의 전환 보존 주장에 맞지 않는다.

수정 요구:

- 직접 입력 초안을 후보 값과 분리해 유지한다. loadConfig 시 저장값에 맞게 초기화하고 선택 왕복만으로 초안을 버리지 않는다.
- Microsoft/Jev/custom 각각 실제 설정 저장 → GET/폼 재로드를 검증한다. 후보 밖 기존 ID 로드, 다른 설정만 저장, 빈 키 유지, Azure 설정 보존도 실제 요청 body와 결과로 확인한다.

### R5 — [P2] 검색 중 목록 닫기가 작동하지 않고 키보드 포커스를 잃는다

위치: `addon/app/fhc/static/app.js`의 `renderDomains()` 내 `isExpanded` 계산과 목록 버튼 click handler.

검색 중에는 `isExpanded`가 무조건 true다. `목록 닫기`를 눌러도 다시 열린 상태로 렌더링되며, 이 과정에서 평상시 expandedDomains만 변경한다. probe의 검색 중 닫기 후 `aria-expanded`는 여전히 true였다. 일반 상태에서도 목록 버튼을 누르면 클릭한 DOM 노드 자체를 교체해 키보드 포커스를 잃는다.

수정 요구:

- 검색 중 자동 펼침과 사용자의 검색 중 조작을 분리한다. 닫기 버튼을 제공하면 실제 닫히게 하고 검색 해제 시 평상시 펼침 상태를 복원한다.
- 펼침/접힘 버튼의 키보드 포커스를 유지한다. 이름이 같은 엔티티에도 안정적인 ID를 사용한다.
- 검색 시작 → 목록 닫기/열기 → 검색 해제의 상태와 Enter/Space로 조작 후 포커스를 검증한다.

### R6 — [P2] 실제 토글 터치 영역은 44×24px다

위치: `addon/app/fhc/static/style.css:537–548` 및 토글 그룹 마크업.

REPORT는 40–44px 터치 영역 확보를 주장하지만 실제 button의 높이는 24px이고 부모 캡션/그룹은 클릭되지 않는다. 추가 probe로 bounding box 44×24px를 확인했다. PLAN A의 시각 스위치 크기와 터치 영역 분리 요구가 충족되지 않았다.

수정 요구: 기존 44×24px 시각 디자인은 유지할 수 있지만 실제 클릭/포커스 영역의 높이를 약 44px 이상으로 확보한다. 열 정렬 및 인접 토글 오조작 방지를 함께 확인하고 모바일 hitbox 측정 결과를 보고한다.

## 4. 검증 증거와 문서 정정

현재 테스트 및 보고서의 다음 항목은 실제 수용 기준 증거로 부족하다.

- `tests/test_browser_ui.py:294–305`는 명령 제출을 하지 않고 `page.evaluate()`에 입력 복원 코드를 직접 작성해 실행한다. 실제 `executeCommand()`가 망가져도 통과한다. 실제 form submit/바로가기 클릭과 모의 API 응답·네트워크 실패를 통해 제품 코드 경로를 검증한다. 새로 작성한 문장 덮어쓰기 방지와 uncertain/partial 자동 재전송 없음도 확인한다.
- 모델 테스트는 선택/필드 표시만 확인하며 POST 저장/재로드를 확인하지 않는다.
- 정책 실패, GET 응답 역전, 새 로그 추가, JSON 내부 스크롤/포커스, 다운로드/삭제, Ingress prefix, 200% 확대 등은 현재 테스트에서 확인하지 않는다. 보고서에 실제 검증한 범위와 미검증 범위를 구별해야 한다.
- 로컬 root URL의 header PNG 확인을 실제 Ingress 및 모든 favicon MIME/공개 README 검증으로 확대하면 안 된다. `docs/verification.md`의 전환값 보존·정책 실패·위치 보존 등 주장을 실제 새 증거에 맞게 정정한다.
- 기존 REPORT는 역사 문서로 보존하고, 부정확했던 주장과 수정 후 결과를 `FIX_01_REPORT.md`에 명시한다. "100%", "완벽히" 같은 표현 대신 검증 흐름·관찰값·제한을 기록한다.

필수 회귀는 R1–R6에 직접 대응하는 동작 중심 테스트로 작성한다. 새 테스트는 수정 전 실제 실패하고 수정 후 통과하는지 확인한다. UI 문자열/CSS 구현을 복제하는 검사를 늘리지 않는다.

## 5. 릴리스·브랜딩 잔여 작업

- dev.10은 현재 로컬 미커밋 구현이다. 실제 설치 및 CI 성공 증거 없이 tag/prerelease 발행 가능 상태로 판단하지 않는다.
- 교정 후 Dev 소스 commit을 확정하고 CI(amd64/arm64 포함)와 프로젝트 전용 HAOS의 공식 저장소 업데이트·기동·Ingress 정책 연속 저장·모델 유지·아이콘/로그 다운로드를 확인한다. `docs/releases.md`의 설치 검증 → 검증 소스 포함 commit tag/prerelease 순서를 따른다. Main/안정 릴리스는 별도 승인 대상이다.
- HA 앱 스토어 icon/logo와 GitHub README는 파일 배치와 실제 노출 검증을 구분한다. 현재 REPORT에는 HA 공식 규격 확인 근거나 실제 스토어/Ingress 확인 기록이 없다. 실행 시 공식 문서/지원 버전과 테스트 환경 근거를 보완한다.
- Social preview는 기존 계획대로 최종 자산 준비와 외부 수동 업로드 필요를 구분하면 된다. 이 항목 때문에 개인/조직 avatar나 GitHub 사이트 favicon을 변경하지 않는다.
- 이미지 자체의 재생성은 이번 교정의 필수 요구가 아니다. 기존 생성 원본·프롬프트·파생 이력은 유지한다.

## 6. 다음 Executor 인계

R1–R6 수정, 동작 검증 보강, 현재 검증 문서 정정 후 같은 폴더에 `FIX_01_REPORT.md`를 신규 작성한다. 기준/최종 Git 상태, 각 요구별 변경 파일, 재현/검증 명령과 결과, fixture/실제 설치 구분, CI/설치/공개 노출 적용표, 남은 제한을 포함한다. 준비된 수정과 증거를 Reviewer가 재검토하기 전에는 본 리뷰를 dev.10 릴리스 승인으로 해석하지 않는다.
