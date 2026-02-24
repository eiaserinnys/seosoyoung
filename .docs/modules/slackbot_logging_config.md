# slackbot/logging_config.py

> 경로: `seosoyoung/slackbot/logging_config.py`

## 개요

로깅 설정 모듈

로깅 레벨 가이드라인
==================

본 프로젝트에서 로깅 레벨을 선택할 때 다음 기준을 따릅니다.

logger.exception()
    - 예외 처리 블록에서 스택 트레이스가 필요한 경우
    - 예상치 못한 오류로 디버깅에 스택 트레이스가 도움이 될 때
    - 예: Claude 실행 오류, 워처 폴링 오류

logger.error()
    - 예상된 오류이거나 스택 트레이스가 불필요한 경우
    - 외부 서비스(Slack, Trello) 호출 실패
    - 파일 로드/저장 실패 등 복구 가능한 오류
    - 예: "추적 상태 로드 실패: {e}", "알림 전송 실패: {e}"
    - 참고: `logger.error(..., exc_info=True)`는 `logger.exception()`과 동등

logger.warning()
    - 복구 가능한 경고 상황
    - 기능에 영향은 적지만 주의가 필요한 상황
    - 설정 누락, 선택적 기능 비활성화
    - 예: "API가 설정되지 않아 워처를 시작하지 않습니다"

logger.info()
    - 주요 상태 변경, 작업 시작/완료
    - 정상 동작 흐름의 중요 이벤트
    - 예: "세션 생성", "Claude 실행 완료"

logger.debug()
    - 상세한 디버깅 정보
    - 개발/문제 해결 시에만 필요한 정보
    - 예: 폴링 상태, 락 획득/해제

## 함수

### `setup_logging()`
- 위치: 줄 44
- 설명: 로깅 설정 및 로거 반환

## 내부 의존성

- `seosoyoung.config.Config`
