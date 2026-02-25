# slackbot/marker_parser.py

> 경로: `seosoyoung/slackbot/marker_parser.py`

## 개요

응용 마커 파서

Claude Code 출력에서 응용 마커(UPDATE, RESTART, LIST_RUN)를 파싱합니다.
claude/ 엔진 패키지 밖에 위치하여, 엔진 독립성을 유지합니다.

## 클래스

### `ParsedMarkers`
- 위치: 줄 13
- 설명: 파싱된 응용 마커

## 함수

### `parse_markers(output)`
- 위치: 줄 21
- 설명: 출력 텍스트에서 응용 마커를 파싱합니다.

Args:
    output: Claude Code 실행 결과 텍스트

Returns:
    파싱된 마커 정보
