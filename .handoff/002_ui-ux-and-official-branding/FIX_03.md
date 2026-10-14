# Reviewer 판정 — UI 교정 코드 승인 및 Dev 설치·릴리스 검증 인계

작성일: 2026-10-14 · 역할: Reviewer · 판정: **검토 범위의 코드 교정 승인. 실제 설치·CI 검증 완료 전 릴리스 완료 판정은 보류.**

## 1. 검토 대상과 상태

- PLAN, REPORT, FIX_01 및 보고서, FIX_02 및 보고서, 현재 Git diff/status, 브라우저 테스트와 검증 문서를 대조했다.
- 기준 HEAD: `02dc9d0877378e95bf9710aa37a7b17579fef67e`, 브랜치 `dev`.
- 버전 문자열: `0.2.0-dev.10` / `0.2.0.dev10`.
- 구현은 아직 working tree에 있다. tracked 변경 14개와 신규 handoff·브라우저 테스트·브랜딩 자산이 있으며, 이번 Reviewer가 구현 commit/push를 수행하지 않았다.
- **새로운 제품 코드 결함을 요구할 근거는 확인하지 못했다.** 이번 문서는 FIX_02 V1에서 아직 이행되지 않은 Dev 설치·CI·릴리스 마무리의 실행 인계다. 이미 완료한 FIX_02의 코드 교정을 반복하지 않는다.

## 2. Reviewer 독립 확인

자동 검사 재실행:

| 명령 | 결과 |
|---|---|
| `uv run pytest -q` | 116 passed, 기존 Starlette deprecation warning 1개 |
| `uv run ruff check addon/app tests scripts` | 통과 |
| `uv run ruff format --check addon/app tests scripts` | 21 files 통과 |
| `node --check addon/app/fhc/static/app.js` | 통과 |
| `git diff --check` | 통과 |
| `actionlint .github/workflows/check.yml` | 통과 |
| `hadolint addon/Dockerfile` | 통과 |

Browser 플러그인이 없어 설치된 Python Playwright Chromium과 localhost/FakeHA를 사용했다. 앞선 Reviewer가 만든 저장소 밖 probe 3개를 재실행했다:

```sh
PYTHONPATH=addon/app uv run pytest -q -s \
  /tmp/fhc_review_002.py \
  /tmp/fhc_review_002_round2.py \
  /tmp/fhc_review_002_race.py
```

관찰 결과:

- 정책 저장 완료 후 `isPolicySaving=false`, 전체 토글 잠금 없음. 이전 영구 잠금 재발 없음.
- 직접 입력 모델 초안 `my-org/my-model`이 후보 왕복 뒤 유지됨.
- 검색 중 목록 닫기 후 `aria-expanded=false`.
- 같은 상태의 phase 변경이 진단에 반영되고 진단 내부 스크롤 120 유지.
- 토글 bounding box 44×44px.
- providers 단독 변경이 진단에 반영됨.
- 앞쪽 기록 높이 변경 전후 최상단 가시 항목은 `probe-7`, 상대 위치는 **-43px → -43px**. 목록 scrollTop은 높이 변화에 맞춰 700 → 1125로 조정됨.
- 최신 조회 뒤 오래된 응답을 반환해도 표시 스냅샷은 **new-response → new-response**로 유지됨.

probe의 3 passed는 관찰 스크립트 완료이며 위 관찰값이 교정 판단의 근거다. 제품 테스트에는 선행 행 높이 변화·새 로그 삽입, 공급자 변경, PUT 실패, 조회 응답 역전 및 실제 지연 명령 중 새 문장 보존 경로가 추가된 것을 확인했다. FIX_02_REPORT의 설명용 코드 예시보다 현재 소스를 판정 기준으로 삼았다.

## 3. 승인 범위

- FIX_01 및 FIX_02의 보고된 코드 결함은 이번 재현 범위에서 해결됐다. 추가 UI 재설계·아이콘 재생성·엔진 변경을 요구하지 않는다.
- 코드 검토 승인에 따라 **Dev 소스 commit/push와 기존 전용 HAOS 설치 검증을 진행할 수 있다.** 로컬 검토를 받기 위해 같은 수정으로 다시 승인을 요청할 필요는 없다.
- 본 승인에는 운영 HA 변경, Main 반영, stable 생성이 포함되지 않는다.
- 원격 Actions 성공, 컨테이너 빌드, dev.10 실제 설치·Ingress, HA 앱 목록/상세 및 GitHub 공개 노출은 이번 Reviewer가 확인하지 않았다. FIX_02_REPORT 역시 이 작업을 남은 단계로 기록한다. 로컬 통과를 해당 항목의 성공으로 확대하지 않는다.

## 4. Executor 필수 실행 — V1 마무리

### V1-A. Dev 소스 확정과 CI

