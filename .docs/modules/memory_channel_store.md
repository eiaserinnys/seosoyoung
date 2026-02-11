# memory/channel_store.py

> 경로: `seosoyoung/memory/channel_store.py`

## 개요

채널 관찰 데이터 저장소

파일 기반으로 채널 단위의 관찰 데이터를 관리합니다.

저장 구조:
    memory/channel/{channel_id}/
    ├── digest.md              # 전체 누적 관찰 요약
    ├── digest.meta.json       # 메타데이터
    ├── buffer_channel.jsonl   # 미소화 채널 루트 메시지
    └── buffer_threads/
        └── {thread_ts}.jsonl  # 미소화 스레드별 메시지

## 클래스

### `ChannelStore`
- 위치: 줄 23
- 설명: 파일 기반 채널 관찰 데이터 저장소

channel_id를 기본 키로 사용합니다.

#### 메서드

- `__init__(self, base_dir)` (줄 29): 
- `_channel_dir(self, channel_id)` (줄 32): 
- `_ensure_channel_dir(self, channel_id)` (줄 35): 
- `_threads_dir(self, channel_id)` (줄 40): 
- `_ensure_threads_dir(self, channel_id)` (줄 43): 
- `_channel_buffer_path(self, channel_id)` (줄 50): 
- `_channel_buffer_lock(self, channel_id)` (줄 53): 
- `append_channel_message(self, channel_id, message)` (줄 56): 채널 루트 메시지를 버퍼에 추가
- `load_channel_buffer(self, channel_id)` (줄 64): 채널 루트 메시지 버퍼를 로드. 없으면 빈 리스트.
- `_thread_buffer_path(self, channel_id, thread_ts)` (줄 76): 
- `_thread_buffer_lock(self, channel_id, thread_ts)` (줄 79): 
- `append_thread_message(self, channel_id, thread_ts, message)` (줄 82): 스레드 메시지를 버퍼에 추가
- `load_thread_buffer(self, channel_id, thread_ts)` (줄 90): 스레드 메시지 버퍼를 로드. 없으면 빈 리스트.
- `load_all_thread_buffers(self, channel_id)` (줄 100): 채널의 전체 스레드 버퍼를 로드. {thread_ts: [messages]} 형태.
- `count_buffer_tokens(self, channel_id)` (줄 116): 버퍼 총 토큰 수 (채널 + 스레드 합산)
- `clear_buffers(self, channel_id)` (줄 136): 소화 완료 후 채널+스레드 버퍼를 비운다.
- `_digest_path(self, channel_id)` (줄 153): 
- `_digest_meta_path(self, channel_id)` (줄 156): 
- `_digest_lock_path(self, channel_id)` (줄 159): 
- `get_digest(self, channel_id)` (줄 162): digest.md를 로드. 없으면 None.
- `save_digest(self, channel_id, content, meta)` (줄 181): digest.md를 저장
- `_read_jsonl(path)` (줄 195): JSONL 파일을 읽어 리스트로 반환
