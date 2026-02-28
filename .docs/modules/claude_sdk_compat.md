# claude/sdk_compat.py

> 경로: `seosoyoung/rescue/claude/sdk_compat.py`

## 개요

SDK 메시지 파싱 에러 호환 레이어

MessageParseError를 forward-compatible하게 분류하는 공통 유틸.

## 클래스

### `ParseAction` (Enum)
- 위치: 줄 13
- 설명: MessageParseError 처리 결과

## 함수

### `classify_parse_error(data)`
- 위치: 줄 19
- 설명: MessageParseError의 data를 분류하여 처리 액션을 반환.
