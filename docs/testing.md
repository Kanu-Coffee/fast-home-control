# 개발과 실기동 테스트

`uv sync --frozen --python 3.13`, `uv run pytest -q`로 API 계약·실행 안전성·Ingress 접근 검사를 실행한다. ScriptedProvider는 배관 테스트용이며 자연어 정확도의 근거가 아니다. Azure 테스트는 MockTransport 계약 검증이며 실제 배포에 대한 호출은 별도 키와 endpoint가 필요하다.

실제 개발 호스트에서는 기존 libvirt 운영 VM과 Docker 서비스에 손대지 않고 사용자 권한 QEMU/KVM 테스트 VM을 생성했다. HAOS 18.3 공식 이미지의 SHA256을 검증하고 2 vCPU, 4GiB RAM, 32GiB sparse disk를 사용했다. sudo 비대화형 접근이 없어 시스템 libvirt 변경 대신 직접 QEMU를 사용했다. HA Core 2026.10.1을 실행하고 공식 demo integration 가상 엔티티로 시험한다. 테스트 HA에만 YAML을 작성하는 것은 설치 사용자 Zero-Config와 별개다.

호스트 포트는 localhost에만 바인딩한다. VM 내부에서 물리 LAN의 private IP 대역으로 나가는 연결을 차단하고 DNS·지정한 테스트 전송 포트만 허용한다. 운영 호스트 방화벽은 변경하지 않는다. 테스트 자원 경로는 `~/.local/share/fast-home-control-test/`이며 `scripts/guest_console.py`도 이 전용 serial socket만 대상으로 한다. VM 설치·인증 정보는 Git 제외 `.local/`에 저장한다.

실기동 시 다음을 구분해 확인한다: HA 자동 탐색과 별칭, 실제 모델 판단, HA 서비스 수락, 가상 기기 상태 변화, Ingress 브라우저 조작. 기기 추가/삭제·영역/이름 변경·수동 탐색·HA 재시작 후 복구를 검사한다. 키/오류 본문을 출력하지 않고 명령·상태·지연만 기록한다. 테스트 종료 후 임시 서버와 VM 프로세스를 정리한다.

브라우저 테스트는 Playwright Chromium을 사용한다. 깨끗한 CI 환경이나 신규 호스트에서는 브라우저 바이너리가 준비되어 있어야 하므로 사전 준비 단계를 거친다:
- Chromium 바이너리 및 시스템 의존성 설치: `uv run playwright install --with-deps chromium` (또는 사용자 지정 캐시: `PLAYWRIGHT_BROWSERS_PATH=/path/to/cache uv run playwright install chromium`)
- 브라우저 검사 실행: `uv run pytest -q tests/test_browser_ui.py`
- 전체 테스트 스위트 실행: `uv run pytest -q`
- GitHub Actions 워크플로 정적 검사: `actionlint .github/workflows/check.yml`
데스크톱과 모바일에서 가로 넘침, 버튼 정렬, 터치 영역(>=44px), 도메인 정책 PUT/GET 후속 생명주기 및 잠금 해제, 검색 중 아코디언 접힘/펼침, 진단 이력 내부 스크롤 및 포커스 보존을 검사한다. 결과와 검증 공백은 [verification.md](verification.md)에 남긴다.

## 0.2 단계 A 회귀

`tests/test_corrections.py`는 그룹 leaf 제외/중복/순환, 안정 ID rename, legacy DB/손상/미래 버전, 단위/step/최신 capability, 대상별 literal 연결, 복합 속성/no-op, Supervisor 최신 옵션 병합/오류, 활성 planning 중 변경, 관리 권한 거부를 검사한다. 전체 71개 테스트와 Ruff/JS 구문 검사를 실행한다.

테스트 VM에서만 `tests/fixtures/haos.yaml`을 사용한다. 공식 demo 기기, 실제 조명 그룹, 밝기/색 없는 template light를 제공한다. FIX_06/07부터 `input_datetime.fhc_wake`(has_time)·`input_text.fhc_secret`(password) 헬퍼와 writable local_calendar(`FHC 로컬 일정`)가 fixture에 포함된다. local_calendar는 YAML platform이 제거되어 config flow API로 생성하며 `scripts/verify_live_bc.py`가 실행마다 entry를 재생성해 상태를 누적시키지 않는다. demo 스피커/날씨/센서/할 일에는 한글 registry 이름(침실 스피커, 집 날씨, 밖에 온도, 장보기 목록 등)을 WS 엔티티 registry update로 부여해 한국어 지칭을 시험한다. 사용자 설치에는 YAML 편집이 필요 없다. 레지스트리에서 `climate.hvac` 이름을 “거실 에어컨”, `climate.heatpump`를 “침실 에어컨”으로 설정하고 기존 영역 fixture를 유지한다.

유효한 개발용 HA 토큰과 OpenRouter 키를 Git 제외 `.local/ha-credentials.json` / `.local/options.json`에 준비한 뒤 `PYTHONPATH=addon/app uv run python scripts/evaluate_stage_a.py`를 실행한다. localhost 테스트 HAOS와 Microsoft Decision-1/OpenRouter만 허용하는 검사이며 다른 모델/운영 HA로 바꿔 실행하지 않는다. 실제 HA 상태·속성과 기대값을 비교하고 `.local/stage-a-evaluation.json`에 결과를 기록한다. 키와 토큰을 출력하지 않는다. 단위 테스트와 이 실제 호출 결과를 혼동하지 않는다.

Supervisor의 공식 저장소 갱신→업데이트로 시험한다. **이미 설치한 Dev보다 높은 버전 식별자가 있어야 업데이트된다.** 이번 검증은 0.1.0-dev.1→0.2.0-dev.2→dev.3→dev.4→dev.5→dev.6로 수행했다. Main/안정 버전은 자동 변경하지 않는다.

`guest_console.py`는 프로젝트 전용 serial socket에서 root prompt를 확인한 뒤 명령을 보낸다. CLI spinner 실행 중 다음 명령이 유실되지 않도록 `ha --no-progress ...`와 충분한 timeout을 사용한다. timeout은 명령 취소가 아니므로 상태를 조회한 뒤 다음 작업을 진행한다.
