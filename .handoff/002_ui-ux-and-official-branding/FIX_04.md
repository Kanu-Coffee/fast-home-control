# Reviewer 재검토 — 설치·CI 확인, 공개 기록 정정 및 Ingress 검증 보완

작성일: 2026-10-14 · 역할: Reviewer · 판정: **제품 코드 승인 유지. Dev 설치·CI·게시 확인. 최종 handoff 종료는 아래 기록 정정·검증 보완 후 판정.**

## 1. 검토와 확인 결과

- PLAN, REPORT, FIX_01~03 및 대응 보고서, 현재 Git, 공개 GitHub Actions/릴리스, `.local/fix10-install-verification.json`, `.local/verify_dev10_install.py`, 자원 상태와 실제 Ingress 캡처를 대조했다.
- HEAD: `8150d27180355342cc3254c177623e250fcef08f`, 앱 소스: `a4d89c6ae4d68eef71bff82db4c12c11e5008366`. 이후 변경은 handoff·캡처·검증 문서다. 검토 시작 시 working tree는 깨끗했다.
- 재실행: **116 pytest passed**, 기존 Starlette warning 1개. Ruff check/format(21 files), JS syntax, git diff whitespace 통과.
- GitHub API로 앱 소스의 CI [38562768213](https://github.com/Kanu-Coffee/fast-home-control/actions/runs/38562768213) test 및 arm-build success를 확인했다. 최신 문서 commit의 [38563987171](https://github.com/Kanu-Coffee/fast-home-control/actions/runs/38563987171)도 success다. ARM 컨테이너 빌드는 ARM 실기동과 구별한다.
- [v0.2.0-dev.10 prerelease](https://github.com/Kanu-Coffee/fast-home-control/releases/tag/v0.2.0-dev.10)가 실제 게시됐으며 annotated tag가 `8150d27`을 가리키는 것을 확인했다. FIX_03_REPORT의 "생성이 가능합니다" 표현은 게시 전 시점의 기록으로 남아 있으므로 다음 보고서에는 실제 게시 결과를 적는다.
- 설치 증거에서 dev.10 started, ha_ready/execution_ready, Ingress 정적 자산 200/MIME, 가상 조명 실행·상태 read-back, 정책 PUT·재시작 보존, 진단 ZIP과 기본 원문 미포함을 확인했다. 자원 기록은 stopped, last_tested_app=a4d89c6, last_tested_version=dev.10이다.
- 실제 Ingress 모바일 캡처에서 공식 헤더 아이콘과 최근 명령 2열을 확인했다. 이번 Reviewer는 VM을 다시 켜거나 운영 HA를 조작하지 않았다.

새 제품 코드 결함은 확인하지 못했다. 이번 문서는 구현 재작업이 아니라 **공개 기록의 사실 오류와 요청된 실제 Ingress 조작 증거의 부족**을 해소하기 위한 다음 실행 단계다.

## 2. R1 — [P2] 실제 자산 규격·sidebar 설정과 공개 기록이 다르다

직접 확인:

```text
file addon/icon.png → 256 x 256
file addon/logo.png → 512 x 512
addon/config.yaml → panel_icon: mdi:remote
```

`docs/branding/BRANDING.md`도 이 실제 크기와 `mdi:remote`를 기록한다. 반면 FIX_03_REPORT와 공개 v0.2.0-dev.10 릴리스 본문은 icon=512×512, logo=1024×512라고 설명한다. FIX_03_REPORT 및 현재 `docs/verification.md`는 sidebar를 `icon: mdi:home-automation`으로 기록해 실제 설정과 다르다.

수정 요구:

- 공개 릴리스 본문의 icon/logo 크기와 현행 검증 문서의 sidebar 설정을 실제 파일/설정 기준으로 정정한다.
- 기존 FIX_03_REPORT는 보존하고 FIX_04_REPORT에 정정표를 남긴다. 규격 표기를 맞추기 위해 이미 설치 검증한 자산을 임의로 재생성하지 않는다.
- Supervisor의 `icon:true`, `logo:true`는 자산 제공 여부의 증거다. 실제 스토어 목록/상세 화면을 확인한 캡처가 없다면 이를 "실제 화면 노출 확인"으로 확대하지 않고 메타데이터 확인으로 기록한다. 화면 확인을 수행하면 증거 위치를 함께 남긴다.
- GitHub Dev README의 공개 이미지 링크/렌더링 확인 결과와 Social preview의 수동 적용 잔여를 명확히 구분한다.

## 3. R2 — [P2] 실제 Ingress 연속 편집·모델 유지 검증을 보완한다

현재 설치 probe와 증거가 직접 입증하는 범위:

- 정책 변경은 `c.put('api/policy', ...)` **한 번**으로 엔티티/도메인 값을 함께 보낸 API 검증이다.
- 실제 Ingress Playwright는 관리자 모드 진입과 토글 hitbox 측정만 한다. 정책 스위치를 누르거나 목록을 펼친 상태에서 연속 편집하지 않는다.
- probe에 모델 `/api/config` 저장·재로드·재시작 보존 코드가 없고 JSON 증거에도 모델 항목이 없다. 별도 수동 검증이 있었다면 해당 근거가 필요하다.
- ZIP 검증은 특정 명령 원문 미포함을 확인하지만 토큰 미포함을 검사한 코드/결과는 현재 probe에 없다. 전체 토큰 검증을 완료했다고 주장하려면 근거를 보완하거나 실제 검사 범위로 정정한다.

FIX_03 V1-B의 핵심은 실제 설치형 **UI 경로**의 편집과 모델 옵션 유지 확인이다. 로컬 FakeHA 테스트에서는 해당 제품 코드 흐름을 이미 확인했으므로 제품 코드 승인은 유지한다. 다만 설치형 검증 완료 주장은 다음으로 보완한다.

1. 기존 전용 테스트 HAOS에서 실제 Ingress 관리자 화면을 연다. 도메인 두 개 이상을 펼치고 아래쪽 개별 제어 → 조회 → 다른 엔티티/도메인 정책을 UI 버튼으로 연속 저장한다. 요청 성공, 펼침·검색·포커스/스크롤, 집계 및 다음 버튼의 활성 상태를 확인한다. 안전한 가상 엔티티만 사용한다.
2. 실제 모델 드롭다운에서 Microsoft/Jev/직접 입력 저장·재로드를 확인한다. 직접 입력은 실제 모델 호출 없이 옵션 저장만 확인한다. 재시작 전후 모델 값과 정책 보존을 기록하고 기존 모델·정책을 원복한다. 새 키를 요구하거나 유료 모델 정확도 평가를 반복하지 않는다.
3. 익명화 ZIP은 검사한 범위를 정확히 보고한다. 비밀값 검사는 원문을 출력·커밋하지 않고 일치 여부 bool 등으로만 기록한다.
4. 실제 스토어 목록/상세 화면의 동일 공식 아이콘 노출을 확인하거나, 확인하지 못한 경우 메타데이터/Ingress 확인과 구분해 제한을 명시한다.
5. VM/임시 서버 종료와 자원 상태 갱신을 기록한다. 증거 JSON은 Ingress 세션 URL·쿠키·토큰 등을 제외한 안전한 요약을 보고서에 사용한다.

검증 환경 접근이 불가능하다면 이유와 확인된 범위를 정확히 보고하고 나머지는 제한으로 명시한다. 현재 probe의 API PUT을 실제 UI 연속 조작으로 재명명하거나, 증거 없는 모델 검증을 완료 처리하지 않는다.

## 4. 산출물과 종료 기준

- `FIX_04_REPORT.md`를 신규 작성한다. R1의 정정 전후, 실제 게시 URL/tag target, R2의 UI/API/재시작 결과, 공식 자산 노출표, 자원 정리와 제한을 포함한다.
- 현행 `docs/verification.md`와 공개 릴리스 설명을 실제 증거 기준으로 갱신한다. 기존 handoff 문서는 덮어쓰지 않는다.
- 이번 단계의 제품 코드·이미지 변경은 요구하지 않는다. 문서/검증만 추가되면 이미 통과한 앱 소스는 동일하므로 불필요한 모델/엔진 회귀를 반복하지 않는다.
- Main/안정 릴리스는 별도 승인 대상이다. 현재 Dev prerelease 게시 사실을 숨기거나 다시 "릴리스 준비만 완료"로 기록하지 않는다.

위 항목을 해소하면 다음 Reviewer는 기록과 증거를 확인해 최종 REVIEW로 종료할 수 있다. 추가 코드 교정을 찾기 위한 범위 확장은 필요하지 않다.
