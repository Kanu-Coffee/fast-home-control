# Reviewer 재검토 — 로그 앵커·응답 순서 및 설치 검증 잔여

작성일: 2026-10-14 · 역할: Reviewer · 판정: **추가 교정 필요, dev.10 릴리스 승인 보류**

## 1. 기준 및 이번 검증

- PLAN, REPORT, FIX_01, FIX_01_REPORT, 현재 tracked diff와 신규 브라우저 테스트를 대조했다. 이전 handoff 문서는 보존한다.
- HEAD는 `02dc9d0877378e95bf9710aa37a7b17579fef67e`, 브랜치 `dev`. 구현 및 교정은 아직 미커밋 working tree에 있다.
- 재실행: `uv run pytest -q` **116 passed**, 기존 Starlette warning 1개. Ruff check/format(21 files), `node --check`, `git diff --check`, `actionlint .github/workflows/check.yml`, `hadolint addon/Dockerfile` 모두 통과했다.
- Browser 플러그인이 없어 기존 Python Playwright Chromium과 localhost/FakeHA fixture를 사용했다. 운영 HA·유료 모델·외부 설정은 변경하지 않았다. 추가 probe는 저장소 밖 `/tmp/`에서 실행했으며 제품 코드는 수정하지 않았다.

이전 probe 재실행 결과:

```text
POLICY_AFTER_SAVE {"saving": false, "disabled": false}
CUSTOM_DRAFT_AFTER_SWITCH my-org/my-model
SEARCH_CLOSE_RESULT false
SAME_STATUS_PHASE_REFRESHED True
DIAGNOSTIC_SCROLL_AFTER_CHANGE 120
TOGGLE_HITBOX width=44, height=44
```

FIX_01 R1의 영구 잠금, R4의 초안 소실, R5의 검색 중 닫기 및 R6의 hitbox 문제는 이 재현 범위에서 해결됐다. R2의 CI Chromium 설치 단계와 fixture 준비/종료 개선도 확인했다. 실제 원격 CI 성공은 아직 확인되지 않았다. R3의 동일 상태 phase 변경과 JSON 내부 스크롤은 개선됐지만 목록 앵커에는 아래 문제가 남는다.

## 2. 필수 교정

### R1 — [P2] 로그 앵커가 서로 다른 좌표계를 비교해 읽던 행을 잃는다

위치: `addon/app/fhc/static/app.js:649–659`, `730–750`.

`container.scrollTop`은 목록 내부 좌표인데 `child.offsetTop`은 현재 BODY 기준이다. `.history-list`가 위치 기준 조상이 아니므로 실제 목록의 최상단 가시 행 대신 첫 행을 앵커로 잡는다. 읽는 행 앞쪽의 다른 행 높이가 달라지면 같은 scrollTop을 복원해도 다른 기록이 보인다. 이는 FIX_01 R3에서 요구한 읽던 항목 보존의 잔여 결함이다.

추가 probe(`/tmp/fhc_review_002_round2.py`)에서 30개 기록을 반환하고 목록 scrollTop=700으로 읽다가 두 번째 기록의 actions를 25개로 증가시킨 결과:

```text
before: id=probe-7, offset=-43, scroll=700
        firstOffset=3497, offsetParent=BODY
after:  id=probe-2, offset=-88, scroll=700
```

스크린샷 확인: `/tmp/fhc-review-round2-log.png`. DOM/request ID 관찰이 읽던 항목 변경의 직접 증거다. 해당 probe의 `1 passed`는 관찰 완료이며 수용 기준 통과를 뜻하지 않는다.

수정 요구:

- 목록과 행의 `getBoundingClientRect()`를 같은 좌표계에서 비교하거나, 확실한 공통 위치 기준을 사용한다. 실제 최상단 가시 request ID와 상대 위치를 기록/복구한다.
- focus 복원에는 필요하면 `preventScroll: true`를 사용해 복구한 스크롤을 다시 움직이지 않게 한다. JSON 내부 스크롤/펼침 상태의 기존 교정은 유지한다.
- 첫 행 이외를 읽는 상태에서 앞쪽 행 높이 변경, 위에 새 기록 삽입, 기존 행 삭제를 각각 검증한다. 첫 기록을 펼친 테스트만으로 목록 앵커 보존을 판정하지 않는다.

### R2 — [P2] 도메인 조회의 오래된 응답이 최신 정책 표시를 덮어쓸 수 있다

위치: `addon/app/fhc/static/app.js:552–555`, `575–580`.

`loadDomains(true)`는 응답 순서 방어 없이 항상 cachedDomains에 값을 대입한다. 모드 진입·재탐색·정책 저장이 겹치면 나중에 도착한 오래된 응답이 최신 허용값/집계를 덮어쓴다. 정책 저장 잠금도 후속 GET을 기다리기 전에 false로 바뀌므로, 대기 중 검색/목록 토글이 재렌더링하면 이전 캐시 기반 버튼이 다시 활성화된다. PLAN B와 FIX_01의 지연/응답 역전 검증이 아직 구현·테스트에 반영되지 않았다.

추가 probe(`/tmp/fhc_review_002_race.py`)에서 두 도메인 GET을 시작하고 두 번째 응답을 먼저 반환한 뒤 첫 번째를 반환했다:

```text
LATEST_BEFORE_OLD_RESPONSE new-response
LATEST_AFTER_OLD_RESPONSE old-response
```

표시명으로 응답 스냅샷을 식별했으며 실제 정책 필드도 같은 대입 경로를 사용한다.

수정 요구:

