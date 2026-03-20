"""Management 서버 (cogito /reflect + /shutdown)

cogito 리플렉션 엔드포인트와 graceful shutdown 엔드포인트를
FastAPI 앱으로 통합하여 제공한다.
"""

import logging
import threading
from typing import Callable

import uvicorn
from cogito import Reflector
from cogito.endpoint import mount_cogito
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def create_management_app(reflector: Reflector, shutdown_callback: Callable[[], None]) -> FastAPI:
    """cogito /reflect + /shutdown 을 제공하는 FastAPI 앱을 생성한다."""
    app = FastAPI()
    mount_cogito(app, reflector)

    @app.post("/shutdown")
    async def shutdown():
        threading.Timer(0.1, shutdown_callback).start()
        return {"status": "shutting down"}

    return app


def start_management_server(app: FastAPI, port: int, host: str = "127.0.0.1"):
    """FastAPI 앱을 별도 데몬 스레드에서 uvicorn으로 실행한다."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info("Management server started on %s:%d", host, port)
