# FIX_09_REPORT — dev.9 설치 검증 및 Dev 배포 마무리

작성일: 2026-10-14 · 역할: Executor · 판정: **V1 설치 검증 완료, V2 Dev 릴리스 준비 완료, 서비스 설명 정정 완료**

기준: `FIX_09.md`(Reviewer, HEAD `685fdff`). FIX_08에서 승인된 코드 보정(`condition_unit` 예외 세분화 및 fail-closed 처리)을 바탕으로, 요구된 dev.9 실제 설치·기동 검증(V1)과 Dev prerelease 배포 인계(V2)를 완료했다.

---

## 1. 검증 명령 및 결과

- `uv run pytest -q`: **115 passed**, Starlette deprecation warning 1개 (기존과 동일).
- `uv run ruff check addon/app tests scripts`: **All checks passed!**
- `uv run ruff format --check addon/app tests scripts`: **20 files already formatted**.
- `hadolint addon/Dockerfile`: **통과** (exit code 0).
- `node --check addon/app/fhc/static/app.js`: **통과** (exit code 0).
- `git diff --check`: **통과** (공백 및 충돌 마커 없음).
- GitHub Checks (run `38512834220`, commit `53ba9b5`): test/arm-build 모두 **success** 확인.

---

## 2. V1 [P2] — dev.9 실제 설치 및 업데이트 검증

프로젝트 전용 QEMU HAOS(Core 2026.10.1, 2 vCPU, 4GiB RAM, 격리 네트워크 포트 18180 포워딩) 환경에서 실제 애드온 업데이트 및 기동 검증을 수행했다. 운영 HA 및 운영 가상머신은 일체 변경하지 않았다.

1. **공식 `#dev` 저장소 기반 업데이트**:
   - Supervisor `/store/reload` 호출 후 `https://github.com/Kanu-Coffee/fast-home-control#dev`의 최신 커밋 감지 확인 (`version: 0.2.0-dev.8` → `version_latest: 0.2.0-dev.9`, `update_available: true`).
   - Supervisor `/addons/a1444ce0_fast_home_control_dev/update` 호출로 **0.2.0-dev.9** 설치 및 기동 완료 (`state: started`, `version: 0.2.0-dev.9`).

2. **Ingress 관리자 세션 상태 확인**:
   - `GET /api/status`: version `0.2.0-dev.9`, `ha_ready: true`, `execution_ready: true`, `entities: 132`, 발견 도메인 정상 집계.

3. **Ingress 조명 제어 명령 (`거실불 꺼줘`)**:
   - 사전 상태: 거실 조명 2건(`light.ceiling_lights`, `light.living_room_rgbww_lights`)을 ON으로 설정.
   - 명령 실행: request_id `d54f5055-149f-4e73-8cf1-347d0abd7b84`, `status: succeeded`, `reason: ha_acknowledged_not_physical_confirmation`, 2×`turn_off` sent.
   - HA 상태 read-back: `light.ceiling_lights: off`, `light.living_room_rgbww_lights: off`, 타 영역 조명(`light.kitchen_lights: on`, `light.office_rgbw_lights: on`) 정상 유지 확인.

4. **Ingress 대표 B/C 명령 (`거실 날씨 어때`)**:
   - request_id `d1b1fbe4-2003-4ac1-a9a0-3a162069e233`.
   - 설치 앱 모델 평가에서 확신도 부족 시 무리한 오실행 없이 fail-closed 처리 (`status: rejected`, `reason: low_confidence`, 물리 전송 0건).

5. **Ingress 사전 조건문 명령 (`거실 온도가 28도 이상이면 거실불 꺼줘`)**:
   - request_id `28730370-c1ea-4cfb-9855-e39b5b3f188c`.
   - 조건 평가 단계에서 안전 거부 (`status: rejected`, `reason: condition_evaluation_failed`, `condition_result: null`, 물리 전송 0건).

6. **관리자 정책 저장 및 애드온 재시작 보존**:
   - `PUT /api/policy`: `read_domains: {'switch': false}`, `entities: {'light.bedroom': {'read_enabled': false}}` 설정 (200 OK).
   - Supervisor `/addons/a1444ce0_fast_home_control_dev/restart` 실행.
   - 재시작 후 Ingress 재연결: `api/status`의 `version: 0.2.0-dev.9` 및 `api/policy`의 `read_domains: {'switch': false}`, `entities` 설정 정상 보존 확인.
   - 검증 종료 후 테스트 정책을 기본값으로 원복.

7. **진단 ZIP 내보내기 검증**:
   - `GET /api/history/export`: 200 OK, `Content-Type: application/zip`.
   - ZIP 압축 해제 검증: `manifest.json`, `summary.json`, `requests.jsonl` 포함 확인.
   - 기본 내보내기 시 명령 원문 미포함(`has_command_text: false`) 및 API 토큰/비밀번호 비노출 검증.

8. **자원 정리**:
   - 테스트 VM은 QEMU 모니터 소켓을 통해 ACPI `system_powerdown`으로 정상 종료 완료.
   - `.local/test-resources.json`의 `state: stopped`, `last_tested_version: 0.2.0-dev.9`, `last_tested_app: 53ba9b5`로 갱신 완료.
   - 세부 실행 결과는 `.local/fix09-install-verification.json`에 원문 비밀정보 없이 기록.

---

## 3. V2 — Dev 배포 완료

- Git 태그: `v0.2.0-dev.9` 생성 및 `origin` 푸시.
- GitHub Prerelease: `v0.2.0-dev.9` 생성 (Microsoft Decision-1 기본 탑재, TypeSafe Jev 1.13 비교, notify/time/date 미지원 명시, 설치 및 업데이트 가이드 포함).
- **중요**: Main 브랜치 및 안정 릴리스는 변경하지 않았으며, 사용자 명시 승인 시까지 dev 브랜치와 prerelease 상태로 유지된다.

---

## 4. 서비스 레이어 설명 정정 (`docs/verification.md`)

FIX_09 §4의 지적에 따라 `docs/verification.md`의 서비스 계약 설명을 정정했다:
- `.local/fix06-live-scripted.json`의 `safety_negative 1개`는 `todo_duplicate_refused_before_write` (동명 할 일 사전 거부)임.
- password 시험은 별도 파일(`.local/fix06-live-r1-password.json`)로 검증된 항목이며, 서비스 계약 8개 + 안전 음성 1개(총 9개 assertion) 집계와 명확히 분리하여 기술했다.
