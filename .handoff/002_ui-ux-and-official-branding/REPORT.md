# 운영 피드백 반영: UI/UX 편의성 및 공식 아이콘 통일 구현 보고서

- **작성일**: 2026-10-14
- **역할**: Executor
- **태스크**: `002_ui-ux-and-official-branding`
- **기준 커밋**: `02dc9d0877378e95bf9710aa37a7b17579fef67e` (브랜치: `dev`)
- **버전 갱신**: `0.2.0-dev.9` → `0.2.0-dev.10` (Python: `0.2.0.dev10`)
- **작업 상태**: 구현 완료 및 브라우저/자동화 검증 완료

---

## 1. 개요 및 구현 요약

`PLAN.md`에 정의된 7가지 요구사항(관리자 제어/조회 정렬, 정책 편집 시 펼침·검색·위치 유지, OpenRouter 모델 드롭다운 + 직접 입력, 로그 내부 스크롤과 열람 안정성, 모바일 최근 명령 2열 그리드, 추가 UI/UX 개선, 이미지 생성 도구 기반 공식 아이콘 및 전사 브랜딩 통일)을 모두 구현하고, 116개 자동 테스트 및 Playwright 기반 브라우저 회귀 테스트를 완벽히 통과했습니다.

---

## 2. 세부 구현 내역

### A. 관리자 제어/조회 정렬 (Admin Control/Query Alignment)
- **고정 너비 열 구조**: `.domain-summary`와 `.entity-row` 내부의 제어 및 조회 스위치를 각각 너비 `78px`의 독립된 flex 컨테이너(`.toggle-group`)로 캡슐화했습니다.
- **수직 열 일치 보장**: 기기 이름의 길이나 영역 지정 여부(`영역 미지정` 등)에 관계없이 모든 행의 '제어' 스위치와 '조회' 스위치의 X 좌표가 완벽하게 일치합니다.
- **터치 영역 및 상태 명확화**: 스위치 및 버튼에 터치 친화적 패딩(최소 40~44px 터치 영역), `focus-visible` 녹색 아웃라인, ON/OFF 명암 대비 및 transition을 적용했습니다.
- **비지원/조회 전용 처리**: `query_only` 또는 제어 미지원 엔티티의 경우 제어 스위치를 비활성화(`disabled`) 및 반투명 처리하되 동일한 `78px` 자리를 유지하여 정렬이 흐트러지지 않도록 구성했습니다.

### B. 정책 편집 시 펼침·검색·위치 유지 (Accordion State & Position Preservation)
- **도메인 펼침 상태 Set 보존**: `expandedDomains = new Set()`을 통해 사용자가 직접 펼친 도메인 목록을 메모리에 유지합니다.
- **네트워크 요청 없는 즉시 검색**: `entity-search` 입력 시 매번 서버로 GET 요청을 보내지 않고, 클라이언트에 캐시된 `cachedDomains` 데이터에서 동기적으로 필터링(`renderDomains()`)하여 타이핑 지연, 네트워크 깜빡임, 응답 순서 역전 현상을 완전히 해소했습니다.
- **검색 상태와 일반 상태 분리**: 검색어가 있을 때는 일치하는 도메인을 자동 펼쳐 보여주고, 검색어를 지우면 사용자가 원래 펼쳐두었던 `expandedDomains` 상태로 정확히 복원됩니다.
- **스크롤 위치 및 포커스 보존**: 정책 PUT(`updatePolicy`) 시 `window.scrollY`와 활성 요소(`document.activeElement`)의 `aria-label`을 저장하고, 갱신 완료 후 위치와 포커스를 원복합니다.
- **오류 및 진행 피드백**: 정책 저장 중에는 중복 클릭을 차단하고 `#policy-feedback`에 진행 및 오류 상태를 명시적으로 표시합니다.

### C. OpenRouter 모델 드롭다운 + 직접 입력 (Model Select & Custom Input)
- **네이티브 드롭다운 제공**: `#cfg-openrouter-model-select` 네이티브 select 요소를 통해 모바일과 데스크톱 모두에서 확실한 선택 UI를 제공합니다.
  - `microsoft/microsoft-decision-1` (Microsoft Decision-1)
  - `typesafe/jev-1.13` (Jev 1.13)
  - `custom` (직접 입력…)
