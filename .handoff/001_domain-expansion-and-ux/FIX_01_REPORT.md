# FIX_01_REPORT — 단계 A 리뷰 수정 구현 및 실기동 결과

- 작성일: 2026-10-13
- 역할: Executor
- 지시: `FIX_01.md`의 R1~R8 구현. 기존 PLAN/REPORT/FIX는 보존했다.
- 작업 시작: `dev`, HEAD `e13c450`에 이전 Executor의 미커밋 0.2.0-dev.1 변경이 존재했다. 해당 변경을 이어서 수정했다.
- 최종 앱 소스: **`0b0330bae1b67522efe7be59f6e666ec58fe7bac` / `0.2.0-dev.6`**.
- Dev 배포 대상: **`v0.2.0-dev.6` prerelease**, 설치 저장소 `https://github.com/Kanu-Coffee/fast-home-control#dev`. 이 보고서와 검증 문서를 포함한 후속 커밋에 태그를 생성한다. 앱 소스는 위 실기동/CI 검증 커밋과 동일하게 유지한다.
- Main 반영/안정 릴리스: 수행하지 않음.

## 1. 결과와 수정 범위

R1~R7의 서버 검증·정책·설정·UI 수정을 구현하고 R8의 실제 HAOS 설치/업데이트 및 실제 Microsoft API 검증을 수행했다. 현재 단계는 PLAN의 A이며, 모든 B/C 도메인 확장을 완료한 것이 아니다.

| 항목 | 구현 파일/핵심 변경 | 검증 |
| --- | --- | --- |
| R1 관리 권한 | `ha.py`, `main.py`: trusted Ingress 사용자 ID를 매 요청 HA `config/auth/list`의 활성 사용자/owner/system-admin과 대조. 관리 설정/정책/탐색/이력 API 실패 시 닫힘. 공개 commands 응답은 판단 점수/계획/모델 trace를 제외하고 관리자 history만 상세 반환 | 자동화의 누락/알 수 없는 ID/권한 회수 및 실제 비관리자 403, 위조 owner 헤더 403, 관리자 부여 200, 회수 403. 최종 dev.6 재시험. 공개/관리 응답 분리 실기동 확인 |
| R2 엔티티 정책 | `catalog.py`, `store.py`, `main.py`: 알려진 실제 그룹을 leaf alias로 전개하고 그룹 ID는 실행 카탈로그에서 제거. 제외 leaf/중복/순환 처리. 레지스트리 안정 ID를 override에 저장하고 rename에 이동. 재사용 ID는 자동 허용하지 않음. typed override, 정책 revision | 실제 HA 그룹과 제외 bed=on 유지, 실제 rename 후 제외 유지. 모의 모델+실제 HA 실행에서 허용 ceiling만 off. 실제 모델의 그룹 이름 요청은 이번 표본에서 거부됐으므로 별칭 의미 해석까지 성공했다고 주장하지 않음 |
| R3 의미 선택/값 연결 | 새 `actions.py`, `engine.py`, `provider.py`: 문구 키워드 동작 gate 제거. 실제 capability/enum으로 속성별 선택지 구성. 부호·소수·단위·원문 위치의 literal 후보 ID를 모델이 대상/절별 선택. 한 엔티티의 모드+온도, 색+밝기를 묶음. 분할 질문의 target context 보존 | 대상별 25/24 값 연결·부호·복합 속성 회귀. 실제 모드/색/밝기 적용. 기존 임계값 유지. 최종 표본의 복수 온도 1건은 낮은 확신으로 무전송; 앞선 dev.2/dev.3에서 실제 성공한 이력과 구분 |
| R4 capability/preflight/no-op | `actions.py`, `catalog.py`, `ha.py`, `engine.py`: supported_features/서비스/색 모드 교집합, 단위/범위/보고된 step 검증, 최신 모든 대상의 capability signature 비교, 전체 매개변수 no-op | onoff 조명에 밝기/색 후보 없음, RANGE-only/단위/step/최신 feature 변경 음성 테스트. 실제 단순 조명의 색 요청 무전송. 색/밝기/온도 실제 HA attributes 검증 |
| R5 설정 일관성 | `config.py`, `main.py`, `static/app.js`: Supervisor 최신 옵션 GET 후 변경 필드만 병합해 POST. 운영 options 파일 직접 쓰기 제거. standalone만 mode 0600 임시 파일+원자적 replace. 실패는 오류/기존 runtime 유지. 공통 mutation lock과 전체 active job 차단, rescan/history runtime 적용, 폼도 변경 필드만 전송 | canonical merge/error/파일 실패/planning 차단 회귀. 실제 자기 API 저장 후 native 옵션 rescan=6 및 키 유지, 앱 재시작 후 유지 |
| R6 DB 이관 | `store.py`: transaction으로 이전 스키마/정책 검증 후 v3 이관, 손상/미래 버전 중단, 기존 light/switch 정책 보존. 기존 0.1 설치의 신규 climate 기본 OFF | 실제 0.1→업데이트 climate OFF 및 새 설치 기본값 구분. 손상 정책/미래 버전/기존 ID·저널 보존 테스트 |
| R7 UI/누락 기능 | 색온도 Kelvin 검증/실행 추가. 관리자 상세 phase/점수/모델/원문 계획/시간/결과 진단. 키 명시 삭제, Azure 빈 값 변경, 공급자 '우선' 표기, 라디오 키보드/ARIA, 이름·영역 검색 결과 자동 펼침. 사용자 화면과 바로가기 유지 | native 기본 키/모델 입력 노출. 실제 Ingress 데스크톱/모바일, 검색/키보드/연타/HTTP UUID fallback. RGB+밝기/Kelvin/상대 밝기 실제 적용 |
| R8 실제 환경 | 공식 Supervisor 저장소 갱신/업데이트, 별도 새 설치, HA Core 및 앱 재시작, 실제 모델+가상 HA, 양쪽 아키텍처 CI | 아래 결과 및 공개 evidence JSON 참조 |

