# Fast Home Control Dev

Configuration에서 OpenRouter API 키를 입력하거나 Microsoft Foundry의 API 키, HTTPS 리소스 endpoint, Decision-1 배포 이름을 입력하세요. 최소 한 공급자만 필요합니다. 저장 후 앱을 재시작합니다.

웹 UI에서 자연어 명령을 입력하세요. 첫 Dev는 조명과 스위치의 즉시 켜기/끄기를 지원합니다. “거실불 켜줘”, “집에 있는 조명 전부 꺼줘”처럼 사용합니다. 모호하거나 지원하지 않는 요청은 실행하지 않습니다. 밝기, 온도, 조건부 명령과 상태 조회는 아직 지원하지 않습니다.

HA 주소·토큰·개별 기기를 입력할 필요가 없습니다. 웹 UI에서 허용 도메인을 선택하고, 연결 상태·최근 이력을 확인하거나 수동 재탐색할 수 있습니다. 전체 자동 재탐색은 기본 12시간이며 Configuration에서 변경합니다.

허용된 기기 메타데이터와 명령이 설정한 AI 공급자로 전송됩니다. 성공 표시는 HA의 명령 수락이며 물리 기기 완료 보장은 아닙니다. 불확실한 실행은 자동 재전송하지 않습니다.

자세한 설치·제약·검증: https://github.com/Kanu-Coffee/fast-home-control/tree/dev
