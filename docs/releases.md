# Dev / Main 정책

- 개발 소스와 앱 저장소는 `dev` 브랜치다. 버전은 `0.1.0-dev.1`처럼 표시하고 GitHub prerelease를 사용한다.
- 이미지: `ghcr.io/kanu-coffee/fast-home-control-dev:<version>`, amd64/aarch64. 버전별 이미지를 생성하며 이미 배포한 버전은 새 코드로 덮어쓰지 않는다.
- Checks가 통과한 dev commit에 대해 Publish Dev를 수동 실행한다. 이미지 생성·공개 pull·실설치 검증 후 동일 commit에 `v<version>` 태그와 prerelease를 만든다. 태그 생성으로 재빌드하지 않는다.
- 릴리스 설명에 지원 범위, 실제/모의 검증 구분, 알려진 제약을 기록한다. 치명적 문제는 이전 버전 재설치 또는 다음 Dev 수정 버전으로 복구한다. HA 백업 기능을 활용한다.
- `main` 반영과 stable slug/image 및 정식 릴리스 생성은 사용자 명시 승인 이후 진행한다. 첫 Dev를 안정 버전으로 자동 승격하지 않는다.
- API 키, 테스트 HA 토큰, VM 디스크와 실행 이력은 Git 및 컨테이너 빌드 컨텍스트에서 제외한다.
