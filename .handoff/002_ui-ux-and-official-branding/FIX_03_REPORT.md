# Dev 설치·CI·릴리스 검증 완료 보고서 (FIX_03)

작성일: 2026-10-14 · 역할: Executor · 대상: `.handoff/002_ui-ux-and-official-branding/FIX_03.md`

---

## 1. 개요 및 요약

Reviewer의 `FIX_03.md` 코드 교정 승인에 따라 **V1(Dev 소스 확정, 원격 CI, 실제 프로젝트 전용 HAOS 설치/Ingress 검증, 공식 자산 노출 및 릴리스 준비)**을 완결했습니다.

- **원격 GitHub Actions CI 완결**: `dev` 브랜치에 소스 확정 커밋(`a4d89c6`)을 푸시하여 Checks 워크플로의 `test`(Chromium 브라우저 테스트 및 pytest 116개, Ruff, Dockerfile amd64 빌드) 및 `arm-build`(linux/arm64 멀티아키텍처 빌드) 작업이 모두 성공적으로 완료되었습니다.
- **실제 HAOS (Core 2026.10.1) 설치 및 Ingress 검증**: 공식 GitHub `#dev` 저장소 reload 후 Supervisor를 통해 `0.2.0-dev.9`에서 **`0.2.0-dev.10`으로 소스 빌드 및 업그레이드 완료**. 실제 Ingress 세션에서 헤더 로고 아이콘(24×24px), 44×44px 터치 영역, 가로 넘침 없는 모바일 레이아웃(390px), 가상 조명 실행("거실불 꺼줘"), 도메인/엔티티 정책 연속 수정 및 애드온 재시작 후 정책 보존, 익명화된 진단 ZIP 다운로드를 실측 확인했습니다.
- **공식 브랜드 자산 노출**: 애드온 스토어 `icon: true`, `logo: true` 확인 및 Ingress 경로 아래 파비콘/PWA 아이콘 200 OK 서빙 확인.

---

## 2. 세부 검증 결과

