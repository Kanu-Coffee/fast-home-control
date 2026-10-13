# Fast Home Control — Dev

Home Assistant OS에서 자연어로 가전을 조작하는 작은 AI 리모컨입니다. Microsoft-Decision-1의 구조화된 판단 API를 사용합니다. **0.2.0-dev.6에서는 조명·스위치뿐 아니라 에어컨/공조(climate) 제어 및 조명 밝기·색상·색온도 제어**를 지원합니다.

## 설치

1. Home Assistant의 **설정 → 앱 → 앱 스토어 → 저장소**에 `https://github.com/Kanu-Coffee/fast-home-control#dev`를 추가합니다. 이전 HA에서는 앱을 애드온이라고 표시합니다.
2. **Fast Home Control Dev**를 설치합니다. 첫 Dev는 공개 소스로 기기에서 컨테이너를 빌드하므로 첫 설치에 시간이 걸릴 수 있습니다.
3. Configuration 탭(기본 옵션에 바로 노출됨) 또는 웹 UI 관리자 모드에서 `openrouter_api_key`를 입력하거나 Azure의 세 항목을 입력하고 저장합니다.
4. 앱을 시작하고 웹 UI를 엽니다. HA 주소, 액세스 토큰, 개별 기기 등록은 필요 없습니다.

OpenRouter 설정만으로 시작하는 것을 권장합니다. Azure만 설정해도 동작하도록 구현했습니다. Azure 실서비스 검증 여부는 [검증 기록](docs/verification.md)을 확인하세요.

| 설정 | 설명 |
|---|---|
| `openrouter_api_key` | 선택. OpenRouter API 키 |
| `openrouter_model` | 선택. OpenRouter 모델 ID (기본: `microsoft/microsoft-decision-1`) |
| `azure_api_key` | 선택. Microsoft Foundry API 키 |
| `azure_endpoint` | 선택. 배포 리소스의 HTTPS origin. 경로 없이 입력 |
| `azure_deployment` | 선택. Microsoft-Decision-1 배포 이름 |
| `provider` | `auto` / `openrouter` / `azure`. 양쪽 설정 시 우선순위. 선택 공급자 실패 시 설정된 다른 공급자를 판단 단계에서 시도 |
| `rescan_hours` | 전체 재탐색 간격. 기본 12시간, 1–168시간 |
| `history_days` / `history_limit` | 로컬 실행 이력 보관. 기본 7일 / 1,000건 |

조명·스위치·에어컨 허용 범위는 관리자 모드의 도메인 및 엔티티 세부 설정으로 관리합니다. 기기 추가·삭제, 이름·영역 변경은 HA 이벤트로 반영하며 수동 재탐색도 제공합니다.

## 제공되는 기능 및 명령

- **조명 / 스위치**: “거실불 켜줘”, “거실전등 꺼줘”, “거실조명 꺼줘”, “침실 조명 전부 꺼줘”, “집에 있는 조명 전부 꺼줘”
- **조명 밝기 및 색상**: “거실 조명 빨간색으로”, “조명 조금 어둡게”, “조명 밝기 30%로”, “천장등 색온도 3500K로”
- **에어컨 / 공조**: “에어컨 켜줘 송풍모드”, “거실 에어컨 25도로”, “에어컨 꺼줘”, “거실 에어컨 냉방 25도로”, “거실 에어컨 제습으로”
- **동적 바로가기 카드**: 최근 성공한 실행 명령을 원클릭 카드로 즉시 실행 (최대 6개)
- **화면 모드 분리**: 기본 간결한 사용자 리모컨과 관리자용 설정·진단 화면 분리

실제 HA에 등록된 영역과 이름을 사용합니다. 영역 없는 기기는 이름으로 지정할 수 있습니다. 대상이 모호하거나 판단이 불확실하면 실행하지 않습니다. 도어락·보안장치 제어는 제공하지 않습니다.


기존 0.1 버전에서 업데이트하면 새 climate 도메인은 자동 허용되지 않습니다. 관리자 모드에서 필요한 도메인을 켜세요. 제외 정책은 HA 그룹의 실제 멤버와 엔티티 이름 변경에도 적용됩니다.

밝기·색·온도는 엔티티가 보고한 기능만 실행합니다. 색은 제공되는 기본 RGB 색상 팔레트, 색온도는 명시한 Kelvin 값, 온도는 명시한 °C/°F/℃/℉ 기호 또는 HA 단위를 사용합니다. 지원되지 않는 복잡한 색 표현·조건·예약·heat_cool 범위 온도·다른 도메인·외부 브릿지는 현재 거부합니다. 다른 OpenRouter 모델 ID를 입력할 수 있지만 Decisions 계약 호환성과 정확성을 보증하지 않으며 일반 chat 모델로 자동 전환하지 않습니다.

관리 API는 Ingress가 확인한 사용자 ID를 실제 HA 관리 권한과 대조합니다. 키 입력을 비우면 유지하고 별도 삭제 선택으로 지웁니다. 웹 저장은 Supervisor 옵션에 반영되며 native Configuration 수정은 앱 재시작으로 적용하세요.

## 데이터와 실행 결과

명령과 허용된 기기 이름·영역·별칭·일부 상태가 선택한 AI 공급자로 전송됩니다. API 키는 HA의 앱 옵션에 저장되며 UI와 실행 이력에는 반환하지 않습니다. 명령 이력은 앱의 `/data`에 저장하고 웹 UI에서 지울 수 있습니다. 이력을 지워도 중복 실행 방지를 위한 요청 ID와 상태는 보관 기간 동안 남습니다.

“HA 명령 수락”은 서비스 호출 응답을 받았다는 뜻입니다. 물리 기기의 완료를 보장하지 않습니다. 통신 중단으로 실행 여부가 불확실하면 자동 재전송하지 않습니다. 새 명령을 보내기 전에 기기 상태를 확인하세요. 서로 다른 요청 ID의 동일 문장은 새로운 사용자 명령으로 취급합니다.

## 개발 / 배포

```sh
uv sync --frozen --python 3.13
uv run ruff check addon/app tests scripts
uv run ruff format --check addon/app tests scripts
uv run pytest -q
docker build -t fhc-dev addon
```

[개발·실기동 테스트](docs/testing.md), [검증 기록](docs/verification.md), [릴리스 정책](docs/releases.md)을 제공합니다. Dev 개발·배포는 자율 진행하며 **Main과 안정 릴리스는 사용자 명시 승인 이후** 진행합니다. MIT License.
