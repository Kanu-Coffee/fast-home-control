# Executor 교정 보고서 — 정책 편집 잠금 해제, 브라우저 CI 및 UI/UX 동작 검증

작성일: 2026-10-14 · 역할: Executor · 판정: **교정 완료, Reviewer 재검토 요청**

---

## 1. 개요 및 변경 파일

본 보고서는 `.handoff/002_ui-ux-and-official-branding/FIX_01.md`에서 요청된 필수 교정 사항(R1–R6), CI 워크플로 보강, 브라우저 테스트 실제 API 경로 반영 및 검증 문서 정정 결과를 기록합니다.

- **기준 HEAD**: `02dc9d0877378e95bf9710aa37a7b17579fef67e`, 브랜치 `dev`
- **대상 버전**: `0.2.0-dev.10` / `0.2.0.dev10`
- **수정된 파일 목록**:
  - `addon/app/fhc/static/app.js`: 정책 저장 생명주기 및 토글 잠금 해제(R1), 상세 진단 지문 확장 및 스크롤/포커스 복원(R3), 모델 직접 입력 초안 보존(R4), 검색 중 아코디언 닫기 및 포커스 유지(R5).
  - `addon/app/fhc/static/style.css`: `.toggle` 스위치 클릭/터치 히트박스를 44×44px로 확장하되 `::before` 가상 요소로 44×24px 시각적 디자인 유지(R6), `.toggle-entities-btn` min-height 40px 확보.
  - `.github/workflows/check.yml`: CI `test` job에 `uv run playwright install --with-deps chromium` 단계 추가(R2).
  - `tests/test_browser_ui.py`: `ui_server` 기동 시 `/healthz` 능동 폴링 및 종료 시 `server.join(timeout=5.0)` 정리(R2), R1~R6 전 항목에 대한 실제 UI/네트워크 동작 테스트 및 실제 form submit/503 오류 처리 검증.
  - `docs/testing.md`: 깨끗한 환경에서의 Playwright Chromium 설치 및 브라우저 테스트 실행 절차 문서화.
  - `docs/verification.md`: 0.2.0-dev.10 항목을 과장 표현 없이 실제 관측 수치 및 테스트 경계로 정정.

---

## 2. 요구사항별 교정 상세

### R1 — [P1] 첫 정책 저장 후 토글 잠금 해제 및 안정적 포커스 복원
- **원인 분석**: `updatePolicy()` 내에서 `isPolicySaving = true`가 설정된 상태로 `await loadDomains(true)`가 호출되었고, `renderDomains()`가 `isPolicySaving === true`를 평가하여 모든 토글을 `disabled = true`로 렌더링했습니다. `finally`에서 플래그만 `false`로 바꾸고 DOM을 갱신하지 않아 저장 완료 후에도 버튼이 잠겨 있었습니다. 또한 `aria-label` 기반 선택자는 동일 이름 기기나 따옴표/대괄호 등 특수문자에서 오작동 위험이 있었습니다.
- **수정 내용**:
  1. 저장 시작 시 활성 토글에 busy 상태(`disabled = true`)를 즉시 반영.
  2. `finally` 블록에서 `isPolicySaving = false`를 먼저 확정한 후 `await loadDomains(true)`를 호출하여, 성공/실패/후속 GET 실패 시에도 새로 렌더링되는 모든 토글이 `disabled = false`로 즉시 활성화되도록 수정.
  3. 모든 토글에 `data-domain`, `data-entity-id`, `data-action`, 고유 `id` 속성을 부여하고, 포커스 복원 시 `CSS.escape(id)`와 `data-entity-id`/`data-domain` 선택자를 사용해 특수문자가 포함된 기기에서도 안전하게 복원.
- **검증**:
  - 조명 도메인 내 첫 번째 엔티티 제어 토글 클릭 → PUT/GET 완료 후 `disabled === false` 확인.
  - 페이지 새로고침 없이 즉시 같은 행의 조회 토글 클릭 → 2차 PUT/GET 완료 및 활성화 상태 유지 확인.
  - 특수문자 `따옴표 "`, `대괄호 []`가 포함된 엔티티(`light.special_quote`)의 연속 토글 조작 및 포커스 복원 통과.

