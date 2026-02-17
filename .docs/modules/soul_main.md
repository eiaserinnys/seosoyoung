# soul/main.py

> 경로: `seosoyoung/mcp/soul/main.py`

## 개요

Seosoyoung Soul - FastAPI Application

슬랙 봇에서 REST API로 호출하는 Claude Code 실행 서비스.
멀티 클라이언트 지원 구조.

## 함수

### `async periodic_cleanup()`
- 위치: 줄 37
- 설명: 주기적 태스크 정리 (24시간 이상 된 완료 태스크)

### `async lifespan(app)`
- 위치: 줄 53
- 데코레이터: asynccontextmanager
- 설명: 애플리케이션 라이프사이클 관리

### `async health_check()`
- 위치: 줄 137
- 데코레이터: app.get
- 설명: 헬스 체크 엔드포인트

### `async get_status()`
- 위치: 줄 148
- 데코레이터: app.get
- 설명: 서비스 상태 조회

### `async global_exception_handler(request, exc)`
- 위치: 줄 180
- 데코레이터: app.exception_handler
- 설명: 전역 예외 핸들러

## 내부 의존성

- `seosoyoung.mcp.soul.api.attachments_router`
- `seosoyoung.mcp.soul.api.tasks.router`
- `seosoyoung.mcp.soul.config.get_settings`
- `seosoyoung.mcp.soul.config.setup_logging`
- `seosoyoung.mcp.soul.models.HealthResponse`
- `seosoyoung.mcp.soul.service.file_manager`
- `seosoyoung.mcp.soul.service.resource_manager`
- `seosoyoung.mcp.soul.service.task_manager.get_task_manager`
- `seosoyoung.mcp.soul.service.task_manager.init_task_manager`