- **직접 입력 필드 연동**: '직접 입력'을 선택하면 `#cfg-openrouter-custom-group` 및 `#cfg-openrouter-model` 입력창이 즉시 노출되고 포커스됩니다.
- **기존 값 및 전환 보존**: 저장된 모델이 후보 목록에 없을 경우 자동으로 `custom`으로 선택되어 해당 모델 ID가 텍스트 필드에 표시되며, 다른 설정을 저장하더라도 기존 모델 ID가 손실되지 않습니다.

### D. 로그 내부 스크롤과 열람 안정성 (Log Internal Scroll & Reading Stability)
- **뷰포트 최적화 내부 스크롤**: `.history-list`에 데스크톱 `max-height: 480px`, 모바일 `max-height: 55dvh` 및 `overflow-y: auto`, `overscroll-behavior: contain`을 적용했습니다. 다운로드/삭제 조작 영역은 스크롤 밖에 고정됩니다.
- **진단 JSON 스크롤 및 줄바꿈**: `.diagnostic-json`에 `max-height: 260px`, `overflow-y: auto`, `white-space: pre-wrap`, `overflow-wrap: anywhere`를 적용하여 긴 텍스트로 인한 화면 늘어남을 방지했습니다.
- **임의 8건 제한 제거**: 임의의 `.slice(0, 8)` 코드를 제거하고 `/api/history` 응답 전체(최대 50건)를 스크롤 목록에서 열람할 수 있도록 개선했습니다.
- **10초 주기 갱신 시 상태 보존**: request ID 기반 핑거프린트 비교를 통해 데이터 변경이 없을 때는 불필요한 DOM 재생성을 생략하며, 변경 시에도 `openDiagnostics` Set을 통해 사용자가 열어둔 `<details>` 진단 펼침 상태와 스크롤 위치를 그대로 유지합니다.
- **안내 및 삭제 확인**: 상단 메타 바에 `최근 최대 50건 표시 · 기본 다운로드: 최근 1일 내역 · 전체 보관: 옵션 설정 주기`를 명시하고, 이력 삭제 시 브라우저 confirm 확인 절차를 추가했습니다.

### E. 모바일 최근 명령 2열 (Mobile 2-Column Shortcuts)
- **모바일 2열 그리드 보장**: 모바일 미디어 쿼리(`@media (max-width: 640px)`)에서 `repeat(2, minmax(0, 1fr))`을 적용하여 320px/360px/390px/430px 전 뷰포트에서 정확히 2열을 유지합니다.
- **줄바꿈 및 가독성**: `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`를 해제하고 `word-break: keep-all; overflow-wrap: break-word; line-height: 1.4;`를 적용하여 긴 명령어도 잘림 없이 자연스럽게 읽을 수 있도록 개선했습니다.
- **빈 상태 및 버튼 피드백**: 빈 상태 안내 문구는 그리드 전체 너비(`grid-column: 1 / -1`)를 차지하며, hover/active/disabled 상태 피드백을 강화했습니다.

### F. 추가 UI/UX 개선
- **사용자 모드 헤더 간결화**: 상단 제목을 `빠른 AI 홈 리모컨`, 설명을 `자연어로 집 안의 가전과 조명을 즉시 제어하세요.`로 정돈하고 불필요한 기술적 문구를 배제했습니다.
- **명령 전송 실패 시 입력 보존**: 전송 실패(`rejected`, `failed`, `uncertain` 등) 또는 네트워크 예외 발생 시, 입력창이 비어 있다면 사용자가 방금 입력했던 문장을 `#command`에 자동으로 복원하여 재작성의 불편을 제거했습니다.
- **관리자 진입 시 즉각 갱신**: 관리자 모드 토글 클릭 즉시 `await loadStatus()`를 호출하여 연결 상태와 최근 탐색 일시를 즉시 갱신합니다.
- **가로 스크롤 완전 차단**: 모바일 관리자 헤더, 도메인 요약, 이력 액션 버튼에 flex-wrap 및 반응형 레이아웃을 적용하여 320px 극단적 좁은 화면에서도 가로 넘침이 발생하지 않습니다.