### R2 — [P1] 깨끗한 CI 환경의 Playwright Chromium 의존성 준비 및 fixture 정리
- **원인 분석**: `.github/workflows/check.yml`에서 `uv sync` 직후 `uv run pytest -q`를 실행하여 브라우저 바이너리가 설치되지 않은 환경(`PLAYWRIGHT_BROWSERS_PATH=/tmp/empty-cache`)에서 `BrowserType.launch` 오류 발생. `ui_server` fixture는 고정 0.6초 sleep에 의존하고 teardown 시 스레드 종료를 대기하지 않았음.
- **수정 내용**:
  1. `.github/workflows/check.yml`에 `uv run playwright install --with-deps chromium` 단계 추가.
  2. `tests/test_browser_ui.py`의 `ui_server` fixture에서 고정 sleep을 제거하고 `http://127.0.0.1:{port}/healthz`를 최대 10초간 능동 폴링(0.05초 간격)하여 서버 기동을 보장.
  3. Fixture teardown 시 `server.should_exit = True` 설정 후 `t.join(timeout=5.0)`으로 서버 스레드 완전 종료를 대기한 뒤 환경변수 및 앱 상태 복원.
  4. `docs/testing.md`에 깨끗한 환경에서의 설치 및 실행 절차 명시.
- **검증**:
  - 빈 캐시 환경 재현: `PLAYWRIGHT_BROWSERS_PATH=/tmp/fhc-review-empty-browser-cache uv run pytest -q tests/test_browser_ui.py` 실행 → **1 passed in 3.01s**.
  - `actionlint .github/workflows/check.yml` 통과.

### R3 — [P2] 로그 변경 내용 감지 및 열람 위치·내부 스크롤 보존
- **원인 분석**: 이전 `lastHistoryFingerprint`가 `id:status:reason`만 비교하여 `phase`, `model_trace`, `timings_ms`, `actions` 등의 진단 정보 변경 시 갱신을 건너뛰었습니다. 또한 갱신 시 전체 DOM이 재생성되어 `<pre>`의 `scrollTop`과 키보드 포커스가 0으로 초기화되었습니다.
- **수정 내용**:
  1. `makeHistoryFingerprint`에서 `id`, `status`, `reason`, `phase`, `model`, `model_trace`, `timings_ms`, `actions`, `decisions`, `verification_score`, `scope_scores`, `proposed_plan` 전체 UI 필드를 직렬화하여 변경 감지.
  2. DOM 교체 전 열려 있는 모든 `<pre class="diagnostic-json">`의 `scrollTop`을 `Map(requestId -> scrollTop)`으로 수집.
  3. 현재 포커스된 요소(summary, pre 등)와 `#history` 목록의 최상단 가시 행(`anchorRequestId`, `anchorOffset`)을 기록.
  4. 렌더링 후 `<pre>`의 `scrollTop` 복원, 앵커 행 기준 컨테이너 스크롤 복원, 포커스 복원 수행.
- **검증**:
  - 50건 이력 fixture 환경에서 첫 행 `<details>` 펼침 후 `<pre>` 스크롤을 120px로 이동.
  - 동일 데이터 갱신 시 DOM 재생성 건너뜀 확인.
  - DB에서 `phase`를 `"completed"`에서 `"phase-test-modified"`로 변경하고 `model_trace` 갱신 후 `loadHistory()` 호출 → 새 phase가 텍스트에 즉시 반영되고, `<pre>`의 `scrollTop`이 **120px**로 유지됨을 확인.

### R4 — [P2] 후보 모델 왕복 시 직접 입력 초안 보존
- **원인 분석**: 모델 드롭다운을 '직접 입력'에서 후보 프리셋(Jev/Microsoft)으로 변경할 때 `modelInput.value = sel`을 실행하여 사용자가 작성 중이던 커스텀 모델 ID를 덮어썼습니다.
- **수정 내용**:
  1. `customModelDraft` 메모리 변수를 신설하여 '직접 입력' 텍스트박스 입력 시 실시간 보존.
  2. 드롭다운 변경 시 프리셋을 선택해도 `customModelDraft`를 훼손하지 않으며, 다시 '직접 입력'을 선택하면 `modelInput.value = customModelDraft`로 복원.
  3. `config-form` 제출 시 선택이 'custom'인 경우 `customModelDraft`를 우선 반영.
- **검증**:
  - '직접 입력' 선택 → `"my-org/my-draft-decision-model"` 작성 → `"typesafe/jev-1.13"` 선택 → '직접 입력' 재선택 → 입력값에 `"my-org/my-draft-decision-model"` 보존 확인.
  - 실제 설정 POST 저장 후 options.json 파일 내 커스텀 모델 반영 및 프리셋 전환 저장 확인.

