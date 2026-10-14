# Executor 교정 완료 보고서 (FIX_02)

작성일: 2026-10-14 · 역할: Executor · 대상: `.handoff/002_ui-ux-and-official-branding/FIX_02.md`

---

## 1. 개요 및 요약

Reviewer가 제시한 `FIX_02.md`의 교정 요구사항(R1, R2, R3) 및 테스트 보완 사항(Section 3)을 모두 구현하고 로컬 환경에서 엄밀하게 검증 완료했습니다.

- **R1 로그 앵커 좌표계 일치 및 위치 보존**: `child.offsetTop` 대신 `getBoundingClientRect()` 기반 부모-자식 상대 좌표 계산 도입, `.history-list`에 `position: relative` 부여, `focus({ preventScroll: true })` 적용. 선행 행 확장 및 상단 새 항목 삽입 시 기준 카드의 가시 뷰포트 상대 위치 안정 유지.
- **R2 도메인 조회 경합 방지 및 정책 저장 생명주기 완결**: 요청 세대 카운터 `domainsRequestSeq` 도입으로 구세대 GET 응답 자동 폐기. 정책 PUT 실행부터 후속 최신 GET 수신 완료 시점까지 `isPolicySaving = true`를 유지하여 경합 및 비정상 상태 차단.
- **R3 로그 변경 감지 지문(fingerprint) 필드 완전화**: `makeHistoryFingerprint`에 `providers`, `created`, `text`를 포함하여 공급자 진단 상태 변경 시 지연 없는 즉시 렌더링 보장.
- **Section 3 테스트 무결성 강화**: `page.evaluate()` 편법 없이 실제 Playwright route hold와 실시간 사용자 입력 상호작용으로 대기 중 입력 문장 보존 검증. Playwright route interception lifecycle 정밀화로 비동기 교착(deadlock) 및 `Route is already handled` 오류 원천 해소.

---

## 2. 세부 교정 내역

### R1 — 로그 앵커 좌표계 일치 및 상대 위치 복원 (`addon/app/fhc/static/app.js`, `style.css`)

- **원인 분석**:
  - `container.scrollTop`은 `.history-list` 내부 스크롤 좌표이나, `child.offsetTop`은 `offsetParent === document.body` 기준이어서(페이지 레이아웃상 약 3500px 지점) 서로 다른 좌표계가 비교되고 있었습니다.
  - 이로 인해 실제 목록 상단에 위치한 가시 행이 아닌 첫 행을 앵커로 오인식하여, 선행 행의 높이가 변할 때 읽고 있던 행을 놓치는 문제가 있었습니다.
- **수정 내용**:
  1. `addon/app/fhc/static/style.css`: `.history-list`에 `position: relative;`를 명시.
  2. `addon/app/fhc/static/app.js`:
     - 앵커 탐색 시 `row.getBoundingClientRect()`와 `container.getBoundingClientRect()`를 사용하여 컨테이너 상단 대비 자식의 상대 좌표(`childRect.top - containerRect.top`)를 계산.
     - 뷰포트 내(상대 좌표 >= -10 및 < containerHeight)에 위치한 행 중 가장 상단에 근접한 행의 `requestId`와 `anchorRelativeTop`을 앵커로 보존.
     - 렌더링 후 앵커 요소를 찾아 현재 상대 좌표(`currentRelativeTop`)와의 차이만큼 컨테이너 스크롤을 보정:
       ```javascript
       const currentRelativeTop = anchorEl.getBoundingClientRect().top - container.getBoundingClientRect().top;
       container.scrollTop += (currentRelativeTop - anchorRelativeTop);
       ```
     - 포커스 복원 시 브라우저 기본 스크롤 강제 점프를 방지하도록 `activeEl.focus({ preventScroll: true })` 적용.

### R2 — 도메인 조회 세대 가드 및 정책 저장 락 완결 (`addon/app/fhc/static/app.js`)

- **원인 분석**:
  - `loadDomains(true)` 호출 간 순서 보장이 없어, 지연된 구 GET 응답이 최신 PUT 이후의 fresh GET 응답을 덮어쓸 위험이 있었습니다.
  - 정책 PUT 완료 직후 GET 완료 전에 `isPolicySaving = false`로 일찍 풀려 검색/목록 토글 등의 재렌더링 시 잠금이 조기 해제되는 틈새가 있었습니다.
- **수정 내용**:
  1. 모듈 전역에 요청 순번 카운터 `let domainsRequestSeq = 0;` 정의.
  2. `loadDomains(refresh)` 시작 시 `const currentSeq = ++domainsRequestSeq;`를 발급하고, 응답 수신 후 `if (currentSeq !== domainsRequestSeq) return;`으로 구세대 응답을 무조건 폐기.
  3. `updatePolicy()`의 `try ... finally` 블록에서 PUT 요청과 후속 `await loadDomains(true)`가 모두 끝날 때까지 `isPolicySaving = true`를 유지하고, `finally`에서만 `isPolicySaving = false`로 환원 및 `renderDomains()` 호출:
     ```javascript
     isPolicySaving = true;
     renderDomains();
     try {
       const res = await fetch(withBase('/api/policy'), { method: 'PUT', ... });
       if (!res.ok) throw new Error(...);
       await loadDomains(true);
     } catch (err) {
       showFeedback('정책 변경 실패: ' + err.message, 'error');
       await loadDomains(true);
     } finally {
       isPolicySaving = false;
       renderDomains();
       // focus 복원
     }
     ```

### R3 — 진단 지문(fingerprint) 필드 완전화 (`addon/app/fhc/static/app.js`)

