"""경량 HTTP Shutdown 서버

supervisor에서 POST /shutdown 요청을 받아 프로세스를 graceful하게 종료합니다.
"""

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable

logger = logging.getLogger(__name__)


class _ShutdownHandler(BaseHTTPRequestHandler):
    shutdown_callback: Callable[[], None]

    def do_POST(self):
        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"shutting down")
            # 응답 전송 후 콜백 실행 (별도 스레드에서 지연 실행)
            threading.Timer(0.1, self.shutdown_callback).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # HTTP 요청 로그 억제


def start_shutdown_server(
    port: int,
    callback: Callable[[], None],
    host: str = "127.0.0.1",
) -> HTTPServer:
    """셧다운 서버를 데몬 스레드에서 시작. HTTPServer 인스턴스 반환."""
    handler_class = type(
        "_Handler",
        (_ShutdownHandler,),
        {"shutdown_callback": staticmethod(callback)},
    )
    server = HTTPServer((host, port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Shutdown server started on %s:%d", host, port)
    return server
