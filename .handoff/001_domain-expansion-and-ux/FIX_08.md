# FIX_08 — dev.8 리뷰: 핵심 보정 승인 및 소규모 잔여 수정

작성일: 2026-10-14 · 역할: Reviewer

판정: **FIX_07 핵심 보정·설치 검증 승인. 새 P1은 발견하지 않았으며 아래 P2 두 항목을 보정한 다음 Dev 운영 시험으로 인계할 수 있다. Main/안정 릴리스 승인은 아니다.**

## 1. 검토 대상과 확인한 결과

작업 트리는 깨끗하다. 앱 구현은 dev `cb6a248`, 설치 검증 문서/보고서까지 포함한 HEAD는 `10ec7b4`다. PLAN 및 이전 FIX/보고서의 요구, FIX_07_REPORT, 현재 코드, 실제 검증 파일과 CI를 대조했다. 이번 Reviewer는 제품 코드·VM·설정·Main·릴리스를 변경하지 않았다.

- pytest **114 passed**, 기존 Starlette warning 1개.
- Ruff check 및 format(20 files), node syntax, git diff --check 통과.
- GitHub run **38489605884**, head `cb6a24859379d4913841ec9543db86535e536eaa`: test/arm-build 모두 success를 gh로 확인했다. ARM 컨테이너 빌드와 실제 ARM HAOS 기동은 구분한다.
- `.local/fix07-install-verification.json`의 설치 앱 version/status, Ingress 명령, 조명 read-back, 정책 PUT/재시작, ZIP 파싱 증거를 확인했다. 운영 HA나 실제 물리 기기에 시험한 것으로 확대하지 않는다.
- `.local/fix06-live-*.json` 결과는 모의 판단+실HA 서비스와 실모델 왕복으로 분리해 확인했다. 새로운 실제 API 호출/VM 기동은 이번 리뷰에서 하지 않았다.

승인하는 개선:

- 실제 달력 응답 및 start/end 생성, todo UID preflight, condition_class 불확실성/단위 검증.
- query_state/응답 조회의 상호 배타 선택 및 TTS speaker nomination/secondary 정책 검사.
- FIX_07의 오후+HH:MM/명시 연도/잘못된 분 처리와 전원+속성 순서 보존.
- Dev 코드 commit/push와 공식 저장소 기반 dev.8 설치, Ingress 실행·정책 재시작 보존·진단 다운로드.

정상 B/C 자연어 실행 경로가 확보됐으므로 이전의 “정상 사례 0/5” blocker는 해소됐다. 아래 보정 때문에 B/C 전체를 다시 설계하거나 모든 모델의 모든 문장을 성공시킬 필요는 없다. Dev MVP와 운영 시험으로 이어가는 방향을 유지한다.

## 2. R1 [P2] 낮은 확신도와 잘못된 모델 응답을 같은 fallback으로 처리한다

위치: `addon/app/fhc/engine.py:Engine._select_condition`, condition_unit 선택의 `except DecisionError`.

단위를 literal/native에서 유도하는 방향은 합리적이다. 하지만 choice()의 모든 DecisionError를 잡아 unit='none'으로 바꾸므로 **invalid_model_response도 정상적인 단위 파생 요청으로 처리**한다. 보고서는 낮은 확신도 보정으로 설명했지만 실제 구현 범위가 더 넓다.

Reviewer 재현(합성 FakeHA + 임시 Store + ScriptedProvider, 실제 API/HA 전송 아님):

- 조건 source/operator/value와 supported/exact는 정상 승인 응답.
- condition_unit만 `{'type':'choice','choice':'°C','probabilities':{'°C':'not-a-probability'}}`로 변조.
- `거실 온도가 28℃ 이상이면 거실불 꺼줘`, source=29°C → **succeeded / condition_result=True**, FakeHA light.turn_off 1건.

잘못된 모델 결과는 실행하지 않는다는 기존 계약에 맞게 수정한다:

- fallback을 검증된 `low_confidence` 경우로만 한정하고 invalid_model_response는 전송 0건 거부한다. 또는 불필요한 unit 질문 자체를 제거하고 검증된 literal/native 단위에서만 결정하는 방식을 사용할 수 있다. source/operator/value 및 명시 단위 충돌 검증은 유지한다.
- malformed type/labels/probability/NaN/합계 불일치가 unit 응답에만 발생해도 실행 0건임을 시험한다. 유효하지만 확신도가 낮은 unit은 안전한 backend 파생으로 처리되는 기존 성공도 회귀 검증한다.
- 안전 임계값을 낮추거나 통과를 위해 모델 재질문을 반복하지 않는다.

