# FIX_09 — 코드 리뷰 통과, dev.9 설치 검증·Dev 배포 마무리

작성일: 2026-10-14 · 역할: Reviewer

판정: **FIX_08 코드 보정 승인. 새 제품 코드 결함은 발견하지 않았다. 남은 작업은 이미 요구된 dev.9 설치 검증 및 Dev 배포 인계이며, Main/안정 릴리스 승인은 아니다.**

## 1. 확인한 결과

기준 앱/HEAD는 dev `53ba9b5fe0d1b36f9f2da9729616c7690cb3b751`. 작업 트리는 깨끗하다. PLAN, 기존 FIX/보고서 및 FIX_08_REPORT, 현재 diff/테스트, 일반 검증 문서와 로컬 증거 metadata를 대조했다. Reviewer는 제품 코드·설정·VM·Main·릴리스를 변경하지 않았다.

- `uv run pytest -q`: **115 passed**, 기존 Starlette warning 1개.
- Ruff check/format(20 files), JS syntax, git diff --check 통과.
- CI **38512834220**, head 53ba9b5: test/arm-build success를 gh로 확인했다.
- condition_unit fallback이 **low_confidence에만 한정**되고 invalid_model_response를 다시 던지는 보정을 승인한다. source/operator/value의 invalid 사유도 유지된다.
- 새 회귀 테스트의 잘못된 구조/레이블/확률 합계 및 정상 저확신도 파생 경로를 확인했다. 추가로 올바른 전체 레이블 집합에 NaN/boolean/string 확률을 넣은 직접 검사도 모두 invalid_model_response였다.
- 모델별 정상 성공/기대 사유 일치/안전 거부의 분모는 docs/verification.md에서 이전보다 정확하게 정정됐다. 기존 보고서는 보존한다.

새 API 호출/실제 HAOS 기동은 이번 리뷰에서 수행하지 않았다. 이전 dev.8의 주요 설치·실모델/서비스 검증 승인과 알려진 범위/변동성은 유지한다. 제품 설계나 B/C 전체를 다시 열지 않는다.

## 2. V1 [P2] dev.9 실제 설치·업데이트 검증이 남아 있다

FIX_08은 코드 변경 뒤 더 높은 버전의 실제 설치 검증을 요구했다. FIX_08_REPORT에는 단위/정적 검사와 버전 변경만 있고 새 설치 증거는 없다.

현재 `.local/test-resources.json` metadata는 stopped, last_tested_version=**0.2.0-dev.8**, last_tested_app=cb6a248이다. fix08/dev9 명칭의 새 runtime 증거 파일도 발견하지 못했다. 이를 dev.9 설치 완료로 간주할 수 없다.

다음 Executor는 기존 승인 범위에서 마무리한다:

1. 프로젝트 소유 VM의 이름·디스크·격리를 확인하고 기동한다. 운영 VM/사용자 운영 HA는 변경하지 않는다.
2. 공식 `#dev` 저장소 갱신/업데이트로 **dev.8→dev.9**를 설치한다. 이미 설치된 버전이 달라졌으면 실제 상태를 기준으로 더 높은 버전을 사용하며, 기존 tag를 덮어쓰지 않는다. 검증을 위해 불필요한 앱 코드 변경은 하지 않는다.
3. 설치 앱 status의 버전·연결, Ingress의 조명/대표 B/C 명령, 관리자 정책·재시작 보존, 실제 ZIP 다운로드·파싱을 확인한다. 달력/TTS/예보 중 기존 fixture에서 실행 가능한 대표 사례를 설치된 앱 경로로 검증하여 호스트 Engine 경로와 구별한다. 모델의 단발 안전 거부는 그대로 기록하고 성공 관측으로 덮어쓰지 않는다.
4. 이번 핵심 수정의 malformed unit은 자동 회귀로 충분히 검증됐다. 실제 API에 malformed 결과를 발생시키기 위해 운영 설정이나 공급자를 변조할 필요는 없다. 설치된 앱의 정상 조건 경로 및 fail-closed 저널 동작을 가능한 범위에서 확인한다.
5. 요청 ID/사용한 앱 소스/설치 버전/성공·거부·HA 상태 및 응답을 비밀 없이 기록한다. 자원 metadata를 실제 검증 버전으로 갱신하고 테스트 VM/임시 프로세스를 정리한다.

## 3. V2 — 이미 승인된 Dev 배포를 완료한다

조회 시 최신 GitHub prerelease는 **v0.2.0-dev.6**이고 dev.9 prerelease는 없다. Dev branch push는 완료됐지만 FIX_08의 “검증 가능한 Dev 배포 형태까지 진행”은 아직 마무리되지 않았다.

- 설치 검증한 앱 소스를 기준으로 Dev tag/prerelease와 사용자가 설치/업데이트할 수 있는 안내를 준비한다. 검사·실기동 완료 전에 배포 완료라고 보고하지 않는다.
- Dev commit/push, 프로젝트 VM, Dev prerelease는 사용자가 이미 명시적으로 승인했다. 별도 승인 질문으로 멈추지 않는다. **Main 및 안정 릴리스는 별도 명시 승인 전까지 변경하지 않는다.** 운영 HA에 자동 업데이트하지 않는다.
- 알려진 notify/time/date 등 미지원·미검증 범위와 Microsoft 기본/Jev 비교 상태를 릴리스 설명에 표시한다. Jev 모든 사례 성공이나 엄격한 초 단위 속도 기준을 새로 추가하지 않는다.
- 사용자 운영 시험은 위 마무리된 Dev를 대상으로 지원할 수 있다. 새 장기 개발 라운드나 완전한 한국어 정확도 달성까지 기다리지 않는다.

## 4. 보고 정정 및 다음 산출물

다음 문서는 **FIX_09_REPORT.md**다. 기존 handoff 보고서를 수정하지 않는다. 코드 보정은 승인됐음을 유지하고, 실제 설치/배포의 명령·결과·commit/tag/CI·자원 정리를 기록한다. 검증이 불가능한 외부 조건이 생기면 정확한 원인과 완료/미완을 구분한다.

FIX_08_REPORT의 서비스 레이어 설명에는 소규모 정정이 필요하다. 실제 `.local/fix06-live-scripted.json`의 safety_negative 1개는 **todo_duplicate_refused_before_write**다. password 시험은 별도 `.local/fix06-live-r1-password.json`의 증거이며 이 9개 assertion에 포함되지 않는다. 일반 문서의 서비스 설명에서도 todo 모호 거부를 service_contract 목록에 혼합하지 않는다. 합계는 service_contract 8개 + safety_negative 1개로 맞다.

이 문서는 새 제품 개발 요구가 아니라 **이미 승인된 코드의 설치 검증·Dev 배포 완료 인계**다.
