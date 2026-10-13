# Fast Home Control — Dev

Home Assistant OS에서 자연어로 가전을 조작하는 작은 AI 리모컨입니다. Microsoft-Decision-1의 구조화된 판단 API를 사용합니다. **첫 Dev는 조명·스위치 켜기/끄기 MVP**이며 안정 버전이 아닙니다.

## 설치

1. Home Assistant의 **설정 → 앱 → 앱 스토어 → 저장소**에 `https://github.com/Kanu-Coffee/fast-home-control#dev`를 추가합니다. 이전 HA에서는 앱을 애드온이라고 표시합니다.
2. **Fast Home Control Dev**를 설치합니다.
3. Configuration에서 `openrouter_api_key`를 입력하거나 Azure의 세 항목을 입력하고 저장합니다.
4. 앱을 시작하고 웹 UI를 엽니다. HA 주소, 액세스 토큰, 개별 기기 등록은 필요 없습니다.

OpenRouter 설정만으로 시작하는 것을 권장합니다. Azure만 설정해도 동작하도록 구현했습니다. Azure 실서비스 검증 여부는 [검증 기록](docs/verification.md)을 확인하세요.

| 설정 | 설명 |
|---|---|
| `openrouter_api_key` | 선택. OpenRouter API 키 |
| `azure_api_key` | 선택. Microsoft Foundry API 키 |
| `azure_endpoint` | 선택. 배포 리소스의 HTTPS origin. 경로 없이 입력 |
| `azure_deployment` | 선택. Microsoft-Decision-1 배포 이름 |
| `provider` | `auto` / `openrouter` / `azure`. 양쪽 설정 시 우선순위. 선택 공급자 실패 시 설정된 다른 공급자를 판단 단계에서 시도 |
| `rescan_hours` | 전체 재탐색 간격. 기본 12시간, 1–168시간 |
| `history_days` / `history_limit` | 로컬 실행 이력 보관. 기본 7일 / 1,000건 |

조명·스위치 허용 범위는 웹 UI의 도메인 스위치로 관리합니다. 기기 추가·삭제, 이름·영역 변경은 HA 이벤트로 반영하며 수동 재탐색도 제공합니다.

## 첫 Dev에서 가능한 명령

- “거실불 켜줘”, “거실전등 꺼줘”, “거실조명 꺼줘”
- “침실 조명 전부 꺼줘”, “집에 있는 조명 전부 꺼줘”
- “거실 불 끄고 거실 콘센트 켜줘”

실제 HA에 등록된 영역과 이름을 사용합니다. 영역 없는 기기는 이름으로 지정할 수 있습니다. 대상이 모호하거나 판단이 불확실하면 실행하지 않습니다. 밝기·온도·조건·예약·상태 조회 및 다른 도메인은 후속 개발 범위이며, 지원하지 않는 절을 포함한 명령 전체를 거부하도록 설계했습니다. 도어락·보안장치 제어는 제공하지 않습니다.

모델에는 허용된 전체 카탈로그를 먼저 전달합니다. 로컬 정규식이나 단어 일치로 후보를 제거하지 않습니다. 매우 큰 카탈로그는 임의로 잘라 실행하지 않고 명확히 거부합니다. [구조와 후속 계획](docs/architecture.md)을 참고하세요.

## 데이터와 실행 결과

명령과 허용된 기기 이름·영역·별칭·일부 상태가 선택한 AI 공급자로 전송됩니다. API 키는 HA의 앱 옵션에 저장되며 UI와 실행 이력에는 반환하지 않습니다. 명령 이력은 앱의 `/data`에 저장하고 웹 UI에서 지울 수 있습니다. 이력을 지워도 중복 실행 방지를 위한 요청 ID와 상태는 보관 기간 동안 남습니다.

“HA 명령 수락”은 서비스 호출 응답을 받았다는 뜻입니다. 물리 기기의 완료를 보장하지 않습니다. 통신 중단으로 실행 여부가 불확실하면 자동 재전송하지 않습니다. 새 명령을 보내기 전에 기기 상태를 확인하세요. 서로 다른 요청 ID의 동일 문장은 새로운 사용자 명령으로 취급합니다.

## 개발 / 배포

```sh
uv sync --frozen --python 3.13
uv run ruff check app tests scripts
uv run ruff format --check app tests scripts
uv run pytest -q
docker build -t fhc-dev .
```

[개발·실기동 테스트](docs/testing.md), [검증 기록](docs/verification.md), [릴리스 정책](docs/releases.md)을 제공합니다. Dev 개발·배포는 자율 진행하며 **Main과 안정 릴리스는 사용자 명시 승인 이후** 진행합니다. MIT License.
