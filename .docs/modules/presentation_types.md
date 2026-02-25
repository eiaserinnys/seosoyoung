# presentation/types.py

> 경로: `seosoyoung/slackbot/presentation/types.py`

## 개요

프레젠테이션 컨텍스트 타입 정의

claude/ 모듈 밖에 위치하여 엔진 독립성을 유지합니다.
executor에 전달되는 opaque 객체로, 콜백과 ResultProcessor가 사용합니다.

## 클래스

### `PresentationContext`
- 위치: 줄 12
- 설명: 프레젠테이션 레이어가 관리하는 실행 컨텍스트

claude/ 밖에 위치하여 엔진 패키지의 Slack 의존성을 제거합니다.
콜백 팩토리와 ResultProcessor가 이 객체의 필드를 읽고 갱신합니다.
