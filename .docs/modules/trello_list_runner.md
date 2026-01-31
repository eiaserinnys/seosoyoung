# trello/list_runner.py

> 경로: `seosoyoung/trello/list_runner.py`

## 개요

ListRunner - 리스트 정주행 기능

트렐로 리스트의 카드를 순차적으로 처리하고,
각 단계 완료 후 검증 세션을 실행하여 품질을 확인합니다.

## 클래스

### `ListNotFoundError` (Exception)
- 위치: 줄 19
- 설명: 리스트를 찾을 수 없을 때 발생하는 예외

### `EmptyListError` (Exception)
- 위치: 줄 24
- 설명: 리스트에 카드가 없을 때 발생하는 예외

### `SessionStatus` (Enum)
- 위치: 줄 29
- 설명: 리스트 정주행 세션 상태

### `ListRunSession`
- 위치: 줄 40
- 설명: 리스트 정주행 세션 정보

#### 메서드

- `to_dict(self)` (줄 53): 딕셔너리로 변환 (저장용)
- `from_dict(cls, data)` (줄 69): 딕셔너리에서 생성 (로드용)

### `ListRunner`
- 위치: 줄 85
- 설명: 리스트 정주행 관리자

트렐로 리스트의 카드를 순차적으로 처리합니다.

주요 기능:
- 세션 생성: 리스트의 카드 목록을 받아 정주행 세션 생성
- 진행 추적: 현재 처리 중인 카드 인덱스 관리
- 상태 관리: 세션 상태 (대기/실행/일시중단/검증/완료/실패)
- 영속성: 세션 정보를 파일에 저장하여 재시작 시 복원

#### 메서드

- `__init__(self, data_dir)` (줄 99): Args:
- `_load_sessions(self)` (줄 112): 세션 목록 로드
- `save_sessions(self)` (줄 126): 세션 목록 저장
- `create_session(self, list_id, list_name, card_ids)` (줄 141): 새 정주행 세션 생성
- `get_session(self, session_id)` (줄 171): 세션 조회
- `update_session_status(self, session_id, status, error_message)` (줄 182): 세션 상태 업데이트
- `get_active_sessions(self)` (줄 209): 활성 세션 목록 조회
- `mark_card_processed(self, session_id, card_id, result)` (줄 227): 카드 처리 완료 표시
- `get_next_card_id(self, session_id)` (줄 253): 다음 처리할 카드 ID 조회
- `async start_run_by_name(self, list_name, trello_client)` (줄 271): 리스트 이름으로 정주행 세션 시작
