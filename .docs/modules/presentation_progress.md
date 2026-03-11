# presentation/progress.py

> 경로: `seosoyoung/slackbot/presentation/progress.py`

## 개요

진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 이벤트 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 집합을 반환합니다.

## 함수

### `post_initial_placeholder(client, channel, thread_ts)`
- 위치: 줄 28
- 설명: 초기 placeholder 메시지를 게시하고 ts를 반환

실패 시 None을 반환합니다. 호출자는 이 ts를 build_event_callbacks의
initial_placeholder_ts 파라미터로 전달합니다.

### `_event_delete_delay()`
- 위치: 줄 46
- 설명: 이벤트 메시지 삭제 전 대기 시간 (초) — 호출 시점에 환경변수를 읽음

### `_thinking_delete_delay()`
- 위치: 줄 51
- 설명: thinking 메시지 삭제 전 대기 시간 (초) — 호출 시점에 환경변수를 읽음

### `build_event_callbacks(pctx, node_map, mode, initial_placeholder_ts, initial_board)`
- 위치: 줄 56
- 설명: 세분화 이벤트 콜백 + on_compact 팩토리

Args:
    pctx: 프레젠테이션 컨텍스트
    node_map: 이벤트-메시지 매핑
    mode: "clean" = 일반 채널(갱신 모드, 완료 후 삭제),
          "keep" = DM 채널(풀 덤프 모드, 완료 후 유지)
    initial_placeholder_ts: 초기 placeholder 메시지의 ts (cleanup()에서 삭제)
    initial_board: ActivityBoard 인스턴스 (clean 모드에서 B placeholder 관리용)

Returns:
    {
        "on_thinking": ...,
        "on_text_start": ...,
        "on_text_delta": ...,
        "on_text_end": ...,
        "on_tool_start": ...,
        "on_tool_result": ...,
        "on_compact": ...,
        "cleanup": ...,
    }

## 내부 의존성

- `seosoyoung.slackbot.formatting.build_input_request_blocks`
- `seosoyoung.slackbot.formatting.format_initial_placeholder`
- `seosoyoung.slackbot.formatting.format_thinking_complete`
- `seosoyoung.slackbot.formatting.format_thinking_initial`
- `seosoyoung.slackbot.formatting.format_thinking_text`
- `seosoyoung.slackbot.formatting.format_tool_initial`
- `seosoyoung.slackbot.formatting.format_tool_result`
- `seosoyoung.slackbot.presentation.activity_board.ActivityBoard`
- `seosoyoung.slackbot.presentation.node_map.SlackNodeMap`
- `seosoyoung.slackbot.presentation.redact.redact_sensitive`
- `seosoyoung.slackbot.presentation.types.PresentationContext`
- `seosoyoung.slackbot.slack.formatting.update_message`