### R5 — [P2] 검색 중 아코디언 닫기 및 키보드 포커스 유지
- **원인 분석**: `renderDomains()` 내 `isExpanded = query ? true : expandedDomains.has(...)`로 인해 검색 중에는 클릭 핸들러가 `expandedDomains`를 조작하더라도 무조건 `true`로 재평가되어 닫히지 않았습니다. 또한 DOM 교체로 버튼의 포커스를 잃었습니다.
- **수정 내용**:
  1. `searchCollapsedDomains` Set을 신설하여 검색 중 사용자의 명시적 닫기 조작을 평상시 `expandedDomains`와 분리.
  2. 검색 중에는 `!searchCollapsedDomains.has(domain)`으로 펼침을 판정하고, 검색어 삭제 시 `searchCollapsedDomains.clear()`로 평상시 상태 복원.
  3. 토글 버튼에 고유 `id="toggle-btn-${d.domain}"`을 부여하고, 클릭 후 DOM 재렌더링 시 클릭했던 버튼 ID로 `.focus()` 복원.
- **검증**:
  - `"보조 조명"` 검색 → 조명 도메인 자동 펼침 → '목록 닫기' 클릭 → 아코디언 닫힘(`aria-expanded="false"`, 숨김 확인) 및 포커스가 `#toggle-btn-light`에 유지됨 확인.
  - 키보드 Space/Enter 키로 다시 열기 조작 및 포커스 유지 확인.
  - 검색어 초기화 시 사용자가 사전에 펼쳐둔 기본 상태 복원 확인.

### R6 — [P2] 토글 스위치 터치 히트박스 44×44px 확보
- **원인 분석**: 기존 `.toggle`은 `width: 44px; height: 24px;`로 실제 버튼 높이가 24px에 불과하여 모바일 터치 접근성 기준(최소 44px)에 미달했습니다.
- **수정 내용**:
  1. `.toggle`의 기본 크기를 `width: 44px; height: 44px; min-height: 44px;`로 설정하고 배경을 투명 처리.
  2. `::before` 가상 요소를 통해 수직 중앙(`top: 10px`)에 44×24px 크기의 둥근 알약 트랙을 렌더링.
  3. `::after` 가상 요소를 통해 `top: 12px`에 20px 원형 스위치 손잡이를 배치.
  4. `.toggle-group` 폭(78px)과 간격(8px)을 유지하여 인접 토글 간 오조작 및 충돌 방지.
- **검증**:
  - Playwright `bounding_box()` 측정: 제어 토글 `width = 44px, height = 44px`, 조회 토글 `width = 44px, height = 44px`.
  - 제어 열과 조회 열의 X 좌표 수직 정렬 유지 확인.

### Section 4 — 실제 API 명령 실패 처리 및 입력 복원 검증
- **원인 분석**: 기존 테스트는 실제 `executeCommand()` 호출 없이 `page.evaluate()`로 DOM 문자열을 수동 조작했습니다.
- **수정 내용**:
  1. 실제 사용자 모드에서 `#command`에 미지원 명령을 작성하고 `#command-form` submit 이벤트를 트리거.
  2. 실제 API POST `/api/commands` 호출 및 503 오류 경로를 거쳐 제품 오류 피드백(`userFeedback`)이 표시되는 흐름 검증.
  3. 실행 실패 후 `#command` 입력창에 원문 명령어가 정상 복원됨을 확인.
  4. 사용자가 대기 중 새 명령을 입력한 경우 새 입력값이 덮어씌워지지 않는 방어 로직 검증.

---

## 3. Reviewer Replica Probe 재실행 관찰값

Reviewer가 `FIX_01.md` 2절에서 제시한 probe 항목을 동일하게 재현하여 측정한 결과 비교는 아래와 같습니다.

