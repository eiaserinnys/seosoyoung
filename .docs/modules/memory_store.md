# memory/store.py

> 경로: `seosoyoung/memory/store.py`

## 개요

관찰 로그 저장소

파일 기반으로 사용자별 관찰 로그와 세션별 대화 로그를 관리합니다.

저장 구조:
    memory/
    ├── observations/
    │   ├── {user_id}.md          # 관찰 로그 (마크다운)
    │   └── {user_id}.meta.json   # 메타데이터
    └── conversations/
        └── {thread_ts}.jsonl     # 세션별 대화 로그

## 클래스

### `MemoryRecord`
- 위치: 줄 26
- 설명: 사용자별 관찰 로그 레코드

#### 메서드

- `to_meta_dict(self)` (줄 38): 메타데이터를 직렬화 가능한 dict로 변환
- `from_meta_dict(cls, data, observations)` (줄 53): dict에서 MemoryRecord를 복원

### `MemoryStore`
- 위치: 줄 75
- 설명: 파일 기반 관찰 로그 저장소

#### 메서드

- `__init__(self, base_dir)` (줄 78): 
- `_ensure_dirs(self)` (줄 83): 저장소 디렉토리가 없으면 생성
- `_obs_path(self, user_id)` (줄 88): 
- `_meta_path(self, user_id)` (줄 91): 
- `_lock_path(self, user_id)` (줄 94): 
- `_conv_path(self, thread_ts)` (줄 97): 
- `get_record(self, user_id)` (줄 100): 사용자의 관찰 레코드를 로드합니다. 없으면 None.
- `save_record(self, record)` (줄 117): 관찰 레코드를 저장합니다.
- `save_conversation(self, thread_ts, messages)` (줄 134): 세션 대화 로그를 JSONL로 저장합니다.
- `load_conversation(self, thread_ts)` (줄 143): 세션 대화 로그를 로드합니다. 없으면 None.
