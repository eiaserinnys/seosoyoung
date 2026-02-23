# utils/async_bridge.py

> 경로: `seosoyoung/utils/async_bridge.py`

## 개요

Async-to-sync 브릿지 유틸리티

동기 컨텍스트(Slack 이벤트 핸들러 등)에서 코루틴을 실행하는 패턴을 캡슐화합니다.

## 함수

### `run_in_new_loop(coro)`
- 위치: 줄 13
- 설명: 별도 스레드에서 새 이벤트 루프로 코루틴을 실행 (블로킹)

각 호출마다 격리된 이벤트 루프를 생성하여
이전 실행의 anyio 잔여물이 영향을 미치지 않도록 합니다.

Args:
    coro: 실행할 코루틴

Returns:
    코루틴 결과

Raises:
    코루틴에서 발생한 예외를 그대로 전파

### `run_async_in_thread(coro)`
- 위치: 줄 46
- 설명: 별도 스레드에서 코루틴을 실행 (fire-and-forget)

예외는 로그로만 기록하고 호출자로 전파하지 않습니다.

Args:
    coro: 실행할 코루틴

Returns:
    시작된 Thread 객체 (테스트 시 join 가능)