## 2. 중요한 구현 조정

- 모델은 질문들을 독립적으로 판단하므로 같은 기기의 속성별 `choice`를 만들고 서버에서 검증한 값만 결합했다. 일반 생성형 tool calling이나 로컬 문장 분할 파서로 바꾸지 않았다.
- API가 `none` 하나뿐인 choice를 거부하는 실제 오류를 발견했다. 후보가 없는 속성 질문은 제거하되, 지원되는 동작을 한국어 단어로 제거하지 않는다. 해당 회귀 테스트를 추가했다.
- 실제 Core 2026.10.1 demo climate 일부는 `temperature_unit`/step을 state에 제공하지 않는다. 단위는 공식 `get_config.unit_system.temperature`로 보완하고 config 변경 이벤트를 동기화한다. step이 보고되면 검사하고, 보고되지 않으면 임의의 step을 만들지 않는다. 범위/단위가 없으면 실행하지 않는다.
- 모델이 공식 HA 서비스의 속성 변경 의미를 판단하도록 검증된 매개변수의 `effect` 설명을 최종 검증에 함께 제공했다. 확신도 기준(0.9 / 0.6+margin / 0.95)을 낮추거나 잘못된 응답을 승인받을 때까지 재시도하지 않았다.
- 새 설치와 기존 설치의 정책 기본값을 분리했다. 이미 설치된 중간 v2 구조의 명시 설정은 보존한다. 기존 0.1 bool 정책은 climate=false로 이관한다.
- UI와 API의 관리자 구분을 분리했다. 화면 토글을 권한으로 사용하지 않고, 공개 명령 결과 DTO에 상세 판단 진단을 넣지 않는다.
- 사용자의 업데이트 조건에 따라 테스트 VM에 이미 설치한 버전보다 매번 patch 식별자를 높였다: `0.1.0-dev.1 → 0.2.0-dev.2 → dev.3 → dev.4 → dev.5 → dev.6`. 중간 버전은 공개 prerelease로 발행하지 않았다.

## 3. 자동화와 빌드

