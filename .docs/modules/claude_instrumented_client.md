# claude/instrumented_client.py

> 경로: `seosoyoung/slackbot/claude/instrumented_client.py`

## 개요

관찰 가능한 Claude SDK 클라이언트

Agent SDK의 ClaudeSDKClient를 서브클래스하여,
SDK가 내부적으로 skip하는 이벤트(rate_limit_event 등)를
raw 스트림 단계에서 가로채어 관찰할 수 있게 한다.

주의: _query는 private 속성이므로 SDK 내부 리팩토링에 취약하다.

## 클래스

### `InstrumentedClaudeClient` (ClaudeSDKClient)
- 위치: 줄 29
- 설명: rate_limit_event 등 SDK가 skip하는 이벤트를 관찰할 수 있는 확장 클라이언트.

사용법:
    client = InstrumentedClaudeClient(
        options=options,
        on_rate_limit=my_rate_limit_handler,
        on_unknown_event=my_unknown_handler,
    )

#### 메서드

- `__init__(self)` (줄 40): 
- `async receive_messages(self)` (줄 51): receive_messages를 오버라이드하여 raw 스트림에서 이벤트를 관찰.
- `_handle_rate_limit(self, data)` (줄 76): rate_limit_event 관찰.
- `_handle_unknown_event(self, msg_type, data)` (줄 84): unknown event 관찰.
