# memory/store.py

> 경로: `seosoyoung/memory/store.py`

## 개요

관찰 로그 저장소

파일 기반으로 세션(thread_ts) 단위 관찰 로그와 대화 로그를 관리합니다.

저장 구조:
    memory/
    ├── observations/
    │   ├── {thread_ts}.md          # 세션별 관찰 로그 (마크다운)
    │   └── {thread_ts}.meta.json   # 메타데이터 (user_id 포함)
    ├── pending/
    │   └── {thread_ts}.jsonl       # 세션별 미관찰 대화 버퍼 (누적)
    └── conversations/
        └── {thread_ts}.jsonl       # 세션별 대화 로그

## 클래스

### `MemoryRecord`
- 위치: 줄 28
- 설명: 세션별 관찰 로그 레코드

thread_ts를 기본 키로 사용하고, user_id는 메타데이터로 보관합니다.

#### 메서드

- `to_meta_dict(self)` (줄 44): 메타데이터를 직렬화 가능한 dict로 변환
- `from_meta_dict(cls, data, observations)` (줄 60): dict에서 MemoryRecord를 복원

### `MemoryStore`
- 위치: 줄 83
- 설명: 파일 기반 관찰 로그 저장소

세션(thread_ts)을 기본 키로 사용합니다.

#### 메서드

- `__init__(self, base_dir)` (줄 89): 
- `_ensure_dirs(self)` (줄 95): 저장소 디렉토리가 없으면 생성
- `_obs_path(self, thread_ts)` (줄 101): 
- `_meta_path(self, thread_ts)` (줄 104): 
- `_lock_path(self, thread_ts)` (줄 107): 
- `_conv_path(self, thread_ts)` (줄 110): 
- `get_record(self, thread_ts)` (줄 113): 세션의 관찰 레코드를 로드합니다. 없으면 None.
- `save_record(self, record)` (줄 130): 관찰 레코드를 저장합니다.
- `_pending_path(self, thread_ts)` (줄 147): 
- `_pending_lock_path(self, thread_ts)` (줄 150): 
- `append_pending_messages(self, thread_ts, messages)` (줄 153): 미관찰 대화를 세션별 버퍼에 누적합니다.
- `load_pending_messages(self, thread_ts)` (줄 163): 미관찰 대화 버퍼를 로드합니다. 없으면 빈 리스트.
- `clear_pending_messages(self, thread_ts)` (줄 179): 관찰 완료 후 미관찰 대화 버퍼를 비웁니다.
- `save_conversation(self, thread_ts, messages)` (줄 187): 세션 대화 로그를 JSONL로 저장합니다.
- `load_conversation(self, thread_ts)` (줄 196): 세션 대화 로그를 로드합니다. 없으면 None.