| 명령/환경 | 결과 |
| --- | --- |
| `uv run pytest -q` | **71 passed**, FastAPI/Starlette testclient deprecation warning 1개. 최종 2.18초(추가 전 반복 결과는 별도) |
| `uv run ruff check addon/app tests scripts` | 통과 |
| `uv run ruff format --check addon/app tests scripts` | 통과, 19 files |
| `node --check addon/app/fhc/static/app.js` | 통과 |
| `git diff --check` | 통과, 기존 EOF 경고 정리 |
| `gitleaks git --staged --redact --no-banner --log-level warn` | 각 소스 커밋 및 보고서 stage 검사. 비밀정보 발견 없음 |
| `docker build -t fhc-fix-check addon` | 초기 수정 후보 amd64 빌드 통과. 최종 소스는 아래 CI로 별도 검증 |
| GitHub Checks `38355927298`, 소스 `0b0330b` | **test(71개/amd64 build), arm-build(aarch64) 모두 success** |

새 `tests/test_corrections.py`와 `tests/fixtures/haos.yaml`, 재현용 `scripts/evaluate_stage_a.py`를 추가했다. 이전 `evaluate_ha.py`의 밝기 음성 사례는 현재 지원 범위와 충돌하므로 실제 미지원 예약 명령으로 교체했다. 라이브 실행기는 localhost 테스트 HAOS와 Microsoft Decision-1/OpenRouter만 허용한다.

## 4. 실제 모델 및 가상 기기 결과

환경: 프로젝트 전용 QEMU/KVM HAOS 18.3, Core 2026.10.1, 2 vCPU/4GiB, localhost:18180. 실제 물리 기기를 연결하지 않았다. OpenRouter 요청 모델은 `microsoft/microsoft-decision-1`, 반환 식별자는 `microsoft/microsoft-decision-1-20261009`였다. Azure와 다른 모델을 실제 호출하지 않았다.

고정 세트의 Ingress dev.4 시험과 동일 엔진의 dev.5 실행기 시험은 각각 **13/15 기대 결과 일치**였다. 정상 명령 10개 중 8개 성공, 음성 5개 모두 거부/무전송. 상세 결과는 `docs/evidence/0.2.0-dev.5.json`에 민감정보 없이 보존한다.

- 실제 적용 성공: 송풍, “바람만” 표현, 제습, 냉방+25도, RGB 빨강+밝기 30프로, 3500K 색온도, 상대 밝기 -10%p, 거실 영역 소등.
- 정상인데 최종 세트에서 거부: “거실 에어컨 26도, 침실 에어컨 24도로”(action 확신 부족), “거실전등 켜줘”(scope 확신 부족). 추가 승인 추구 재시도나 임계값 하향은 하지 않았다. 앞선 별도 probe의 ON/OFF 성공은 이 세트의 실패를 대체하지 않는다.
- 음성: -25도, -20% 밝기, 불 끄기+현관문 열기, 아무거나 켜기, 조건부 켜져 있으면 끄기 모두 무전송.
- 최종 dev.6에 별도 자연어 “천장등 색온도 4000K로 맞춰줘”를 보내 실제 4000K 적용과 공개/관리 응답 DTO 분리를 확인했다.

기대하지 않은 대상/값 전송은 이 관측 세트에서 없었다. 고정 fixture 결과를 전체 한국어 정확도 보증으로 해석하지 않는다. 그룹 별칭 요청도 모델이 거부한 사례가 있어 후속 정확도 개선 대상이다.

성공한 고정 세트의 첫 HA dispatch는 **3.620–4.811초**, 추가 dev.6 smoke는 **5.131초**였다. 대표 성공의 scope 1.80–2.99초, action 0.89–1.00초, verify 0.83–0.89초, preflight 2–9ms였다. 논리 3단계가 scope 분할을 포함한 실제 HTTP 4회 호출이었다. 속도를 출시의 엄격한 통과 기준으로 삼지 않았다.

## 5. 설치·복구·브라우저