- **원인 분석**:
  - `makeHistoryFingerprint()`에 `providers`, `created`, `text`가 누락되어 동일 요청 ID/status 내에서 공급자 진단 배열만 갱신될 경우 렌더링 갱신이 생략되었습니다.
- **수정 내용**:
  - `makeHistoryFingerprint`에 `providers: i.providers`, `created: i.created`, `text: i.text`를 추가하여 DTO 내 렌더링 관련 필드 변경 시 즉시 DOM이 갱신되도록 보장.

### Section 3 — 테스트 무결성 강화 및 비동기 인터셉트 안정화 (`tests/test_browser_ui.py`)

- **대기 중 입력 보존 실제 브라우저 인터랙션 검증**:
  - `page.evaluate()` 내부 조건문 검증 대신, `/api/commands` 경로를 route 인터셉트하여 대기 상태로 유지한 뒤 사용자가 실제로 `#command`에 새 문장을 타이핑하도록 구현.
  - 대기 중인 원본 요청에 503 오류를 반환한 후, 제품 코드의 복원 로직이 사용자가 방금 입력한 새 문장을 덮어쓰지 않고 온전히 보존하는지 검증.
- **R1~R3 신규 회귀 테스트 추가**:
  - **R1**: 이력 목록 50건 렌더링 후 중간 항목 스크롤 위치에서 앞쪽 행 확장 및 최상단 새 항목 추가 시 앵커 행의 가시 영역 상대 위치가 보존되는지 검증.
  - **R2**: 지연된 구 GET 응답 도착 시 신규 데이터가 덮어써지지 않고 무시되는지 검증 및 PUT 실패 시의 정상 복구 검증.
  - **R3**: 동일 상태 코드에서 `providers` 진단 필드가 변경되었을 때 화면에 즉시 반영되는지 검증.
- **Playwright 비동기 라우트 안정성**:
  - `page.unroute` 조기 호출로 인한 `Route is already handled` 오류 방지를 위해 핸들러 내부 `intercept` 플래그 제어로 1회차 지연 캡처 및 후속 실서버 전송 분기 구현.
  - `page.evaluate` 반환 Promise 대기 교착(deadlock) 방지를 위해 `setTimeout(() => { void loadDomains(true); }, 0)` 패턴 적용.

---

## 3. 검증 결과 및 실행 명령

### 1) 자동 테스트 (pytest)
```bash
# 브라우저 종합 UI 테스트 (Playwright Chromium)
PLAYWRIGHT_BROWSERS_PATH=/tmp/fhc-review-empty-browser-cache uv run pytest -q tests/test_browser_ui.py
# 결과: 1 passed in 4.52s

# 전체 테스트 스위트
uv run pytest -q
# 결과: 116 passed, 1 warning in 6.65s (FastAPI TestClient httpx2 deprecation warning)
```

### 2) 정적 분석, 린터 및 포맷 검사
```bash
uv run ruff check addon/app tests scripts
# 결과: All checks passed!

uv run ruff format --check addon/app tests scripts
# 결과: 21 files already formatted

node --check addon/app/fhc/static/app.js
# 결과: 구문 오류 없음 (exit code 0)

git diff --check
# 결과: 공백/포맷 결함 없음 (exit code 0)

actionlint .github/workflows/check.yml
# 결과: 통과 (exit code 0)

hadolint addon/Dockerfile
# 결과: 통과 (exit code 0)
```

---

## 4. 작업 트리 및 검증 경계 (V1 관련)

### 현재 Git 상태
- 기준 커밋: `02dc9d0877378e95bf9710aa37a7b17579fef67e` (브랜치 `dev`)
- 수정 파일 (Tracked):
  - `.github/workflows/check.yml`
  - `README.md`, `addon/CHANGELOG.md`, `addon/DOCS.md`, `addon/Dockerfile`, `addon/config.yaml`, `addon/app/fhc/__init__.py`
  - `addon/app/fhc/static/app.js`, `addon/app/fhc/static/index.html`, `addon/app/fhc/static/style.css`
  - `docs/testing.md`, `docs/verification.md`, `pyproject.toml`, `uv.lock`
- 신규 파일 (Untracked):
  - `.handoff/002_ui-ux-and-official-branding/` (PLAN, REPORT, FIX_01, FIX_01_REPORT, FIX_02, FIX_02_REPORT)
  - `tests/test_browser_ui.py`
  - 브랜드 이미지: `addon/icon.png`, `addon/logo.png`, `addon/app/fhc/static/*.png`, `docs/branding/*`

### 검증 경계 명시
- **로컬 검증 완료 범위**:
  - Python Playwright Chromium 브라우저 환경에서 실제 렌더링, 레이아웃, 터치 영역(44×44px), 비동기 경합, 앵커 보존, 키보드 접근성, 모델 입력 보존 검증 완료.
  - 단위/통합/계약 116개 테스트 및 모든 정적 분석 도구 통과.
- **원격 / 라이브 설치 잔여 범위 (V1 경계)**:
  - 본 검증은 로컬 FakeHA 환경에서 수행되었으며, 실제 운영 Home Assistant 및 실제 유료 모델 API 호출은 포함하지 않습니다.
  - 원격 GitHub Actions CI 실행 및 프로젝트 전용 HAOS(QEMU/KVM) 내 dev.10 애드온 실제 빌드/설치 확인은 커밋/푸시 이후 단계에서 진행되며, Reviewer의 최종 확인 및 승인 전에는 tag/prerelease를 임의 생성하지 않습니다.
