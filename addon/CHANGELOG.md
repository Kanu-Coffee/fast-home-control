# 0.2.0-dev.9

- R1: `condition_unit` 선택 예외 처리에서 fallback 대상을 `low_confidence`로 엄격히 한정. `invalid_model_response`(malformed type/labels/probability/NaN/합계 불일치)는 정상 단위 파생으로 삼키지 않고 `invalid_model_response`로 fail-closed(HA 전송 0건) 처리.
- R2: 문서 및 지원 범위 정정: 서비스 계약 8건 + 안전 음성 1건(총 9개 assertion)과 모델별 실단발 평가(Microsoft 6/8, Jev 2/8) 분모·사유 명확화.

# 0.2.0-dev.8

- R1: password 모드 `input_text`는 catalog 구성 단계에서 완전히 제외(조회/제어/모델 입력/내보내기 모두 차단). 조회·디테일·조건·내보너기 등 모든 경로에서 실제 `mode` 속성으로 민감 여부를 판정하고 ID 문자열 검사에 의존하지 않음. 과거 이력은 안전성 분류가 없거나 엔티티가 삭제되면 보수적으로 원문 제외.
- R2: 읽기(read) 권한을 정책/DTO/API/마이그레이션/UI에 독립 연결. 쓰기 정책 저장·엔티티 개별 토글·rename/swap/cycle 시 읽기 설정 보존. 정책 미검증 조회/응답 조회 및 2차 출력 대상 차단. 개인 상태 도메인(person/device_tracker/zone) 및 캘린더·할 일 읽기는 명시 opt-in만 허용. `/api/domains`의 read/write 가능·허용 수 분리 집계.
- R3: TTS가 고정 `media_player`나 수동 매핑으로 방송하지 않도록, 실제 발견·허용된 출력 스피커 ref를 모델이 선택하고 정책/가용성/최종 효과를 백엔드에서 검증. 대상 누락·모호·제외 시 전송 0건.
- R4: `input_datetime` 시간·날짜 토큰, `calendar.get_events` 시작/종료 구간, `create_event` 시작/기간, `weather.get_forecasts` 요청 유형(지원 여부 검증), `todo.update_item` 대상 UID 조회 후 상태 구분 연결. 빈/불충분 payload 차단, 응답 원문 대신 요청 범위 요약 표시.
- R5: 조건 실행을 로컬 정규식 파서에서 모델 선택 typed 조건(source/ref/comparator/literal/단위)으로 전환. `장면`·`벽면`·`화면` 등 정상 명칭 오인 및 경계 비교(`넘으면` vs `이상`) 오류 해소. 부정·복합·기준 없는 조건은 전송 0건.
- R6: 진단 내보내기에서 실제 서비스 열거값과 사용자 생성 원문(option/이름/본문)을 구분해 기본 익명화 일관 적용, provider 실패 trace에 단계별 소요 시간·질문 수 기록(원문 prompt/body 미저장), 평가 하네스 reset 실패/응답 효과/상대 밝기 변화량 검증 보강.
- FIX_06: 달력 실제 응답 계약(`{"events":[...]}`/ISO 문자열, malformed를 빈 목록 성공과 분리), 시간 일정 종료 시각 필수(`calendar_end_time`, 임의 duration 폐기)·`오후 8시 30분`/month_day 한국어 시각 토큰·has_date+has_time 동시 결합, HA 시간대 모를 때 날짜/시간 쓰기·조회 거부, todo UID 참조를 첫 쓰기 전 preflight로 이동(혼합 명령도 0건), 조건 3분류(none/typed/unclear)와 단위 미상·충돌 시 안전 거부, live 하네스를 service_contract/e2e_model/safety_negative 3단계로 분리.
- FIX_07: `오후 8:30`·명시 연도(`2028년 10월 20일`) 완전 span 파싱과 잘못된 분/날짜의 부분 잘라쓰기 금지, fan·humidifier·media_player의 명시 전원 켜기 + 속성 동시 실행 보존, calendar/todo/weather/input_datetime의 상태 조회와 응답 조회를 단일 상호배타 선택으로 통합(query+get_events 상충 거부 구조 제거), 테스트 VM fixture 한글 이름/영역과 local_calendar/도메인 헬퍼 자동화.

