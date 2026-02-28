# rescue/shutdown.py

> 경로: `seosoyoung/rescue/shutdown.py`

## 개요

경량 HTTP Shutdown 서버

supervisor에서 POST /shutdown 요청을 받아 프로세스를 graceful하게 종료합니다.

## 클래스

### `_ShutdownHandler` (BaseHTTPRequestHandler)
- 위치: 줄 14

#### 메서드

- `do_POST(self)` (줄 17): 
- `log_message(self, format)` (줄 28): 

## 함수

### `start_shutdown_server(port, callback, host)`
- 위치: 줄 32
- 설명: 셧다운 서버를 데몬 스레드에서 시작. HTTPServer 인스턴스 반환.