이 재현은 backend 응답 검증의 공백이며 운영 모델에서 실제 오실행을 관측했다는 뜻이 아니다. 새로운 안전 체크리스트/승인 절차를 도입할 필요 없이 예외 분류를 좁히는 작은 보정으로 충분하다.

## 3. R2 [P2] 결과 표를 실제 사례와 일치시키고 승인 범위를 명확히 한다

위치: `docs/verification.md` dev.8 절, FIX_07_REPORT §4의 설명. **기존 handoff 보고서는 수정하지 말고 FIX_08_REPORT에서 정정한다.** 일반 문서/지원표는 수정할 수 있다.

확인한 최신 단발 평가:

| 항목 | Microsoft Decision-1 | TypeSafe Jev 1.13 |
| --- | --- | --- |
| 전체 기대 결과 일치 | 6/8 | 2/8 |
| 정상 요청 6개 중 성공 | 5/6 | 1/6 |
| 통과한 정상 사례 | 조명 off, 조건 false, 지정 TTS, 일정 조회, 예보 조회 | 공조 온도 설정 |
| 기대 거부 사유까지 일치한 음성 사례 | TTS 모호 1/2 | TTS 모호 1/2 |
| 거부 사례의 실제 전송 | 두 음성 사례 모두 0건 | 두 음성 사례 모두 0건 |

Microsoft의 todo 부재 사례는 **plan_not_verified**로 거부돼 해당 corpus의 기대 사유 todo_item_not_found와 불일치(e2e_pass=False)다. 공조도 plan_not_verified다. Jev 2/8 중 하나는 공조 **실전송 성공**이므로 “모두 0건/보수 거부”가 아니다. probe 재실행의 성공은 보조 관측이며 고정 단발 결과를 대체하지 않는다.

모의 판단+실제 HA의 저장 파일은 **service_contract 8개 + safety_negative 1개**, 합계 9개 assertion 통과다. 현재 일반 문서가 “서비스 계약 9/9”, “안전 거부 3건” 등으로 이를 섞어 설명한다. 각 레이어와 분모를 분리하고 수치를 정정한다.

다음 보고/릴리스 설명에서는:

- 실제 구현/검증된 대표 기능과 legacy notify, time/date 등 미지원·미검증을 구별한다. “B/C 전 항목 실기동 완료”와 대표 기능 MVP 검증을 혼동하지 않는다.
- 최신 설치형 앱에서 직접 확인한 것은 조명 실행/정책·재시작/다운로드이고, 달력·TTS 등의 깊은 계약 검증은 호스트 Engine→같은 테스트 HA 경로라는 구분을 유지한다. 다음 코드 보정 버전에서는 대표 B/C 명령도 설치 앱을 통해 한 번씩 확인한다.
- 다양한 일반 환경의 성능/정확도 보장, 사고율, ARM/Azure 실제 호출로 확대하지 않는다. 속도는 기록하되 엄격한 초 단위 합격 기준은 추가하지 않는다.

## 4. 다음 Executor의 완료 경로

다음 산출물은 **FIX_08_REPORT.md**다. R1의 작은 코드 보정과 R2의 문서/지원 범위 정정을 수행하고 필요한 회귀/CI 및 설치 검증을 마친다. 새로운 장기 설계 단계로 돌리지 않는다.

- 앱 코드가 바뀌므로 이미 설치된 dev.8보다 높은 Dev 버전을 사용한다. config/package/Docker/UI/CHANGELOG를 일치시키고 기존 tag를 덮어쓰지 않는다.
- Dev 커밋·Push·테스트 VM 업데이트·Dev prerelease는 이미 승인된 자율 범위다. 별도 승인 질문 없이 검증 가능한 Dev 배포 형태까지 진행한다.
- 본 라운드 이후에는 실제 작동하는 핵심 B/C와 관리자 로그 다운로드를 갖춘 Dev로 사용자 운영 시험을 지원할 수 있다. 미지원 기능을 솔직히 표시하면 되고, Jev 성공률이나 외부 API 지연 때문에 MVP를 무기한 보류하지 않는다.
- 기존 password/read 정책/rename/secondary target/모호한 todo/조건/저널/조명·공조 검증을 유지하고 프로젝트 소유 VM의 격리·정리를 지킨다. 운영 HA에 자동 설치하지 않는다.
- Main 및 안정 릴리스는 여전히 사용자 별도 명시 승인 이후다.
