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

- `__post_init__(self)` (줄 33): 

### `SessionManager`
- 위치: 줄 41
- 설명: 세션 매니저

스레드 ID를 키로 세션 정보를 관리합니다.
세션 정보는 sessions/ 폴더에 JSON 파일로 저장됩니다.

#### 메서드

- `__init__(self, session_dir)` (줄 48): 
- `_get_session_file(self, thread_ts)` (줄 53): 세션 파일 경로 반환
- `get(self, thread_ts)` (줄 59): 스레드 ID로 세션 조회
- `create(self, thread_ts, channel_id, user_id, username, role)` (줄 78): 새 세션 생성
- `update_session_id(self, thread_ts, session_id)` (줄 99): Claude Code 세션 ID 업데이트
- `update_thread_ts(self, old_thread_ts, new_thread_ts)` (줄 109): 세션의 thread_ts 변경 (멘션 응답 시 사용)
- `increment_message_count(self, thread_ts)` (줄 145): 메시지 카운트 증가
- `_save(self, session)` (줄 154): 세션을 파일에 저장
- `exists(self, thread_ts)` (줄 165): 세션 존재 여부 확인
- `list_active(self)` (줄 169): 모든 활성 세션 목록
- `count(self)` (줄 180): 활성 세션 수

### `SessionRuntime`
- 위치: 줄 185
- 설명: 세션 실행 상태 관리자

세션 락(동시 실행 방지)과 실행 상태 추적을 담당합니다.

#### 메서드

- `__init__(self, on_all_sessions_stopped)` (줄 191): Args:
- `get_session_lock(self, thread_ts)` (줄 208): 스레드별 락 반환 (없으면 생성)
- `mark_session_running(self, thread_ts)` (줄 215): 세션을 실행 중으로 표시
- `mark_session_stopped(self, thread_ts)` (줄 221): 세션 실행 종료 표시
- `get_running_session_count(self)` (줄 234): 현재 실행 중인 세션 수 반환
- `set_on_all_sessions_stopped(self, callback)` (줄 239): 세션 종료 콜백 설정 (초기화 후 설정 가능)

## 내부 의존성

- `seosoyoung.config.Config`