### G. 이미지 생성 기반 공식 아이콘과 노출 통일
- **이미지 생성 도구 실제 실행**: Antigravity 내장 `image-generator` 서브에이전트(Imagen 3 기반)를 호출하여 1024×1024 고해상도 공식 마스터 아이콘을 생성했습니다.
  - **콘셉트**: 스마트홈 원격 제어를 상징하는 직사각형 리모컨 실루엣 + 상단 원형 내비게이션 링 + 중앙을 역동적으로 관통하는 날렵한 번개(⚡) 에너지 엠블럼 + 브랜드 시그니처 에메랄드 그린 (`#158747`) / 다크 슬레이트 명암 대비.
  - **프롬프트 기록**: `docs/branding/BRANDING.md`에 원문 수록.
- **파생 자산 일괄 생성**: Python PIL(LANCZOS 리샘플러)을 활용하여 모든 플랫폼에 필요한 규격으로 단일 원본에서 파생했습니다.
  - `docs/branding/master-icon.png` (1024×1024 마스터 원본)
  - `docs/branding/social-preview.png` (1280×640 GitHub 소셜 미리보기 카드)
  - `addon/icon.png` (256×256 HA 애드온 스토어 아이콘)
  - `addon/logo.png` (512×512 HA 애드온 상세 로고)
  - `addon/app/fhc/static/favicon.ico` (16×16, 32×32, 48×48 멀티사이즈 파비콘)
  - `addon/app/fhc/static/icon-32.png` (32×32 헤더 및 탭 아이콘)
  - `addon/app/fhc/static/icon-192.png` (192×192 바로가기)
  - `addon/app/fhc/static/icon-512.png` (512×512 앱 아이콘)
  - `addon/app/fhc/static/apple-touch-icon.png` (180×180 iOS 홈 화면)

---

## 3. 공식 브랜드 자산 노출 매핑 표

| 노출 위치 | 적용 파일 및 상대 경로 | 적용 상태 및 검증 결과 |
|---|---|---|
| **웹 UI 헤더** | `addon/app/fhc/static/index.html` (`static/icon-32.png`) | 공식 마크 24×24px 배치, 텍스트 로고와 결합, 상대 경로 200 OK 로드 검증 완료 |
| **브라우저 탭 파비콘** | `static/favicon.ico`, `static/icon-32.png`, `static/icon-192.png` | `<head>` 내 relative link 추가, 다중 브라우저 MIME (`image/vnd.microsoft.icon`, `image/png`) 200 OK 검증 완료 |
| **모바일 홈 화면** | `static/apple-touch-icon.png` (180×180) | iOS Apple touch icon 메타 태그 추가 완료 |
| **HA 애드온 스토어** | `addon/icon.png` (256×256), `addon/logo.png` (512×512) | 저장소 루트 및 Supervisor 규격에 맞는 고해상도 PNG 배치 완료 |
| **HA Sidebar** | `addon/config.yaml` (`panel_icon: mdi:remote`) | **플랫폼 제약**: HA 사이드바는 Material Design Icons 식별자만 수용하며 이미지 파일 경로를 지원하지 않음. 콘셉트에 가장 부합하는 `mdi:remote` 유지 |
| **GitHub README** | `README.md` (`addon/icon.png`) | 상단 중앙에 공식 128×128 아이콘 렌더링 적용 완료 |
| **HA 애드온 문서** | `addon/DOCS.md` (`icon.png`) | 상단 중앙에 공식 96×96 아이콘 렌더링 적용 완료 |
| **GitHub Social Preview** | `docs/branding/social-preview.png` (1280×640) | 1280×640 전용 프리뷰 카드 파일 생성 완료. GitHub Web UI(`Settings > General > Social preview`) 업로드를 위한 자산 제공 (외부 수동 적용 필요) |

---

## 4. 변경된 파일 목록 및 사유

