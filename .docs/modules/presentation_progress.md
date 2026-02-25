# presentation/progress.py

> 경로: `seosoyoung/slackbot/presentation/progress.py`

## 개요

진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 on_progress/on_compact 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 쌍을 반환합니다.

## 함수

### `build_progress_callbacks(pctx, update_message_fn)`
- 위치: 줄 25
- 설명: PresentationContext를 캡처하는 on_progress/on_compact 클로저 쌍을 생성

Args:
    pctx: 프레젠테이션 컨텍스트 (mutable - 콜백이 ts 필드를 갱신)
    update_message_fn: (client, channel, ts, text, *, blocks=None) -> None

Returns:
    (on_progress, on_compact) 콜백 튜플

## 내부 의존성

- `seosoyoung.slackbot.claude.message_formatter.format_as_blockquote`
- `seosoyoung.slackbot.claude.message_formatter.format_dm_progress`
- `seosoyoung.slackbot.claude.message_formatter.format_trello_progress`
- `seosoyoung.slackbot.claude.message_formatter.truncate_progress_text`
- `seosoyoung.slackbot.presentation.types.PresentationContext`
