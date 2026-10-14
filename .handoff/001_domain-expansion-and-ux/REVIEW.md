# 최종 Reviewer 기록 — 0.2.0-dev.9 운영 시험 인계

작성일: 2026-10-14 · 역할: Reviewer · 판정: **Dev 운영 시험용 승인. 검토 범위에서 새로운 수정 요구 없음.**

## 대상과 검증

- 검토 HEAD: `d55d50b6caccd22c285b8a8fdac23094aa79649f`.
- 앱 소스: `53ba9b5fe0d1b36f9f2da9729616c7690cb3b751`. 이후 릴리스 커밋까지 변경은 handoff/검증 문서이며 앱 코드는 동일하다.
- PLAN, 기존 FIX/보고서, FIX_09 및 FIX_09_REPORT, 현재 Git/릴리스, docs/verification.md, 로컬 설치 증거의 비밀 없는 결과를 대조했다. 작업 트리는 검토 시작 시 깨끗했다.
- 재실행: **115 pytest passed**, 기존 Starlette deprecation warning 1개. Ruff check/format(20 files), JavaScript syntax, git diff --check 통과.
- CI **38514419962**, head d55d50b: test 및 arm-build success 확인. 이전 앱 커밋 53ba9b5의 CI 38512834220도 success다. ARM 컨테이너 빌드는 ARM 실기동과 구별한다.
- GitHub prerelease **v0.2.0-dev.9**가 게시됐고 tag는 d55d50b를 가리킨다: https://github.com/Kanu-Coffee/fast-home-control/releases/tag/v0.2.0-dev.9

## FIX_09 마무리 판정

V1의 공식 저장소 기반 **dev.8→dev.9 업데이트·기동**을 `.local/fix09-install-verification.json`에서 확인했다. 설치 앱 version=0.2.0-dev.9, ha_ready/execution_ready=True다.

Ingress 조명 실행은 succeeded, 거실 light 2개 turn_off sent이며 실제 HA 상태 read-back과 타 영역 유지 증거가 있다. 관리자 read/entity 정책 PUT은 200, 앱 재시작 후 버전·정책 유지, 진단 ZIP의 manifest/summary/requests 구조 및 기본 원문 비포함을 확인했다. `.local/test-resources.json`도 stopped, last_tested_version=dev.9, last_tested_app=53ba9b5로 갱신됐다.

V2의 Dev tag/prerelease 게시와 설치 안내, 검증 레이어 정정도 확인했다. 이미 승인된 코드의 설치·배포 마무리가 이뤄졌다. **새 교정을 요구할 근거가 없어 FIX_10을 만들지 않고 이 REVIEW.md로 해당 workflow를 닫는다.**

## 승인 범위와 알려진 한계

이번 승인은 실제 사용자의 **Dev 운영 시험으로 넘어가도 된다는 Reviewer 판정**이다. Main 반영·안정 릴리스에 대한 사용자의 별도 승인을 대체하지 않는다. Reviewer가 운영 HA를 변경하거나 자동 업데이트한 것은 아니다.

설치 앱의 `거실 날씨 어때`는 low_confidence, 조건 명령은 condition_evaluation_failed로 0전송 거부됐다. 이를 해당 기능의 설치 앱 성공으로 집계하지 않는다. 조건 미충족(False)과 조건 평가 실패도 구별한다. 설치 앱의 대표 B/C 정상 성공 증거가 모두 확보된 것은 아니라는 잔여 한계를 유지한다.

달력/TTS/예보의 정상 경로는 이전 같은 앱 계열의 실제 모델→호스트 Engine→테스트 HA 시험과, 모의 판단+실제 서비스 계약 시험으로 확인됐으며 설치 앱 직접 검증과 구별한다. 안전 거부만을 기능 성공으로 간주하지 않지만, 이 제한을 명시한 기능 MVP의 Dev 운영 시험을 무기한 보류할 사유로 삼지 않는다.

현재 기록된 Microsoft 6/8(정상 5/6), Jev 2/8(정상 1/6)은 작은 단발 corpus의 결과다. 재시도 성공을 고정 평가 결과로 덮어쓰거나 일반 한국어 정확도·물리 장치 완료 보장으로 확대하지 않는다. Microsoft 기본 유지/Jev 비교 검증 지속, notify/time/date 등 미지원·미검증 범위는 릴리스 설명대로 유지한다. 처리속도는 측정하되 엄격한 초 단위 기준을 추가하지 않는다.

## 다음 단계

사용자는 `https://github.com/Kanu-Coffee/fast-home-control#dev` 저장소의 **0.2.0-dev.9**로 운영 시험할 수 있다. 문제 분석에는 관리자 모드의 진단 로그 다운로드를 사용한다. 의미 해석 분석에 원문이 필요할 때만 원문 포함 옵션을 선택하고, 기본 공유 모드의 익명화는 유지한다.

후속 운영 이슈/개발은 이 완료 기록을 보존하고 실제 증거를 기준으로 진행한다. 새로운 handoff 작업이 필요하면 기존 task 번호/문서를 덮어쓰지 않는다. Main/안정 릴리스는 여전히 사용자 명시 승인 이후다.

이번 Reviewer는 테스트 VM을 새로 기동하거나 API를 추가 호출하지 않았고, 제품 코드·설정·릴리스를 수정하지 않았다. 확인은 자동 검사 재실행과 저장된 실기동/CI/공개 릴리스 증거의 대조로 수행했다.
