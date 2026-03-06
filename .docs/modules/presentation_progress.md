# presentation/progress.py

> 경로: `seosoyoung/slackbot/presentation/progress.py`

## 개요

진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 on_progress/on_compact 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 쌍을 반환합니다.

## 함수

### `build_progress_callbacks(pctx, update_message_fn)`
- 위치: 줄 35
- 설명: PresentationContext를 캡처하는 on_progress/on_compact 클로저 쌍을 생성

Args:
    pctx: 프레젠테이션 컨텍스트 (mutable - 콜백이 ts 필드를 갱신)
    update_message_fn: (client, channel, ts, text, *, blocks=None) -> None

Returns:
    (on_progress, on_compact) 콜백 튜플

### `build_event_callbacks(pctx, node_map, mode)`
- 위치: 줄 161
- 설명: 세분화 이벤트 콜백 + on_compact 팩토리 (build_progress_callbacks 대체)

Args:
    pctx: 프레젠테이션 컨텍스트
    node_map: 이벤트-메시지 매핑
    mode: "clean" (삭제) 또는 "keep" (유지)

Returns:
    {
        "on_thinking": ...,
        "on_text_start": ...,
        "on_text_delta": ...,
        "on_text_end": ...,
        "on_tool_start": ...,
        "on_tool_result": ...,
        "on_compact": ...,
    }

## 내부 의존성

- `seosoyoung.slackbot.formatting.format_as_blockquote`
- `seosoyoung.slackbot.formatting.format_dm_progress`
- `seosoyoung.slackbot.formatting.format_thinking_initial`
- `seosoyoung.slackbot.formatting.format_thinking_text`
- `seosoyoung.slackbot.formatting.format_tool_complete`
- `seosoyoung.slackbot.formatting.format_tool_error`
- `seosoyoung.slackbot.formatting.format_tool_initial`
- `seosoyoung.slackbot.formatting.format_trello_progress`
- `seosoyoung.slackbot.formatting.truncate_progress_text`
- `seosoyoung.slackbot.presentation.node_map.SlackNodeMap`
- `seosoyoung.slackbot.presentation.types.PresentationContext`
