# Fast Home Control 공식 브랜드 및 아이콘 가이드

## 1. 개요 및 디자인 콘셉트

- **브랜드 방향**: Fast Home Control — Home Assistant를 위한 빠른 AI 리모컨
- **핵심 시각 언어**:
  - 간결하고 기하학적인 현대적 스마트 리모컨 실루엣
  - 원형 탐색 링과 중앙부를 관통하는 날렵한 번개(⚡) 에너지 엠블럼을 결합하여 '즉각 반응'과 '속도'를 직관적으로 상징
  - 브랜드 시그니처 에메랄드 그린 (`#158747`) 액센트와 다크 슬레이트 차콜 캔버스 간의 강한 명암 대비
  - 16×16 / 32×32 파비콘 크기에서도 시인성을 유지할 수 있도록 불필요한 미세 버튼, 텍스트, 복잡한 회로 표현을 완전히 배제하고 대담한 솔리드 글리프 형태로 제작

## 2. 생성 도구 및 프롬프트 기록

- **도구**: Antigravity 내장 이미지 생성 서브에이전트 (`image-generator`)
- **생성 모델/엔진**: Imagen 3
- **사용 프롬프트**:
  > "Professional app icon for 'Fast Home Control'. Centered geometric vector glyph of a modern sleek smart home remote controller: a clean rounded rectangle silhouette with a circular navigation ring at the top and an elegant, sharp lightning bolt symbol carved dynamically through the center. Perfectly centered composition, balanced symmetry, generous safe margins. Bold clean silhouette, vibrant emerald green (#158747) to vivid electric jade gradient on a solid dark charcoal slate background inside an iOS-style rounded squircle. Crisp vector edges, high contrast, clean negative space, iconic, highly legible at small 16x16 favicon size. Absolutely no text, no words, no letters, no realistic textures, no clutter."
- **원본 마스터**: `docs/branding/master-icon.png` (1024×1024 PNG)

## 3. 파생 자산 목록

| 자산 경로 | 규격 | 용도 |
|---|---|---|
| `docs/branding/master-icon.png` | 1024×1024 PNG | 원본 마스터 아이콘 |
| `docs/branding/social-preview.png` | 1280×640 PNG | GitHub 저장소 Social Preview 카드 |
| `addon/icon.png` | 256×256 PNG | Home Assistant Add-on Store 공식 아이콘 |
| `addon/logo.png` | 512×512 PNG | Home Assistant Add-on 상세 정보 로고 |
| `addon/app/fhc/static/favicon.ico` | 16/32/48 ICO | 브라우저 탭 파비콘 (다중 해상도) |
| `addon/app/fhc/static/icon-32.png` | 32×32 PNG | 웹 UI 상단 헤더 로고 마크 및 브라우저 파비콘 |
| `addon/app/fhc/static/icon-192.png` | 192×192 PNG | 모바일 웹 바로가기 / 북마크 아이콘 |
| `addon/app/fhc/static/icon-512.png` | 512×512 PNG | 고해상도 앱 아이콘 |
| `addon/app/fhc/static/apple-touch-icon.png` | 180×180 PNG | iOS Safari 홈 화면 추가 아이콘 |

## 4. 노출 위치별 매핑 및 한계 명시

1. **웹 UI 헤더 & 브라우저 탭**:
   - `addon/app/fhc/static/index.html`에서 상대 경로(`static/favicon.ico`, `static/icon-32.png` 등)로 직접 참조하여 Ingress 및 독립 접속 모두에서 200 OK와 올바른 MIME 타입으로 로드.
   - 헤더에 `icon-32.png`와 텍스트 로고 결합 적용.
2. **Home Assistant 애드온 스토어**:
   - `addon/icon.png`, `addon/logo.png` 배치로 Supervisor 및 애드온 스토어 목록/상세 화면에 표시.
3. **Home Assistant Sidebar**:
   - `addon/config.yaml`의 `panel_icon: mdi:remote` 유지.
   - Home Assistant 플랫폼 제약상 사이드바 아이콘은 Material Design Icons(MDI) 식별자만 지원하며 외부 PNG 경로를 임의 지정할 수 없음. 가장 부합하는 `mdi:remote` 식별자를 유지.
4. **GitHub README 및 문서**:
   - `README.md` 상단 및 `addon/DOCS.md`에 공식 아이콘 마크 배치.
5. **GitHub Social Preview**:
   - `docs/branding/social-preview.png` 파일 생성 완료.
   - GitHub 저장소 설정(`Settings > General > Social preview`)에서 이미지를 업로드하는 것은 외부 웹 UI/권한 작업이 필요하므로 커밋 자산으로 제공하고 수동 적용 절차를 안내.
