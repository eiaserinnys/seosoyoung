# trello/list_runner.py

> 경로: `seosoyoung/trello/list_runner.py`

## 개요

ListRunner - 리스트 정주행 기능

트렐로 리스트의 카드를 순차적으로 처리하고,
각 단계 완료 후 검증 세션을 실행하여 품질을 확인합니다.

## 클래스

### `ListNotFoundError` (Exception)
- 위치: 줄 20
- 설명: 리스트를 찾을 수 없을 때 발생하는 예외

### `EmptyListError` (Exception)
- 위치: 줄 25
- 설명: 리스트에 카드가 없을 때 발생하는 예외

### `ValidationStatus` (Enum)
- 위치: 줄 30
- 설명: 검증 결과 상태

### `SessionStatus` (Enum)
- 위치: 줄 37
- 설명: 리스트 정주행 세션 상태

### `CardExecutionResult`
- 위치: 줄 48
- 설명: 카드 실행 결과

### `ValidationResult`
- 위치: 줄 58
- 설명: 검증 결과

### `CardRunResult`
- 위치: 줄 67
- 설명: 카드 실행 및 검증 전체 결과

### `ListRunSession`
- 위치: 줄 78
- 설명: 리스트 정주행 세션 정보

#### 메서드

- `to_dict(self)` (줄 91): 딕셔너리로 변환 (저장용)
- `from_dict(cls, data)` (줄 107): 딕셔너리에서 생성 (로드용)

### `ListRunner`
- 위치: 줄 123
- 설명: 리스트 정주행 관리자

트렐로 리스트의 카드를 순차적으로 처리합니다.

주요 기능:
- 세션 생성: 리스트의 카드 목록을 받아 정주행 세션 생성
- 진행 추적: 현재 처리 중인 카드 인덱스 관리
- 상태 관리: 세션 상태 (대기/실행/일시중단/검증/완료/실패)
- 영속성: 세션 정보를 파일에 저장하여 재시작 시 복원

#### 메서드

- `__init__(self, data_dir)` (줄 137): Args:
- `_load_sessions(self)` (줄 150): 세션 목록 로드
- `save_sessions(self)` (줄 164): 세션 목록 저장
- `create_session(self, list_id, list_name, card_ids)` (줄 179): 새 정주행 세션 생성
- `get_session(self, session_id)` (줄 209): 세션 조회
- `update_session_status(self, session_id, status, error_message)` (줄 220): 세션 상태 업데이트
- `get_active_sessions(self)` (줄 247): 활성 세션 목록 조회
- `get_paused_sessions(self)` (줄 265): 중단된 세션 목록 조회
- `find_session_by_list_name(self, list_name)` (줄 278): 리스트 이름으로 활성 세션 검색
- `pause_run(self, session_id, reason)` (줄 299): 정주행 세션 중단
- `resume_run(self, session_id)` (줄 330): 중단된 정주행 세션 재개
- `mark_card_processed(self, session_id, card_id, result)` (줄 359): 카드 처리 완료 표시
- `get_next_card_id(self, session_id)` (줄 385): 다음 처리할 카드 ID 조회
- `async start_run_by_name(self, list_name, trello_client)` (줄 403): 리스트 이름으로 정주행 세션 시작
- `_parse_validation_result(output)` (줄 451): 검증 결과 마커 파싱
- `async process_next_card(self, session_id, trello_client)` (줄 476): 다음 처리할 카드 정보 조회
- `async execute_card(self, session_id, card_info, claude_runner)` (줄 497): 카드 실행
- `async validate_completion(self, session_id, card_info, execution_output, claude_runner)` (줄 551): 카드 완료 검증
- `async run_next_card(self, session_id, trello_client, claude_runner, auto_pause_on_fail)` (줄 618): 다음 카드 실행 및 검증