| 파일 | 변경 사유 |
|---|---|
| `addon/app/fhc/static/index.html` | 파비콘 메타 링크, 헤더 공식 로고 마크, 간결한 사용자 리모컨 문구, OpenRouter 모델 select/직접입력 그룹, 정책/이력 피드백 영역 추가, 버전 0.2.0-dev.10 표시 |
| `addon/app/fhc/static/app.js` | 도메인 펼침 상태 Set 관리, 클라이언트 캐시 기반 비동기 없는 즉시 검색, 제어/조회 78px 고정 토글 그룹 렌더링, 정책 PUT 시 스크롤/포커스 복원, OpenRouter 모델 select 연동, 로그 8건 제한 해제 및 details 펼침 상태 보존, 명령 실패 시 입력 복원, 관리자 진입 즉시 loadStatus 호출 |
| `addon/app/fhc/static/style.css` | 헤더 로고 아이콘, 모바일 최근 명령 2열 그리드 및 multiline 줄바꿈, 도메인/엔티티 제어/조회 정밀 수직 열 정렬, 44px 터치 영역/focus-visible, 히스토리 내부 스크롤(480px/55dvh), 진단 JSON 스크롤, 320~430px 반응형 줄바꿈 및 가로 오버플로 방지 |
| `addon/app/fhc/static/favicon.ico` | 16/32/48 ICO 다중 해상도 브라우저 파비콘 |
| `addon/app/fhc/static/icon-32.png` | 32×32 헤더 및 브라우저 파비콘 PNG |
| `addon/app/fhc/static/icon-192.png` | 192×192 PWA/웹 클립 바로가기 PNG |
| `addon/app/fhc/static/icon-512.png` | 512×512 고해상도 앱 아이콘 PNG |
| `addon/app/fhc/static/apple-touch-icon.png` | 180×180 iOS Safari 홈 화면 아이콘 PNG |
| `addon/icon.png` | 256×256 Home Assistant 공식 애드온 스토어 아이콘 |
| `addon/logo.png` | 512×512 Home Assistant 공식 애드온 상세 로고 |
| `docs/branding/master-icon.png` | 1024×1024 AI 생성 공식 마스터 아이콘 원본 |
| `docs/branding/social-preview.png` | 1280×640 GitHub 소셜 미리보기 카드 |
| `docs/branding/BRANDING.md` | 공식 브랜드 가이드, 프롬프트, 도구 및 자산 매핑 문서 |
| `tests/test_browser_ui.py` | Playwright Chromium 기반 정밀 UI/UX, 반응형, 정렬, 상태 보존, 에러 회귀 테스트 신규 추가 |
| `README.md` | 상단 공식 브랜드 로고 추가 |
| `addon/DOCS.md` | 상단 공식 브랜드 로고 추가 |
| `addon/config.yaml` | `version: 0.2.0-dev.10` 상향 |
| `addon/Dockerfile` | `BUILD_VERSION=0.2.0-dev.10` 상향 |
| `addon/app/fhc/__init__.py` | `VERSION = "0.2.0-dev.10"` 상향 |
| `pyproject.toml` | `version = "0.2.0.dev10"` 상향 |
| `uv.lock` | dev.10 패키지 버전 일치 갱신 |
| `addon/CHANGELOG.md` | 0.2.0-dev.10 릴리스 변경 내역 기록 |
| `docs/verification.md` | 0.2.0-dev.10 검증 및 브라우저 테스트 증거 문서화 |

---

## 5. 검증 실행 명령 및 결과

### 1) 자동화 코드 품질 및 유닛 테스트 검사
```sh
$ uv run ruff check addon/app tests scripts
All checks passed!

$ uv run ruff format --check addon/app tests scripts
21 files already formatted

$ uv run pytest -q
........................................................................ [ 62%]
............................................                             [100%]
116 passed, 1 warning in 5.42s

$ node --check addon/app/fhc/static/app.js
# Exit code 0 (문법 오류 없음)

$ git diff --check
# Exit code 0 (공백 오류 없음)

$ hadolint addon/Dockerfile
# Exit code 0 (Dockerfile 모범사례 준수)

$ gitleaks git --verbose
4:01PM INF 27 commits scanned.
4:01PM INF no leaks found

$ uv export --frozen --no-dev --no-emit-project --no-hashes --no-header --output-file /tmp/requirements.txt && diff addon/requirements.txt /tmp/requirements.txt
# Exit code 0 (애드온 requirements.txt 완전 일치)
```

