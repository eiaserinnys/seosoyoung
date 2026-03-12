# soulstream/intervention.py

> 경로: `seosoyoung/slackbot/soulstream/intervention.py`

## 개요

인터벤션(Intervention) 관리

실행 중인 스레드에 새 메시지가 도착했을 때의 처리를 담당합니다.
- Soulstream에 HTTP intervene 요청 전송 (agent_session_id 기반)

per-session 아키텍처: agent_session_id가 유일한 식별자.

## 클래스

### `InterventionManager`
- 위치: 줄 15
- 설명: 인터벤션 관리자

실행 중인 스레드에 새 메시지가 도착하면:
현재 실행 중인 세션에 agent_session_id 기반 intervene 전송

#### 메서드

- `fire_interrupt_remote(self, thread_ts, prompt, service_adapter)` (줄 22): Soulstream에 HTTP intervene 요청 (agent_session_id 기반)
