# claude/session.py

> 경로: `seosoyoung/claude/session.py`

## 개요

Claude Code 세션 관리

스레드 ID ↔ 세션 ID 매핑을 관리합니다.
세션 락과 실행 상태 추적도 포함합니다.

## 클래스

### `Session`
- 위치: 줄 21
- 설명: Claude Code 세션 정보

#### 메서드

- `__post_init__(self)` (줄 35): 

### `SessionManager`
- 위치: 줄 43
- 설명: 세션 매니저

스레드 ID를 키로 세션 정보를 관리합니다.
세션 정보는 sessions/ 폴더에 JSON 파일로 저장됩니다.

#### 메서드

- `__init__(self, session_dir)` (줄 50): 
- `_get_session_file(self, thread_ts)` (줄 55): 세션 파일 경로 반환
- `get(self, thread_ts)` (줄 61): 스레드 ID로 세션 조회
- `create(self, thread_ts, channel_id, user_id, username, role, source_type, last_seen_ts)` (줄 80): 새 세션 생성
- `update_session_id(self, thread_ts, session_id)` (줄 105): Claude Code 세션 ID 업데이트
- `update_thread_ts(self, old_thread_ts, new_thread_ts)` (줄 115): 세션의 thread_ts 변경 (멘션 응답 시 사용)
- `update_last_seen_ts(self, thread_ts, last_seen_ts)` (줄 151): 세션의 last_seen_ts 업데이트
- `increment_message_count(self, thread_ts)` (줄 161): 메시지 카운트 증가
- `_save(self, session)` (줄 170): 세션을 파일에 저장
- `exists(self, thread_ts)` (줄 181): 세션 존재 여부 확인
- `list_active(self)` (줄 185): 모든 활성 세션 목록
- `count(self)` (줄 196): 활성 세션 수

### `SessionRuntime`
- 위치: 줄 201
- 설명: 세션 실행 상태 관리자

세션 락(동시 실행 방지)과 실행 상태 추적을 담당합니다.

#### 메서드

- `__init__(self, on_all_sessions_stopped)` (줄 207): Args:
- `get_session_lock(self, thread_ts)` (줄 224): 스레드별 락 반환 (없으면 생성)
- `mark_session_running(self, thread_ts)` (줄 231): 세션을 실행 중으로 표시
- `mark_session_stopped(self, thread_ts)` (줄 237): 세션 실행 종료 표시
- `get_running_session_count(self)` (줄 250): 현재 실행 중인 세션 수 반환
- `set_on_all_sessions_stopped(self, callback)` (줄 255): 세션 종료 콜백 설정 (초기화 후 설정 가능)

## 내부 의존성

- `seosoyoung.config.Config`