1. 작업 시작 시 Git/원격/최신 Dev 버전과 적용되는 지침을 다시 확인한다. 다른 작업자가 추가한 변경이 있다면 구분하고 필요한 경우 재검증한다.
2. 이 작업의 코드·자산·테스트·문서·handoff를 빠짐없이 Dev commit에 포함한다. `.local/`, 자격 증명, 테스트 DB 등은 제외한다. untracked 이미지/테스트 누락을 확인한다.
3. 기존 Dev 권한 범위에서 commit/push하고 변경된 GitHub Actions를 실행한다. test job의 Chromium 준비 및 pytest, amd64 빌드와 arm-build 성공을 run URL/commit과 함께 기록한다. 실패는 수정·재검증 후 진행한다.
4. 버전 충돌이 있으면 실제 다음 Dev 번호를 사용하고 관련 파일/기록을 맞춘다. 현재 시점 후보는 dev.10이다.

### V1-B. 실제 프로젝트 전용 HAOS 설치·Ingress 확인

1. 기존 프로젝트 전용 VM/자원 기록과 `docs/testing.md`를 확인한다. 운영 HA, 기존 운영 VM/호스트 방화벽은 변경하지 않는다.
2. 공식 `#dev` 저장소 업데이트 → 설치/업데이트 → 기동을 수행하고 설치 버전·앱 상태·HA readiness를 확인한다. 파일만 직접 복사한 환경을 공식 업데이트 성공으로 표기하지 않는다.
3. 실제 Ingress 관리자 화면에서 여러 도메인을 펼친 상태로 개별 제어/조회 및 도메인 정책을 연속 저장한다. 펼침·검색·스크롤·집계와 저장 후 재편집 가능 상태를 확인한다.
4. Microsoft/Jev/직접 입력 모델 저장·재로드 및 앱 재시작 후 옵션 보존을 확인한다. 실제 유료 모델로 모두 명령을 실행할 필요는 없다. 기존 키와 Azure 설정은 유지하고 테스트 변경은 원복한다.
5. 실제 Ingress prefix 아래 헤더/파비콘/Apple 아이콘의 응답과 MIME을 확인하고, 모바일 최근 명령 2열·관리자 레이아웃·로그 내부 스크롤을 확인한다. 가상 기기 기반 명령만 필요 최소한으로 사용한다.
6. 진단 다운로드 ZIP과 기본 원문 비포함을 확인한다. 공개 캡처/보고서에 키·토큰·운영 기기명/명령을 포함하지 않는다.
7. 사용한 VM/임시 서버를 종료·정리하고 기존 테스트 자원 상태를 갱신한다.

### V1-C. 공식 자산 노출 및 Dev 릴리스

1. HA 공식 icon/logo 규격·위치를 구현 대상 버전에 맞춰 확인하고, 실제 테스트 스토어 목록/상세 노출을 확인한다. 파일 배치와 화면 적용을 구분한다.
2. push 후 GitHub Dev README의 이미지 링크/노출을 확인한다. Social preview는 최종 자산 파일과 수동 업로드 경로를 제공한 기존 방식으로 인계해도 된다. 외부 설정 적용 완료로 허위 표기하지 않는다. sidebar MDI 제약도 유지한다.
3. **CI 성공과 설치·Ingress 확인을 모두 얻은 후** `docs/releases.md`에 따라 검증된 소스를 포함하는 commit에 Dev tag/prerelease를 만든다. 위 검증을 통과하면 이 코드 승인 범위 안에서 마무리할 수 있으며, 사용자에게 중복 승인 요청을 추가하지 않는다. 코드가 추가로 바뀌면 관련 회귀와 설치 검증을 다시 수행한다. Main/안정 릴리스는 여전히 별도 승인 대상이다.
4. `docs/verification.md`와 changelog/릴리스 안내에 실제/모의 검증 구분, 브랜딩 적용표, 알려진 제한을 정확히 기록한다.

## 5. 산출물 및 다음 리뷰 기준

같은 작업 폴더에 `FIX_03_REPORT.md`를 신규 작성한다. 최소 포함 항목:

- 최종 소스 commit, 브랜치/버전, Git dirty 상태, CI run URL와 job 결과.
- 실제 설치 전후 버전 및 기동/Ingress 검증의 비밀 없는 결과.
- 정책 연속 편집·모델 재시작 보존·아이콘·모바일·로그 다운로드 검증 결과와 캡처/증거 위치.
- HA/GitHub 자산별 파일 준비·실제 노출·수동 잔여 적용표.
- Dev tag/prerelease 결과, 자원 정리, 남은 제약 및 계획 대비 변경.

외부 인증·환경 등으로 실행이 불가능하면 구체적인 원인과 완료된 범위를 보고한다. 단순히 "Reviewer 승인 후 진행"으로 V1을 다시 미루지 않는다. **코드 검토는 승인됐으며, 다음 재검토의 중심은 실제 CI·설치·배포 증거다.** 기존 handoff 문서는 덮어쓰지 않는다.