# 0.2.0-dev.7

- F1: 레지스트리 reconcile 시 다중/교환/순환 rename 원자적 처리 및 정책 보존 (제외 정책 유실 결함 수정).
- F2: 이력 삭제(`clear_history`) 시 `proposed_plan` 및 텍스트/결과 필드 화이트리스트 기반 완전 제거.
- F3: `/api/domains` 엔드포인트 및 관리자 UI에서 발견/제어/조회/허용 엔티티 수 분리 및 상태/보류 사유 명시.
- F4: 관리자 진단 로그 다운로드(`GET /api/history/export`) 기능 구현 (ZIP 압축: manifest/summary/requests.jsonl, 재귀적 민감정보 redaction, 명령 원문 포함 토글, 관리자 권한 보호).
- B 도메인 확장: vacuum(시작/일시정지/정지/복귀), button(누름), fan(전원/풍속), cover(열기/닫기/위치), humidifier(전원/습도/모드), media_player(재생/일시정지/볼륨/음소거), 헬퍼(number, select, counter, script, automation, scene, input_boolean) 공식 서비스 및 상태 연동.
- C 도메인 확장: sensor/binary_sensor/weather/calendar/todo/person 상태 및 측정값 조회 지원(물리 서비스 미호출), 단순 명시 조건("거실 온도가 28도 이상이면...") 사전 평가 및 조건 불만족 시 무호출(0건) 처리.

# 0.2.0-dev.6

- 기본 Configuration 탭 API 및 모델 입력 숨김 해결 (기본 options 노출 및 Azure endpoint str 스키마 적용).
- 사용자 리모컨 화면과 관리자 설정·진단 화면 분리 (상시 진단/경고 문구 제거, 간결한 요약 결과).
- 동적 최근 성공 명령 바로가기 카드 (최대 6개, 원클릭 즉시 실행).
- 관리자 모드 동적 공급자 설정 (OpenRouter/Azure 세그먼트 전환, OpenRouter 모델 선택, 안전한 옵션 저장).
- 도메인 제어 확장 (climate 송풍/냉방/난방 모드 및 온도 조절, light 밝기·상대 밝기·색상·Kelvin 색온도 설정).
- 엔티티 세부 제어 정책 (도메인 마스터 토글 및 엔티티 개별 제외/포함 토글).
- SQLite PRAGMA user_version 순차 마이그레이션 (이전 버전 -> v3) 및 정책 하위 호환성 유지.

- 리뷰 수정: Ingress 실제 사용자 관리 권한 검사, 그룹 leaf 및 안정 ID 정책, 최신 capability preflight, 부호/단위/대상별 값 연결.
- 동작 후보의 로컬 키워드 gate 제거. 여러 속성을 묶어 계획하고 전체 매개변수로 no-op 판정.
- Supervisor 최신 옵션 병합, 저장 실패 보존, planning 중 변경 차단, 키 삭제·공급자 우선순위·라디오 접근성·기기 검색 개선.
- 테스트 업데이트마다 patch 식별자를 올려 `dev.2` / `dev.3`을 거쳐 `dev.4`로 기능 검증 후 검색 표시를 보완한 `dev.5`, 공개 명령 응답의 관리자 진단 분리를 적용한 `dev.6`로 업데이트. 이전 Dev 태그는 유지.

# 0.1.0-dev.1

- 최초 실험적 Dev MVP: 조명·스위치 ON/OFF, 영역·전체 조명·복수 대상.
- HA 자동 탐색, 이벤트 동기화, 주기·수동 재탐색, 재연결.
- OpenRouter Decision API 및 Azure 직접 연결 어댑터.
- 전체 허용 카탈로그를 사용하는 의미 기반 판단. 로컬 단어 필터 없음.
- Ingress 웹 UI, 도메인 정책, 실행 이력, 중복 요청 방지.
- 조건·밝기·온도·다른 도메인·외부 브릿지는 후속 범위.
