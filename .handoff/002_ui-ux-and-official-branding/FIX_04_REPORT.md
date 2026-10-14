# FIX_04 실행 보고서 — 공개 기록 정정 및 실제 Ingress UI·모델·ZIP 검증 보강

작성일: 2026-10-15 · 역할: Executor · 대상: `FIX_04.md`(Reviewer 재검토 R1/R2) · 제품 코드 변경: 없음(app 소스 `a4d89c6` 유지)

## 1. 시작 상태와 범위 확인

- 기준: dev 브랜치 HEAD `8150d27`(app 소스 `a4d89c6`), working tree는 FIX_04.md 미추적 상태를 제외하고 깨끗했다.
- 테스트 자원: 전용 HAOS VM `fhc-test-haos`(stopped)을 `.local/test-resources.json`의 `start_argv`로 기동, HA Core 2026.10.1 응답 확인 후 애드온 `a1444ce0_fast_home_control_dev` 상태 `stopped`→`started`(버전 `0.2.0-dev.10`, 변경 없이 재기동)로 검증 환경을 복원했다. 운영 HA는 조작하지 않았다.
- 이번 라운드는 제품 코드·이미지 재생성 없이 문서·검증 보강만 수행(FIX_04 §4)한다. 검증 중 발견된 날짜 고정 테스트 1건은 테스트 코드만 교정했다(§5).

## 2. R1 — 공개 기록 정정표(정정 전 → 실제 확인값 → 조치)