| 관찰 항목 | 수정 전 (Reviewer probe) | 수정 후 (Executor 재측정) | 판정 |
|---|---|---|---|
| `TOGGLE_HITBOX` | `width=44, height=24` | `width=44, height=44` | **통과 (최소 44px 충족)** |
| `CUSTOM_DRAFT_AFTER_SWITCH` | `typesafe/jev-1.13` | `my-custom-model` | **통과 (초안 보존)** |
| `POLICY_AFTER_SAVE` | `{"saving": false, "disabled": true}` | `{"saving": false, "disabled": false}` | **통과 (토글 활성화)** |
| `SEARCH_CLOSE_RESULT` (닫기 후 열림 여부) | `true` (닫히지 않음) | `false` (정상 닫힘) | **통과 (검색 중 닫기 작동)** |
| `SAME_STATUS_PHASE_REFRESHED` | `False` | `True` | **통과 (진단 변경 즉시 반영)** |
| `DIAGNOSTIC_SCROLL_AFTER_CHANGE` | `0` | `120` | **통과 (내부 스크롤 보존)** |

---

## 4. 실행 및 정적 검사 증거

1. **GitHub Actions 워크플로 정적 검사**:
   ```sh
   actionlint .github/workflows/check.yml
   ```
   - 결과: 오류 및 경고 0건 통과.

2. **Dockerfile 린트**:
   ```sh
   hadolint addon/Dockerfile
   ```
   - 결과: 오류 0건 통과.

3. **Python 린트 및 포맷 검사**:
   ```sh
   uv run ruff check addon/app tests scripts
   uv run ruff format --check addon/app tests scripts
   ```
   - 결과: `All checks passed!`, `21 files already formatted`.

4. **JavaScript 구문 검사 및 Git 공백 검사**:
   ```sh
   node --check addon/app/fhc/static/app.js
   git diff --check
   ```
   - 결과: 구문 오류 및 공백 이상 0건 통과.

5. **깨끗한 캐시 환경 브라우저 테스트 (R2 회귀 검증)**:
   ```sh
   PLAYWRIGHT_BROWSERS_PATH=/tmp/fhc-review-empty-browser-cache uv run pytest -q tests/test_browser_ui.py
   ```
   - 결과: **1 passed in 3.01s**.

6. **전체 단위/통합 테스트 스위트**:
   ```sh
   uv run pytest -q
   ```
   - 결과: **116 passed, 1 warning in 5.61s** (StarletteDeprecationWarning 1건 유지).

---

## 5. 검증 경계 및 환경 구분

| 구분 | 검증된 항목 (본 보고서 증거) | 미검증 / 잔여 항목 (출시 전 필요) |
|---|---|---|
| **브라우저 UI/UX** | 로컬 HTTP 서버 및 Chromium 환경에서 R1~R6 전체 검증, 320~430px 모바일 레이아웃 및 1280px 데스크톱 정렬 | 실제 모바일 디바이스 물리 터치스크린 조작, 200% 브라우저 줌 접근성 |
| **Home Assistant** | mock 환경(`FakeHA`) 기반 도메인·엔티티 목록 렌더링, 정책 PUT/GET 왕복, Ingress dev-session 인증 헤더 | 실제 HAOS 18.3 VM 환경에서의 Ingress 프록시 세션 및 Supervisor API 연동 |
| **LLM 모델** | OpenRouter 모델 드롭다운/커스텀 초안 저장 및 로드, 실패 시 입력 복구 | 유료 OpenRouter / Azure OpenAI 실호출 왕복 (비용/토큰 소비 방지) |
| **브랜딩 및 패키징** | 마스터 아이콘(1024×1024), 소셜 프리뷰(1280×640), 앱/파비콘 자산 생성 및 로컬 정적 서빙(200 OK) | HA 애드온 스토어 실제 렌더링 노출, GitHub 저장소 Social Preview 수동 업로드 |
| **CI / 빌드** | `check.yml` actionlint 검증 및 로컬 Dockerfile hadolint 검증 | GitHub 원격 Actions 워크플로 실행 및 멀티아키텍처(amd64/arm64) 빌드 push |

---

## 6. 결론 및 Reviewer 인계

`FIX_01.md`에서 지적된 2건의 P1 결함(정책 저장 후 토글 잠금, 깨끗한 CI의 Playwright 실행 실패)과 4건의 P2 결함(로그 스크롤 초기화, 모델 초안 유실, 검색 중 아코디언 미작동, 토글 터치 히트박스 부족)이 모두 수정되었으며, 실제 API 경로를 거치는 자동화 테스트를 통해 검증되었습니다.

관련 검증 문서(`docs/testing.md`, `docs/verification.md`)의 서술 또한 실제 관측된 수치와 한계에 부합하도록 정정되었습니다.

Reviewer의 재검토 및 판정을 요청합니다.
