# 개발과 실기동 테스트

`uv sync --frozen --python 3.13`, `uv run pytest -q`로 API 계약·실행 안전성·Ingress 접근 검사를 실행한다. ScriptedProvider는 배관 테스트용이며 자연어 정확도의 근거가 아니다. Azure 테스트는 MockTransport 계약 검증이며 실제 배포에 대한 호출은 별도 키와 endpoint가 필요하다.

실제 개발 호스트에서는 기존 libvirt 운영 VM과 Docker 서비스에 손대지 않고 사용자 권한 QEMU/KVM 테스트 VM을 생성했다. HAOS 18.3 공식 이미지의 SHA256을 검증하고 2 vCPU, 4GiB RAM, 32GiB sparse disk를 사용했다. sudo 비대화형 접근이 없어 시스템 libvirt 변경 대신 직접 QEMU를 사용했다. HA Core 2026.10.1을 실행하고 공식 demo integration 가상 엔티티로 시험한다. 테스트 HA에만 YAML을 작성하는 것은 설치 사용자 Zero-Config와 별개다.

호스트 포트는 localhost에만 바인딩한다. VM 내부에서 물리 LAN의 private IP 대역으로 나가는 연결을 차단하고 DNS·지정한 테스트 전송 포트만 허용한다. 운영 호스트 방화벽은 변경하지 않는다. 테스트 자원 경로는 `~/.local/share/fast-home-control-test/`이며 `scripts/guest_console.py`도 이 전용 serial socket만 대상으로 한다. VM 설치·인증 정보는 Git 제외 `.local/`에 저장한다.

실기동 시 다음을 구분해 확인한다: HA 자동 탐색과 별칭, 실제 모델 판단, HA 서비스 수락, 가상 기기 상태 변화, Ingress 브라우저 조작. 기기 추가/삭제·영역/이름 변경·수동 탐색·HA 재시작 후 복구를 검사한다. 키/오류 본문을 출력하지 않고 명령·상태·지연만 기록한다. 테스트 종료 후 임시 서버와 VM 프로세스를 정리한다.

브라우저 테스트는 로컬 Playwright Chromium을 사용한다. 데스크톱과 모바일에서 오버플로, 버튼·도메인 정책·이력·재탐색을 검사한다. 결과와 검증 공백은 [verification.md](verification.md)에 남긴다.
