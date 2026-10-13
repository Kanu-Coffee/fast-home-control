# 승인된 개발 방향과 구현

## 목적과 확장된 MVP

Fast Home Control은 대화 비서가 아니라 HAOS에서 작동하는 자연어 리모컨이다. API 공급자 정보 외에 HA URL, Long-Lived Access Token, 기기 등록, 사용자 YAML을 요구하지 않는다.

- **0.1.0-dev.1:** 조명·스위치 켜기/끄기 MVP.
- **0.2.0-dev.3 (단계 A):** 기본 옵션 노출, 사용자 리모컨 / 관리자 설정 분리, 최근 성공 명령 원클릭 카드, OpenRouter 모델 선택, 공식 도메인 확장(climate 송풍/냉방/난방 모드 및 온도 설정, light 밝기·색상 설정), 도메인 및 엔티티 세부 제어 정책, SQLite user_version v2 마이그레이션.

## Decision-1의 실제 계약

일반 chat completions/function calling을 사용하지 않는다. `state`와 이름별 `questions`를 보내고 `answers`를 받는다. `noul`은 참일 확률, `choice`는 고정 선택지와 확률 분포다. 질문은 같은 state를 독립적으로 판단하며 다른 질문의 답을 다음 질문에서 참조하지 못한다. 자유 텍스트 실행계획이나 임의 수치 매개변수를 생성하는 모델이 아니다.

OpenRouter는 `POST https://openrouter.ai/api/alpha/decisions`, Bearer 키, 모델 선택(기본 `microsoft/microsoft-decision-1`)을 지원한다. Azure는 `POST {resource-origin}/providers/microsoft/v1/systemone`, `api-key`, 배포 이름을 사용한다. 공급자 인증·전송만 분리하며 판단·실행 코어는 공유한다. 설정된 우선 공급자의 통신/API 오류는 판단 단계에서 다른 설정 공급자로 전환할 수 있다. 잘못된 판단 응답을 더 허용적인 결과가 나올 때까지 재시도하지 않는다.

## 실행 파이프라인과 후보 누락 방지

1. **허용 카탈로그 구성:** 정책에 허용된 도메인 및 엔티티 전체를 구성한다. 도메인이 허용되어도 개별 제외된 엔티티는 제외한다. 사용자 문장의 로컬 정규식·키워드 매칭으로 기기를 사전에 제거하지 않는다.
2. **범위 및 모드 판단:** 전체 허용 기기의 이름·별칭·장치 이름을 영역/도메인별로 압축해 전달한다. 모델이 요청의 지원 여부와 관련 그룹을 판단한다.
3. **매개변수 바인딩 및 선택:** 원문의 literal 수치(온도, 밝기 %, 색상)와 엔티티가 실제 지원하는 기능(hvac_modes, temp_range, color_modes)을 대조하여 기기별 `choice` criteria를 동적으로 구성한다. 모델이 대상 기기별 최적 동작을 선택한다.
4. **계획 검증:** 요청 전체와 생성된 typed plan이 일치하는지 별도 모델 질문(`exact`)으로 검증한다. 범위 판단 0.9 이상, 중간 후보 0.6 이상, 최종 정확성 0.95 이상을 유지한다.
5. **사전 조회 및 No-op 판단:** 모든 대상의 최신 HA 상태를 preflight로 조회한다. 조명이 이미 on이어도 밝기나 색상 변경은 실행하며, 동일한 상태일 때만 `already_in_state` no-op으로 처리한다. climate 역시 현재 모드/온도와 요청이 같을 때만 no-op으로 처리한다.
6. **디스패치 및 저널링:** 실행 직전 저널에 `uncertain`으로 기록하고 HA 서비스를 호출한다. `service_data` 매개변수를 공식 WS payload에 실어 전달한다. 미확인 응답은 재전송하지 않는다.

## HA 연동과 설정

- `homeassistant_api: true`로 주입되는 `SUPERVISOR_TOKEN`과 `/core/websocket`, `/core/api`를 사용한다.
- 관리자 모드에서 공급자 설정 및 모델 변경 시 Supervisor 자기 옵션 API (`/addons/self/options`)를 호출하여 안전하게 설정을 동기화한다.
- SQLite 저널은 `PRAGMA user_version`을 순차 검사하여 v1에서 v2로 마이그레이션하며, 기존 정책을 무손실 매핑한다.

## 후속 단계

1. **단계 B 일반 가전 확장:** fan, cover, humidifier, vacuum, media_player 및 도우미 도메인(input_boolean, number, select 등) 순차 추가.
2. **단계 C 조회 및 원문 기반 작업:** sensor, weather, calendar/todo 등 읽기 전용 및 응답 서비스 연동.
3. **안정 채널:** 사용자의 Dev 실운영 검증과 명시 승인 후 main으로 승격.
