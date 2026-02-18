# rescue/session.py

> 경로: `seosoyoung/rescue/session.py`

## 개요

rescue-bot 세션 관리 (경량 in-memory 버전)

메인 봇의 SessionManager에서 파일 저장, 역할 관리 등을 제외한 경량 버전입니다.
스레드 ts → 세션 정보를 in-memory dict로 관리합니다.

## 클래스

### `Session`
- 위치: 줄 14
- 설명: 세션 정보

#### 메서드

- `__post_init__(self)` (줄 22): 

### `SessionManager`
- 위치: 줄 27
- 설명: 경량 세션 매니저 (in-memory)

#### 메서드

- `__init__(self)` (줄 30): 
- `get(self, thread_ts)` (줄 34): 스레드 ID로 세션 조회
- `create(self, thread_ts, channel_id)` (줄 39): 새 세션 생성
- `get_or_create(self, thread_ts, channel_id)` (줄 46): 세션 조회, 없으면 생성
- `update_session_id(self, thread_ts, session_id)` (줄 53): Claude Code 세션 ID 업데이트
- `increment_message_count(self, thread_ts)` (줄 60): 메시지 카운트 증가
- `count(self)` (줄 67): 세션 수
