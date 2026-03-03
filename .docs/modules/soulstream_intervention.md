# soulstream/intervention.py

> 경로: `seosoyoung/slackbot/soulstream/intervention.py`

## 개요

인터벤션(Intervention) 관리

실행 중인 스레드에 새 메시지가 도착했을 때의 처리를 담당합니다.
- PendingPrompt 저장/조회
- interrupt 전송 (agent_session_id 기반)

per-session 아키텍처: agent_session_id가 유일한 식별자.

## 클래스

### `PendingPrompt`
- 위치: 줄 19
- 설명: 인터벤션 대기 중인 프롬프트 정보

콜백 + opaque 컨텍스트만 저장합니다.
Slack 필드(channel, say, client 등)는 presentation 컨텍스트에 포함됩니다.

### `InterventionManager`
- 위치: 줄 36
- 설명: 인터벤션 관리자

실행 중인 스레드에 새 메시지가 도착하면:
1. pending에 프롬프트 저장 (최신 것으로 덮어씀)
2. 현재 실행 중인 세션에 agent_session_id 기반 intervene 전송

#### 메서드

- `__init__(self)` (줄 44): 
- `save_pending(self, thread_ts, pending)` (줄 48): pending 프롬프트 저장 (최신 것으로 덮어씀)
- `pop_pending(self, thread_ts)` (줄 53): pending 프롬프트를 꺼내고 제거
- `pending_prompts(self)` (줄 59): pending_prompts dict 직접 접근 (테스트용)
- `fire_interrupt_remote(self, thread_ts, prompt, service_adapter)` (줄 63): Remote 모드: Soulstream에 HTTP intervene 요청 (agent_session_id 기반)
