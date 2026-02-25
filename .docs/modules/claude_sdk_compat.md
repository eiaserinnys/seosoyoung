# claude/sdk_compat.py

> 경로: `seosoyoung/slackbot/claude/sdk_compat.py`

## 개요

SDK 메시지 파싱 에러 호환 레이어

MessageParseError를 forward-compatible하게 분류하는 공통 유틸.
Agent SDK 전환 후에는 SDK 내부에서 None skip이 처리되므로
except MessageParseError 블록이 거의 트리거되지 않지만,
방어적 폴백으로 유지한다.

## 클래스

### `ParseAction` (Enum)
- 위치: 줄 16
- 설명: MessageParseError 처리 결과

## 함수

### `classify_parse_error(data)`
- 위치: 줄 22
- 설명: MessageParseError의 data를 분류하여 처리 액션을 반환.

Args:
    data: MessageParseError.data (dict 또는 None)
    log_fn: 로거 (None이면 모듈 로거 사용)

Returns:
    (action, msg_type): action은 CONTINUE/RAISE, msg_type은 분류된 메시지 타입
