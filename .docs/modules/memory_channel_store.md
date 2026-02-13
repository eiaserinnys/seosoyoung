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
- `move_pending_to_judged(self, channel_id)` (줄 126): pending 내용을 judged에 append 후 pending 클리어
- `_thread_buffer_path(self, channel_id, thread_ts)` (줄 135): 
- `_thread_buffer_lock(self, channel_id, thread_ts)` (줄 138): 
- `append_thread_message(self, channel_id, thread_ts, message)` (줄 141): 스레드 메시지를 버퍼에 추가
- `load_thread_buffer(self, channel_id, thread_ts)` (줄 149): 스레드 메시지 버퍼를 로드. 없으면 빈 리스트.
- `load_all_thread_buffers(self, channel_id)` (줄 159): 채널의 전체 스레드 버퍼를 로드. {thread_ts: [messages]} 형태.
- `_count_messages_tokens(self, messages)` (줄 175): 메시지 리스트의 총 토큰 수를 계산
- `count_pending_tokens(self, channel_id)` (줄 185): pending 버퍼 총 토큰 수 (채널 + 스레드 합산)
- `count_judged_plus_pending_tokens(self, channel_id)` (줄 194): judged + pending 합산 토큰 수
- `count_buffer_tokens(self, channel_id)` (줄 200): count_pending_tokens의 하위호환 별칭
- `clear_buffers(self, channel_id)` (줄 206): pending + judged + 스레드 버퍼를 모두 비운다.
- `_digest_path(self, channel_id)` (줄 224): 
- `_digest_meta_path(self, channel_id)` (줄 227): 
- `_digest_lock_path(self, channel_id)` (줄 230): 
- `get_digest(self, channel_id)` (줄 233): digest.md를 로드. 없으면 None.
- `save_digest(self, channel_id, content, meta)` (줄 252): digest.md를 저장
- `_read_jsonl(path)` (줄 266): JSONL 파일을 읽어 리스트로 반환