### 2) Playwright 브라우저 회귀 테스트 (`tests/test_browser_ui.py`)
- **실행 명령**: `uv run pytest tests/test_browser_ui.py -v`
- **결과**: `1 passed in 3.24s`
- **주요 검증 항목**:
  1. **헤더 & 브랜딩**: `.logo-icon`(`static/icon-32.png`, 200 OK, image/png), 파비콘 링크 및 애플 터치 아이콘 정상 로드.
  2. **사용자 모드**: 간결한 리모컨 헤드라인 및 서브타이틀 확인.
  3. **관리자 모드 전환**: `#mode-toggle` 토글 시 즉시 화면 전환 및 `aria-pressed` 상태 확인.
  4. **OpenRouter 모델 드롭다운**:
     - `microsoft/microsoft-decision-1` 선택 시 직접 입력 필드 숨김.
     - `typesafe/jev-1.13` 선택 시 직접 입력 필드 숨김 및 값 동기화.
     - `custom` 선택 시 직접 입력 필드 노출 및 포커스.
  5. **제어/조회 토글 X좌표 열 일치**:
     - 조명 도메인 엔티티 3개 행의 Control 토글 X좌표: 모두 동일(`ctrl_x_coords` 단일값).
     - Query 토글 X좌표: 모두 동일(`query_x_coords` 단일값).
     - Control 열이 Query 열보다 선행 배치됨 확인.
  6. **정책 저장 시 펼침 상태 유지**:
     - 엔티티 토글 클릭 시 PUT 완료 후에도 도메인 아코디언이 닫히지 않고 펼침 유지 확인.
  7. **캐시 기반 엔티티 검색**:
     - `보조 조명` 검색 시 1개 행 즉시 필터링.
     - 검색어 삭제 시 원래 펼쳐두었던 아코디언이 그대로 펼쳐진 상태 복원 확인.
  8. **로그 내부 스크롤 및 진단 유지**:
     - 25건 샘플 항목 전체 렌더링 확인 (8건 잘림 없음).
     - 진단 `<details>` 펼침 후 `loadHistory()` 갱신 시에도 details 열림 상태 유지 확인.
  9. **모바일 2열 그리드 및 오버플로 검사**:
     - 320px, 360px, 390px, 430px 전 뷰포트에서 `scrollWidth <= clientWidth` 확인 (가로 넘침 0건).
     - 모바일에서 `.shortcuts-grid`의 `grid-template-columns`가 2열(`repeat(2, minmax(0, 1fr))`)로 렌더링됨 확인.
  10. **명령 실패 시 입력 복원**:
      - 실패/미지원 응답 시 `#command` 텍스트 박스에 입력 문장 복원 확인.
  11. **콘솔 무오류**: 페이지 로드 및 모든 인터랙션 중 `pageerror` 및 콘솔 에러 0건.

### 3) 렌더링 캡처 증거
`.handoff/002_ui-ux-and-official-branding/screenshots/`에 실 브라우저 렌더링 스크린샷 보관:
- `desktop-user-mode.png`: 데스크톱 사용자 간결 리모컨 화면
- `desktop-admin-mode.png`: 데스크톱 관리자 모드 (수직 열 정렬된 엔티티 토글, 모델 드롭다운, 스크롤 가능한 로그 및 진단 열림)
- `mobile-user-mode-390px.png`: 모바일(390px) 2열 최근 명령 바로가기 및 간결 리모컨
- `mobile-admin-mode-390px.png`: 모바일(390px) 관리자 설정 및 가로 넘침 없는 엔티티 토글

---

## 6. 계획 대비 변경 및 잔여/외부 작업 안내

- **계획 대비 변경 사항**: 없음. `PLAN.md`에 기재된 모든 원칙과 제약(API 엔진 보존, zero-config 유지, Supervisors 옵션 보존, Ingress 상대 경로 준수)을 100% 충족하며 구현했습니다.
- **외부 수동 작업 필요 항목**:
  - **GitHub 저장소 Social Preview**: `docs/branding/social-preview.png` 파일이 생성되었으므로, 저장소 관리 권한을 가진 사용자가 GitHub 웹 UI(`Settings > General > Social preview`)에서 해당 이미지를 업로드해야 합니다.
  - **HA Sidebar**: Home Assistant 플랫폼 구조상 Material Design Icons 식별자(`panel_icon: mdi:remote`)만 지원하므로, 사용자 정의 PNG를 임의 연결할 수 없어 가장 적합한 `mdi:remote`를 유지했습니다.
- **후속 Dev 배포 준비**:
  - `0.2.0-dev.10`으로 코드 및 설정 버전 일치 완료.
  - Reviewer 승인 후 기존 `docs/releases.md` 절차에 따라 git tag(`v0.2.0-dev.10`) 및 GitHub prerelease 발행을 진행할 수 있습니다.
