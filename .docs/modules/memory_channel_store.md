# memory/channel_store.py

> 경로: `seosoyoung/memory/channel_store.py`

## 개요

채널 관찰 데이터 저장소

파일 기반으로 채널 단위의 관찰 데이터를 관리합니다.

저장 구조:
    memory/channel/{channel_id}/
    ├── digest.md              # 전체 누적 관찰 요약
    ├── digest.meta.json       # 메타데이터
    ├── pending.jsonl          # 아직 LLM이 보지 않은 새 대화
    ├── judged.jsonl           # LLM이 이미 리액션 판단을 거친 대화
    └── buffer_threads/
        └── {thread_ts}.jsonl  # 미소화 스레드별 메시지

## 클래스

### `ChannelStore`
- 위치: 줄 24
- 설명: 파일 기반 채널 관찰 데이터 저장소

channel_id를 기본 키로 사용합니다.

#### 메서드

- `__init__(self, base_dir)` (줄 30): 
- `_channel_dir(self, channel_id)` (줄 33): 
- `_ensure_channel_dir(self, channel_id)` (줄 36): 
- `_threads_dir(self, channel_id)` (줄 41): 
- `_ensure_threads_dir(self, channel_id)` (줄 44): 
- `_pending_path(self, channel_id)` (줄 51): 
- `_pending_lock(self, channel_id)` (줄 54): 
- `append_pending(self, channel_id, message)` (줄 57): 채널 루트 메시지를 pending 버퍼에 추가
- `load_pending(self, channel_id)` (줄 65): pending 버퍼를 로드. 없으면 빈 리스트.
- `clear_pending(self, channel_id)` (줄 75): pending 버퍼만 비운다.
- `append_channel_message(self, channel_id, message)` (줄 83): append_pending의 하위호환 별칭
- `load_channel_buffer(self, channel_id)` (줄 87): load_pending의 하위호환 별칭
- `_judged_path(self, channel_id)` (줄 93): 
- `_judged_lock(self, channel_id)` (줄 96): 
- `append_judged(self, channel_id, messages)` (줄 99): judged 버퍼에 메시지들을 추가
- `load_judged(self, channel_id)` (줄 108): judged 버퍼를 로드. 없으면 빈 리스트.
- `clear_judged(self, channel_id)` (줄 118): judged 버퍼만 비운다.
- `move_pending_to_judged(self, channel_id)` (줄 126): pending + 스레드 버퍼를 judged에 append 후 클리어
- `move_snapshot_to_judged(self, channel_id, snapshot_ts, snapshot_thread_ts)` (줄 141): 스냅샷에 포함된 메시지만 judged로 이동하고 나머지는 pending에 남깁니다.
- `_thread_buffer_path(self, channel_id, thread_ts)` (줄 193): 
- `_thread_buffer_lock(self, channel_id, thread_ts)` (줄 196): 
- `append_thread_message(self, channel_id, thread_ts, message)` (줄 199): 스레드 메시지를 버퍼에 추가
- `load_thread_buffer(self, channel_id, thread_ts)` (줄 207): 스레드 메시지 버퍼를 로드. 없으면 빈 리스트.
- `load_all_thread_buffers(self, channel_id)` (줄 217): 채널의 전체 스레드 버퍼를 로드. {thread_ts: [messages]} 형태.
- `_count_messages_tokens(self, messages)` (줄 233): 메시지 리스트의 총 토큰 수를 계산
- `count_pending_tokens(self, channel_id)` (줄 243): pending 버퍼 총 토큰 수 (채널 + 스레드 합산)
- `count_judged_plus_pending_tokens(self, channel_id)` (줄 252): judged + pending 합산 토큰 수
- `count_buffer_tokens(self, channel_id)` (줄 258): count_pending_tokens의 하위호환 별칭
- `_clear_thread_buffers(self, channel_id)` (줄 264): 스레드 버퍼 전체를 비운다.
- `clear_buffers(self, channel_id)` (줄 273): pending + judged + 스레드 버퍼를 모두 비운다.
- `_digest_path(self, channel_id)` (줄 281): 
- `_digest_meta_path(self, channel_id)` (줄 284): 
- `_digest_lock_path(self, channel_id)` (줄 287): 
- `get_digest(self, channel_id)` (줄 290): digest.md를 로드. 없으면 None.
- `save_digest(self, channel_id, content, meta)` (줄 309): digest.md를 저장
- `update_reactions(self, channel_id)` (줄 322): pending/judged/thread 버퍼에서 ts가 일치하는 메시지의 reactions를 갱신합니다.
- `_update_reactions_in_jsonl(self, path, lock_path, ts, emoji, user, action)` (줄 362): JSONL 파일 내에서 ts가 일치하는 메시지의 reactions를 갱신합니다.
- `_read_jsonl(path)` (줄 416): JSONL 파일을 읽어 리스트로 반환