- 요청 세대/순서 또는 취소·직렬화로 오래된 조회 응답의 반영을 막는다. 정책 변경 전 시작된 응답이 변경 후 최신 조회를 덮어쓰지 않게 한다.
- 정책 저장 생명주기는 최신 값 반영/실패 처리까지 일관되게 관리한다. 플래그를 너무 일찍 해제해 검색 재렌더링으로 중복 편집이 가능해지는 문제를 피하면서 FIX_01의 영구 잠금 해제를 유지한다.
- 실제 PUT 실패 후 재시도, PUT 성공 후 GET 실패, 늦은 GET 응답과 검색/재탐색이 겹치는 경우의 표시값·집계·재편집 가능 여부를 동작 테스트로 확인한다.

### R3 — [P2] 로그 변경 지문이 표시하는 providers를 빠뜨린다

위치: `addon/app/fhc/static/app.js:605–618`, `700–710`.

진단 JSON에는 providers를 표시하지만 fingerprint에는 포함하지 않는다. 같은 ID/status/reason/phase 등에서 공급자 진단만 바뀌면 갱신을 건너뛴다. 추가 probe에서 `providers=['initial-provider']`를 `['changed-provider']`로 바꾼 뒤 갱신했으나 `PROVIDERS_UPDATED False`였다.

수정 요구: 렌더링 필드 집합과 변경 감지 필드를 일치시킨다. 별도의 수작업 필드 목록을 유지하기보다 공통 DTO 또는 응답 전체 비교를 사용해도 된다. providers만 바뀌는 응답이 화면에 반영되는 검증을 추가한다. 동일 응답일 때 불필요한 재렌더링을 생략하는 동작은 유지한다.

## 3. 검증 주장과 테스트 보완

FIX_01_REPORT와 docs/verification.md는 이전보다 검증 경계를 잘 구분했지만 아래 주장은 여전히 보완해야 한다.

- `tests/test_browser_ui.py`의 실제 form submit → 503 → 원문 복원 경로는 제품 코드를 거쳐 검증하도록 개선됐다. 그러나 그 다음 "대기 중 새 문장 덮어쓰기 방지" 항목은 여전히 `page.evaluate()` 안에서 복원 조건문을 직접 작성해 실행한다. 실제 명령 요청을 지연시킨 뒤 새 문장을 입력하고 요청 실패 응답을 반환해 제품 코드가 새 문장을 보존하는지 검사한다. 이 코드 복제 테스트를 해당 동작의 검증 근거로 쓰지 않는다.
- 현재 브라우저 테스트에는 정책 실패/후속 GET 실패, 응답 역전, 로그 앞쪽 새 항목/높이 변화가 없다. R1–R3 재현을 포함하는 의미 있는 회귀를 보완한다.
- FIX_01_REPORT의 로컬 FakeHA dev-session은 독립 개발 인증 경로다. 실제 HA Ingress 관리자 세션과 구분한 현재 미검증 표시는 유지한다.
- 과거 REPORT 및 FIX_01_REPORT를 덮어쓰지 않는다. 현행 docs/verification.md를 실제 새 검증 범위로 갱신하고, 기존 주장 중 정정되는 항목을 FIX_02_REPORT에 남긴다.

## 4. V1 — Dev 배포 전 설치·CI 증거 마무리

FIX_01의 릴리스 검증 인계는 아직 미완료이며 FIX_01_REPORT에서도 잔여 항목으로 인정했다. 로컬 UI 교정을 마친 뒤 다음을 수행하고 증거를 제공한다.

1. 최종 Dev 소스 commit을 확정하고 변경된 CI에서 Chromium 준비/브라우저 테스트 및 amd64·arm64 빌드가 실제 성공하는지 확인한다. actionlint/hadolint 성공은 원격 빌드 성공과 구별한다.
2. 기존 프로젝트 전용 HAOS에서 공식 저장소 업데이트로 dev.10 설치·기동을 확인한다. 실제 Ingress에서 연속 정책 제어/조회 저장, 모델 저장·재시작 유지, 아이콘 상대 URL/MIME, 모바일 레이아웃 및 진단 다운로드를 확인한다. 운영 HA·물리 기기는 사용하지 않는다.
3. HA icon/logo 규격·위치는 공식 문서/지원 버전과 테스트 스토어 실제 노출로 확인하고 결과를 남긴다. GitHub README 노출과 Social preview 파일 준비/수동 업로드 잔여를 구분한다.
4. 테스트 자원을 사용했다면 종료·정리하고 기존 자원 기록을 갱신한다. 설치·기동 검증 후에만 `docs/releases.md` 순서로 검증된 Dev 소스를 포함하는 tag/prerelease를 만든다. Main/안정 릴리스는 별도 사용자 승인 없이 변경하지 않는다.

실제 환경 접근이 불가능하면 정확한 원인과 완료된 범위를 보고한다. 로컬 mock/정적 검사로 위 설치/공개 노출 항목을 완료 처리하지 않는다. 기존 엔진 변경 없는 UI 회귀를 확인하기 위해 유료 실제 모델 호출을 반복할 필요는 없다.

## 5. Executor 인계

다음 실행 대상은 이 문서다. R1–R3, 테스트 보완, V1을 수행하고 `FIX_02_REPORT.md`를 신규 작성한다. 기준/최종 Git 상태, 수정 전후 관찰값, 명령/검사 결과, 실제 CI·설치 증거, 외부 수동 잔여 항목을 포함한다. 기존 수정에서 해결된 토글 잠금·모델 초안·검색·hitbox를 회귀시키지 않는다. 이번 재검토는 전체 기능 재설계나 아이콘 재생성을 요구하지 않는다.
