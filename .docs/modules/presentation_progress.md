# presentation/progress.py

> 경로: `seosoyoung/slackbot/presentation/progress.py`

## 개요

진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 on_progress/on_compact 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 쌍을 반환합니다.

## 함수

### `post_initial_placeholder(client, channel, thread_ts)`
- 위치: 줄 37
- 설명: 초기 placeholder 메시지를 게시하고 ts를 반환

실패 시 None을 반환합니다. 호출자는 이 ts를 build_event_callbacks의
initial_placeholder_ts 파라미터로 전달합니다.

### `_event_delete_delay()`
- 위치: 줄 55
- 설명: 이벤트 메시지 삭제 전 대기 시간 (초) — 호출 시점에 환경변수를 읽음

### `build_progress_callbacks(pctx, update_message_fn)`
- 위치: 줄 60
- 설명: PresentationContext를 캡처하는 on_progress/on_compact 클로저 쌍을 생성

Args:
    pctx: 프레젠테이션 컨텍스트 (mutable - 콜백이 ts 필드를 갱신)
    update_message_fn: (client, channel, ts, text, *, blocks=None) -> None

Returns:
    (on_progress, on_compact) 콜백 튜플

### `build_event_callbacks(pctx, node_map, mode, initial_placeholder_ts)`
- 위치: 줄 193
- 설명: 세분화 이벤트 콜백 + on_compact 팩토리 (build_progress_callbacks 대체)

Args:
    pctx: 프레젠테이션 컨텍스트
    node_map: 이벤트-메시지 매핑
    mode: "clean" = 일반 채널(갱신 모드, 완료 후 삭제),
          "keep" = DM 채널(풀 덤프 모드, 완료 후 유지)
    initial_placeholder_ts: 초기 placeholder 메시지의 ts (있으면 첫 이벤트에서 삭제)

Returns:
    {
        "on_progress": ...,
        "on_thinking": ...,
        "on_text_start": ...,
        "on_text_delta": ...,
        "on_text_end": ...,
        "on_tool_start": ...,
        "on_tool_result": ...,
        "on_compact": ...,
        "_cleanup_progress": ...,
    }

## 내부 의존성

- `seosoyoung.slackbot.formatting.format_as_blockquote`
- `seosoyoung.slackbot.formatting.format_dm_progress`
- `seosoyoung.slackbot.formatting.format_initial_placeholder`
- `seosoyoung.slackbot.formatting.format_thinking_complete`
- `seosoyoung.slackbot.formatting.format_thinking_initial`
- `seosoyoung.slackbot.formatting.format_thinking_text`
- `seosoyoung.slackbot.formatting.format_tool_initial`
- `seosoyoung.slackbot.formatting.format_tool_result`
- `seosoyoung.slackbot.formatting.format_trello_progress`
- `seosoyoung.slackbot.formatting.truncate_progress_text`
- `seosoyoung.slackbot.presentation.node_map.SlackNodeMap`
- `seosoyoung.slackbot.presentation.types.PresentationContext`