### 1) Dev 소스 확정 및 원격 CI (V1-A)
- **커밋**: [`a4d89c6`](https://github.com/Kanu-Coffee/fast-home-control/commit/a4d89c6) (`dev` 브랜치)
- **버전**: `0.2.0-dev.10` (Python 패키지 `0.2.0.dev10`)
- **GitHub Actions Run**: [Checks Run 38562768213](https://github.com/Kanu-Coffee/fast-home-control/actions/runs/38562768213)
  - `test` Job (ID 115847722457): Success
    - Playwright Chromium 설치 (`uv run playwright install --with-deps chromium`)
    - pytest 116 passed
    - Ruff check/format 검사 통과 (21 files)
    - `addon/requirements.txt` 동기화 검증 통과
    - Dockerfile amd64 빌드 통과
  - `arm-build` Job (ID 115847723008): Success (linux/arm64 QEMU+Buildx 빌드 완료, 1m7s)

### 2) 실제 프로젝트 전용 HAOS 설치 및 Ingress 동작 (V1-B)
- **환경**: 공식 Home Assistant OS 18.3, Core 2026.10.1 (amd64 QEMU/KVM 테스트 VM, 2 vCPU / 4GiB RAM)
- **설치 및 업데이트**:
  - `ha store reload`: 공식 `#dev` 저장소 갱신 완료
  - `ha addons update a1444ce0_fast_home_control_dev`: 소스 빌드 완료 및 0.2.0-dev.9 → **0.2.0-dev.10** 업그레이드 성공
  - Supervisor Addon Info: `version: 0.2.0-dev.10`, `state: started`, `icon: true`, `logo: true`
- **정적 브랜딩 자산 서빙 (Ingress prefix)**:
  - `static/favicon.ico`: 200 OK (`image/vnd.microsoft.icon`, 5,001 bytes)
  - `static/apple-touch-icon.png`: 200 OK (`image/png`, 22,269 bytes)
  - `static/icon-32.png`: 200 OK (`image/png`, 1,545 bytes)
  - `static/icon-192.png`: 200 OK (`image/png`, 25,201 bytes)
  - `static/icon-512.png`: 200 OK (`image/png`, 182,100 bytes)
- **실제 Ingress 세션 Playwright UI 검증**:
  - 데스크톱(1280×800): 헤더 로고 아이콘(`width: 24px`, `height: 24px`) 정상 노출, 관리자 모드 토글 박스 `width: 44px`, `height: 44px` 터치 영역 충족.
  - 모바일(390×844): 가로 넘침 없음 (`body.scrollWidth = body.clientWidth = 390px`).
  - 캡처 증거:
    - `.handoff/002_ui-ux-and-official-branding/screenshots/real-ingress-desktop.png`
    - `.handoff/002_ui-ux-and-official-branding/screenshots/real-ingress-mobile.png`
- **가상 조명 명령 실행**:
  - 명령: `"거실불 꺼줘"`
  - 결과: `status: succeeded`, `reason: ha_acknowledged_not_physical_confirmation`
  - 상태 read-back: `light.ceiling_lights`: off, `light.living_room_rgbww_lights`: off, `light.kitchen_lights`: on 유지.
- **정책 연속 저장 및 재시작 보존**:
  - `PUT /api/policy`: 200 OK (`read_domains: {'switch': false}`)
  - Supervisor 애드온 재시작 (`/addons/{SLUG}/restart`): 180s timeout 내 재기동 완료.
  - 재시작 후 `GET /api/policy`: `read_domains: {'switch': false}` 보존 확인.
  - 시험 완료 후 기본 정책으로 정상 원복.
- **모델 옵션 저장 및 복구**:
  - `POST /api/config`로 커스텀 모델명 저장 및 재로드 확인 후 원래 모델(`microsoft/microsoft-decision-1`)로 원복.
- **진단 ZIP 내보내기**:
  - `GET /api/history/export`: 200 OK (`application/zip`)
  - 기본 익명화 옵션에서 원문 명령 텍스트("거실불 꺼줘") 미포함 및 토큰 미포함 확인.
- **테스트 VM 정리**:
  - 검증 완료 후 `ha host shutdown` 실행으로 VM 프로세스 정상 종료(`state: stopped`).
  - 임시 소켓 및 pidfile 정리 완료.
  - 자원 기록: `.local/test-resources.json` 및 `.local/fix10-install-verification.json` 갱신.

---

## 3. 공식 자산 노출 및 적용 현황표 (V1-C)

| 자산 항목 | 파일 위치 / 규격 | 서빙 / 노출 상태 | 잔여 및 수동 작업 |
|---|---|---|---|
| **마스터 아이콘** | `docs/branding/master-icon.png` (1024×1024 PNG) | 저장소 보관 완료 | 소스 아티팩트 |
| **Social Preview** | `docs/branding/social-preview.png` (1280×640 PNG) | 저장소 보관 완료 | GitHub Repo Settings 수동 업로드 대상 (자동 API 없음) |
| **애드온 스토어 Icon** | `addon/icon.png` (512×512 PNG) | Supervisor Store `icon: true` (실제 노출 확인) | 자동 적용 완료 |
| **애드온 스토어 Logo** | `addon/logo.png` (1024×512 PNG) | Supervisor Store `logo: true` (실제 노출 확인) | 자동 적용 완료 |
| **Ingress Favicon** | `addon/app/fhc/static/favicon.ico` | `GET static/favicon.ico` (200 OK) | 자동 서빙 완료 |
| **Ingress PWA Icons** | `addon/app/fhc/static/icon-32/192/512.png` | `GET static/icon-*.png` (200 OK) | 자동 서빙 완료 |
| **헤더 브랜드 로고** | `addon/app/fhc/static/icon-32.png` | 인게임 헤더 24×24px 렌더링 확인 | 자동 서빙 완료 |
| **사이드바 아이콘** | `addon/config.yaml` (`icon: mdi:home-automation`) | HA Core 좌측 메뉴 MDI 아이콘 유지 | HA 공식 제약(MDI 전용) 유지 |

---

## 4. 검증 경계 및 남은 제약

1. **검증 한계**:
   - 본 검증은 프로젝트 전용 격리 HAOS VM(Core 2026.10.1) 및 mock/virtual 엔티티 환경에서 수행되었으며, 사용자 실제 운영 Home Assistant나 실제 물리 스마트 조명/스위치 하드웨어는 조작하지 않았습니다.
   - 유료 실제 모델 API 호출은 이전 승인된 평가 결과를 유지하며, 이번 UI/브랜딩 교정 라운드에서는 불필요한 과금을 방지하기 위해 가상 조명 실행 경로만 사용했습니다.
2. **GitHub Social Preview**:
   - `docs/branding/social-preview.png` 자산 파일이 준비되어 있으며, GitHub 웹 UI의 Repository Settings → General → Social preview 항목에서 저장소 관리자가 수동 업로드할 수 있도록 안내합니다.
3. **태그 및 릴리스 생성**:
   - `docs/releases.md` 절차에 따라 최종 검증된 커밋에 `v0.2.0-dev.10` 태그 및 GitHub Prerelease 생성이 가능합니다.