- 공식 `ha --no-progress store reload` / `ha --no-progress apps update a1444ce0_fast_home_control_dev` 경로로 업데이트했다. 기존 키/DB/저널을 보존했다.
- 별도 `local_fast_home_control_fixture` 새 설치를 기동했다. 키 없이 탐색/설정 UI 정상, 기본 옵션에 API/모델 관련 키 존재, 공개 config 응답에 키 원문 없음. 검증 후 uninstall했다.
- native HA Configuration 화면에서 unused optional 설정을 클릭하지 않고 OpenRouter 키와 Microsoft 모델 입력을 확인했다. 새 HA UI 경로는 `/config/app/<slug>/config`였다. 테스트 계정 토큰 만료 및 초기 onboarding 잔여 단계는 테스트 HA 안에서 정상 로그인/완료하여 해결했다.
- Core 재시작 후 연결/카탈로그가 복구됐다. 앱 재시작 후 canonical rescan=6 및 키, 기존 요청 기록이 유지됐다. 가상 조명을 반대 상태로 seed한 뒤 과거 UUID를 재전송해 상태가 다시 조작되지 않는 것을 확인했다.
- 네트워크 lost ACK, API 오류, DB 오류는 자동화의 fault injection으로 검증했다. 실제 네트워크 패킷 단절로 물리 ACK를 잃은 시험을 했다고 주장하지 않는다.
- Browser plugin not available. 설치된 Playwright Chromium으로 실제 Ingress를 검사했다. desktop 1280×900, mobile 390×844. 제목/비어 있지 않은 페이지/오류 overlay 없음, pageerror 및 console warning/error 없음, 가로 넘침 없음.
- 사용자/관리자 전환, 공급자 라디오 키보드·ARIA, 빈 비밀 입력, FHC 검색 결과 1개 도메인으로 축소 및 일치 엔티티 펼침, 원클릭 카드 연타에 commands POST 1회, randomUUID 없이 getRandomValues UUID fallback을 확인했다. 최종 카드 결과는 “이미 요청한 상태입니다.”였다.
- 스크린샷: `/tmp/fhc-fix-native-config.png`, `/tmp/fhc-fix-user-desktop.png`, `/tmp/fhc-fix-admin-desktop.png`, `/tmp/fhc-fix-admin-mobile.png`, `/tmp/fhc-fix-user-result-mobile.png`. Git 밖 임시 증거이므로 장기 보관을 보장하지 않는다.

## 6. 자원 정리와 남은 범위

프로젝트 전용 VM만 사용했다. guest 외부 private 네트워크 차단은 테스트 guest에만 적용했다. 기존 운영 VM, 호스트 방화벽, 다른 Docker 서비스/저장소는 수정하지 않았다.

검증 후 테스트 사용자, 별도 새 설치 앱/로컬 디렉터리, 전송 HTTP 서버, tar/전송 디렉터리, 호스트 `fhc-fix-check` 이미지를 제거했다. 프로젝트 VM은 ACPI로 정상 종료했다. baseline 디스크와 새 가상 fixture, Git 제외 자격 증명/진단 결과는 재사용 목적으로 보존하고 `.local/test-resources.json` 상태를 stopped로 갱신했다. `guest_console.py`는 busy root prompt 및 timeout을 명시적으로 검사하도록 보완했다.

남은 제약:

- 유효한 한국어 명령도 확신 부족으로 거부될 수 있다. 속도/정확도 후속 개선 대상이며 강제 실행/자동 재시도로 우회하지 않는다.
- Azure live, ARM 실기동, 실제 ID 삭제/재사용의 HA runtime 재현은 미수행이다. 각각 mock 계약, CI 빌드, 안정 ID/정책 회귀로 구분해 검증했다.
- 매우 큰 카탈로그는 40KB 안전 budget을 넘으면 명시적으로 거부한다. 엔티티를 조용히 잘라내지 않는다. 더 큰 환경의 paging 최적화는 후속 과제다.
- 색은 제공한 RGB 팔레트, 색온도는 명시 Kelvin을 지원한다. effect 선택, 임의 RGB 텍스트 생성, heat_cool 상하한, 조건/예약, B/C 도메인 및 외부 브릿지는 이번 A 범위에 추가하지 않았다.
- Main 승격/안정 배포는 사용자 실운영 검증과 명시 승인 이후다. 본 보고서는 Executor 결과이며 Reviewer 승인으로 간주하지 않는다.
