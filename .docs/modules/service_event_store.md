# service/event_store.py

> 경로: `seosoyoung/soul/service/event_store.py`

## 개요

Event Store - JSONL 기반 이벤트 저장소

대시보드 재접속 시 이전 이벤트 재생 및 세션 목록 조회를 위한
이벤트 영속화 계층.

각 세션(client_id:request_id)의 이벤트를 개별 JSONL 파일로 저장합니다.
파일 형식: {base_dir}/{client_id}/{request_id}.jsonl
각 줄: {"id": <monotonic_int>, "event": <event_dict>}

## 클래스

### `EventStore`
- 위치: 줄 23
- 설명: JSONL 기반 이벤트 저장소

Args:
    base_dir: JSONL 파일 저장 디렉토리

#### 메서드

- `__init__(self, base_dir)` (줄 30): 
- `_session_key(self, client_id, request_id)` (줄 38): 
- `_get_lock(self, key)` (줄 41): 
- `_sanitize_path_component(value)` (줄 45): 파일명에 안전한 문자만 남긴다 (영숫자, 점, 하이픈, 언더스코어).
- `_session_path(self, client_id, request_id)` (줄 49): 세션의 JSONL 파일 경로를 반환한다.
- `_load_next_id(self, client_id, request_id)` (줄 63): JSONL 파일에서 마지막 ID를 읽어 다음 ID를 결정한다.
- `append(self, client_id, request_id, event)` (줄 90): 이벤트를 JSONL 파일에 추가한다.
- `read_all(self, client_id, request_id)` (줄 116): 세션의 모든 이벤트를 반환한다.
- `read_since(self, client_id, request_id, after_id)` (줄 146): after_id 이후의 이벤트만 반환한다.
- `cleanup_session(self, client_id, request_id)` (줄 162): 세션의 캐시된 메타데이터를 제거한다.
- `delete_session(self, client_id, request_id)` (줄 171): 세션 데이터와 JSONL 파일을 제거한다.
- `list_sessions(self)` (줄 181): 저장된 세션 목록을 반환한다.
