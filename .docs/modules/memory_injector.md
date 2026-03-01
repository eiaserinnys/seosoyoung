# memory/injector.py

> 경로: `seosoyoung/slackbot/plugins/memory/injector.py`

## 개요

OM(Observational Memory) 주입 및 관찰 트리거 로직

agent_runner.py에서 분리된 메모리 주입 전용 모듈.
ClaudeRunner가 이 모듈의 함수를 호출하여 OM 기능을 사용합니다.

## 함수

### `prepare_memory_injection(thread_ts, channel, session_id, prompt)`
- 위치: 줄 15
- 설명: OM 메모리 주입을 준비합니다.

장기 기억, 세션 관찰, 채널 관찰 등을 수집하여
첫 번째 query 메시지에 프리픽스로 주입할 프롬프트를 생성합니다.

Args:
    thread_ts: 스레드 타임스탬프
    channel: 채널 ID
    session_id: 세션 ID (None이면 새 세션)
    prompt: 사용자 프롬프트 (앵커 미리보기용)

Returns:
    (memory_prompt, anchor_ts) 튜플

### `create_or_load_debug_anchor(thread_ts, session_id, store, prompt, debug_channel)`
- 위치: 줄 101
- 설명: 디버그 앵커 메시지를 생성하거나 기존 앵커를 로드합니다.

새 세션이면 앵커 메시지를 생성하고 MemoryRecord에 저장합니다.
기존 세션이면 MemoryRecord에서 저장된 anchor_ts를 로드합니다.

Args:
    thread_ts: 스레드 타임스탬프
    session_id: 세션 ID (None이면 새 세션)
    store: MemoryStore 인스턴스
    prompt: 사용자 프롬프트 (앵커 미리보기용)
    debug_channel: 디버그 채널 ID

Returns:
    anchor_ts (빈 문자열이면 앵커 없음)

### `send_injection_debug_log(thread_ts, result, debug_channel, anchor_ts)`
- 위치: 줄 157
- 설명: 디버그 이벤트 #7, #8: 주입 정보를 슬랙에 발송

LTM/세션 각각 별도 메시지로 발송하며, 주입 내용을 blockquote로 표시.
anchor_ts가 있으면 해당 스레드에 답글로 발송.
anchor_ts가 비었으면 채널 본문 오염 방지를 위해 스킵.

### `trigger_observation(thread_ts, user_id, prompt, collected_messages, anchor_ts)`
- 위치: 줄 241
- 설명: 관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)

공유 이벤트 루프에서 ClaudeSDKClient가 실행되므로,
별도 스레드에서 새 이벤트 루프를 생성하여 OM 파이프라인을 실행합니다.
