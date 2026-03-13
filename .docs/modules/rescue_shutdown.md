# rescue/shutdown.py

> 경로: `seosoyoung/rescue/shutdown.py`

## 개요

Management 서버 (cogito /reflect + /shutdown)

cogito 리플렉션 엔드포인트와 supervisor graceful shutdown 엔드포인트를
FastAPI 앱으로 통합하여 제공한다.

## 함수

### `create_management_app(reflector, shutdown_callback)`
- 위치: 줄 19
- 설명: cogito /reflect + /shutdown 을 제공하는 FastAPI 앱을 생성한다.

### `start_management_server(app, port, host)`
- 위치: 줄 32
- 설명: FastAPI 앱을 별도 데몬 스레드에서 uvicorn으로 실행한다.