| 항목 | 정정 전 기록(출처) | 실제 확인값(방법) | 조치 |
|---|---|---|---|
| `addon/icon.png` | 512×512 (v0.2.0-dev.10 릴리스 본문, FIX_03_REPORT) | 256×256 PNG (`file addon/icon.png`) | 릴리스 본문 정정, `docs/verification.md` FIX_04 절에 기록. 자산 자체는 설치·검증된 값 유지(재생성하지 않음) |
| `addon/logo.png` | 1024×512 (같은 출처) | 512×512 PNG (`file addon/logo.png`) | 동일 |
| 사이드바 아이콘 | `icon: mdi:home-automation` (FIX_03_REPORT 및 dev.10 검증 문서 한계 절) | `panel_icon: mdi:remote` (`addon/config.yaml:16`, BRANDING.md와 일치) | `docs/verification.md` 정정 |
| 마스터/소셜 자산 | 1024×1024 / 1280×640 | 1024×1024 / 1280×640 (`file` 확인) | 오류 아님, 유지 |
| 스토어 아이콘 노출 근거 | "스토어 노출 확인"으로 읽힐 수 있는 서술 | Supervisor `/addons/{slug}/info`의 `icon=true`, `logo=true`는 **자산 제공 메타데이터**다. `/store/{slug}/icon`·`/addons/{slug}/icon` HTTP 엔드포인트는 이 Supervisor에서 unknown_error(미노출). **스토어 목록/상세 화면 렌더링 캡처는 미수행** | 메타데이터/Ingress 확인과 구분해 `docs/verification.md`·릴리스 본문에 제한으로 명시. 확인하지 못한 것을 화면 노출로 주장하지 않음 |
| README 공개 이미지 | — | `https://raw.githubusercontent.com/Kanu-Coffee/fast-home-control/dev/addon/icon.png` → 200 `image/png` (44,881 bytes), README `<img src="addon/icon.png">` 정상 노출 | 렌더링 확인 결과를 문서에 기록 |
| Social preview | — | 파일(`docs/branding/social-preview.png` 1280×640)만 커밋 상태 | GitHub 설정 수동 업로드 **잔여**로 README 노출 확인과 구분 기록 |
| FIX_03_REPORT | "생성이 가능합니다"(게시 전 시점) | [v0.2.0-dev.10 prerelease](https://github.com/Kanu-Coffee/fast-home-control/releases/tag/v0.2.0-dev.10) 실재, `refs/tags/v0.2.0-dev.10` → `8150d27` (`git ls-remote`), 본문은 이번 라운드에서 `gh release edit`으로 실제 갱신·재게시 | FIX_03_REPORT는 보존하고 본 보고서에 정정표 기록. 게시 사실을 완료로 갱신 |

## 3. R2 — 실제 Ingress UI 검증 보강 (Round A 교훈 → Round B)

Round A(dev.10 설치 검증 당시)의 한계를 정확히 재인식했다: 정책 변경은 API PUT 1회, Playwright는 진입·hitbox만, 모델 저장 코드 부재, ZIP은 원문 텍스트 제외만 검사. Round A의 모델 드롭다운 재로드 판정 자체도 loadConfig 완료 전 선행 읽기 경합이 있었고 첫 draft 저장 POST는 조기 재로드에 중단된 사실이 `.local/fix04-r2-verification.json`의 `fix04_note`에 남아 있다. 아래는 응답을 대기하도록 교정한 Round B 결과다.

### 3.1 실제 Ingress 관리자 UI 연속 편집 (`fix04-admin-policy-ui.png`)

light·switch 두 도메인 아코디언을 펼친(`aria-expanded=true`) 상태에서 Chromium(1280×900)으로 다음 3개를 **연속 클릭 저장**했다.

| 순서 | 조작 | busy lock | 저장 후 재활성 | 포커스 복원 | 펼침 유지 | 집계 갱신 | PUT |
|---|---|---|---|---|---|---|---|
| 1 | `light.ceiling_lights` 제어 토글(허용→차단) | ○ | ○ | ○ | ○ | 제어 허용 7→6 | 200 |
| 2 | `switch` 도메인 조회 토글(허용→차단) | ○ | ○ | ○ | ○ | 조회 허용 2→0 표시 | 200 |
| 3 | `switch.ac` 제어 토글(허용→차단) | ○ | ○ | ○ | ○ | 제어 허용 2→1 | 200 |

- 검증 방법: 클릭 직전 활성 상태였던 토글 집합이 저장 중 전부 비활성(busy)→ 완료 후 전부 재활성되는 주기를 페이지 내 10ms 폴링으로 관찰, `document.activeElement`가 재렌더된 동일 식별자 토글인지 확인, `.domain-count` 집계 문구 전후 비교, 네트워크 응답(`PUT /api/policy` 200 ×3) 대조. 검색·스크롤은 페이지 유지 동작(직접 스크롤 복원 로직)으로 유지됐다.

### 3.2 실제 모델 드롭다운 (`fix04-admin-model-custom.png`)

- Jev 1.13 선택 → 설정 저장: `POST /api/config` **200** 대기 후 재로드, 재로드 시 GET `/api/config` 응답을 기다린 다음 셀렉트 값 = `typesafe/jev-1.13` 확인.
- '직접 입력' → 초안 `custom/fix04-draft-probe` → 저장 200 → 재로드: 셀렉트 `custom`, 입력창 초안 문자열 유지, `GET /api/config`의 `openrouter_model` = 초안 확인. POST `/api/config`는 옵션 저장만 수행하고 공급자 상태를 `configured_unverified`로 표시(main.py:287–305) — 실제 모델 API 호출 없음.
- 애드온 재시작(Supervisor restart) 후: 버전 `0.2.0-dev.10`, 모델 초안·정책 delta(ceiling/ac 차단, switch 조회 차단) **API와 실제 UI 재진입(`fix04-admin-after-restart.png`: 셀렉트 `custom`+초안, 차단 토글 표시) 양쪽에서 보존 확인**.
- 원복: UI에서 Microsoft preset 재저장(POST 200), 정책은 baseline 유효값으로 PUT 후 `GET /api/policy` 실효값이 baseline과 일치(`final_policy_effective_equals_baseline: true`, revision 12).

### 3.3 진단 ZIP 검사 범위(정정)

정상 조명 명령 성공(`succeeded`, 2×turn_off sent) 이력 상태에서 기본 익명화 내보내기 3개 파일(`manifest.json`/`summary.json`/`requests.jsonl`) 전문을 메모리에서 검사:

- 원문 명령 텍스트 미포함: `false`(없음) 확인.
- 비밀값 미포함(bool로만 기록, 값·원문 출력/커밋 없음): OpenRouter API 키(73자)·HA access token(183자)·HA refresh token(128자)·Ingress 세션 토큰(128자) 모두 **포함되지 않음**.
- 검사하지 못한 범위(정직한 제한): Azure 키는 이 환경에 미설정이라 대상에서 제외, Supervisor 주입 토큰 자체는 검증 환경에서 값 확보 불가로 미검사. 따라서 "전체 토큰 검증"이 아니라 위 4종+원문 텍스트 검사 범위로 기록한다.

### 3.4 증거와 정리

- 증거: `.local/fix04-r2-verification.json`(Ingress 경로 해시·쿠키·토큰 값 제외, API 경로 suffix만 기록), `.local/fix10-install-verification.json`(Round A), 스크린샷 3종 `.handoff/002_ui-ux-and-official-branding/screenshots/fix04-*.png`.
- 검증 완료 후 테스트 VM을 monitor socket `system_powerdown`(ACPI)으로 정상 종료하고 qemu 프로세스 소멸을 확인, `.local/test-resources.json`을 `state=stopped`, `last_tested_app=a4d89c6`, `last_tested_version=0.2.0-dev.10`으로 갱신했다. 운영 VM·HA는 미변경.

## 4. 문서·공개물 갱신

- `docs/verification.md` dev.10 절: Round A 서술을 "정책 저장 API 검증"으로 재명명, ZIP 검사 범위 정정, FIX_04 보강 절 신설(R1 정정 내역·R2 UI/모델/재시작/ZIP 결과·제한 명시), 사이드바 `mdi:remote` 정정, 스토어 노출 근거를 메타데이터로 구분.
- 공개 릴리스 [v0.2.0-dev.10](https://github.com/Kanu-Coffee/fast-home-control/releases/tag/v0.2.0-dev.10): 자산 크기 정정(256×256/512×512), 검증 상태를 실제 UI 연속 편집·모델 보존·ZIP bool 검사 범위로 갱신, 스토어 화면 미캡처 제한 명시, 과거 오기재 정정 문구 포함. `gh release edit`으로 실제 재게시했으며 태그 target(`8150d27`)과 앱 소스는 변동 없다.
- 기존 handoff 문서(FIX_03_REPORT 포함)는 덮어쓰지 않았다. Dev prerelease 게시 사실은 완료 기록으로 유지하고, Main/안정 승격은 여전히 사용자 명시 승인 대상이다.

## 5. 계획 외 발견 교정 (테스트 코드만)

- `tests/test_corrections.py::test_fix05_r2_readonly_calendar_get_events_end_to_end`가 작성일 기준 고정 날짜(`2026-10-15`/`16`)로 실제 시계의 "tomorrow"를 단정해 작성 익일(KST 10-15)부터 실패했다. 제품 코드는 정상이며(창 계산 actions.py:230–238), 테스트만 Asia/Seoul 실시간에서 tomorrow/day_after를 유도하도록 교정했다. 이 교정 없이는 다음 CI 실행도 실패하므로 검증 인프라 결함으로 판단했다. 제품 코드·이미지는 미변경이다.

## 6. 실행한 검증

- `uv run pytest -q`: **116 passed**(기존 Starlette deprecated warning 1개, 제품 코드 미변경으로 dev.10 검증과 동일 소스).
- `ruff check`/`ruff format --check`(addon·tests·scripts), `node --check app.js`, `git diff --check` 통과.

## 7. 잔여 제한

- 스토어 목록/상세 화면 캡처 미수행(메타데이터·Ingress 자산 제공까지 확인).
- ZIP 비밀 검사는 §3.3의 4종+원문 범위이며 Azure 키(미설정)·Supervisor 주입 토큰(값 확보 불가)은 미검사.
- ARM 실기동은 CI 컨테이너 빌드와 구분되며 이번 라운드에서 반복하지 않았다.
- Social preview 수동 업로드 잔여는 GitHub 웹 UI 권한 작업으로 유지.

위 R1 정정과 R2 보강이 해소되었으므로, 다음 Reviewer의 기록·증거 대조와 REVIEW 종료 판정에 맡긴다.
