"""Graceful shutdown 관련 테스트

ShutdownServer, _kill_process_tree, stop() graceful/fallback 동작 검증.
"""

import os
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

import psutil
import pytest

from supervisor.models import ProcessConfig, ProcessStatus, RestartPolicy
from supervisor.process_manager import ProcessManager

# seosoyoung 패키지 경로 추가 (shutdown.py 위치)
_SEOSOYOUNG_SRC = str((Path(__file__).parent.parent.parent / "src").resolve())
if _SEOSOYOUNG_SRC not in sys.path:
    sys.path.insert(0, _SEOSOYOUNG_SRC)

from seosoyoung.slackbot.shutdown import start_shutdown_server  # noqa: E402


@pytest.fixture
def pm():
    return ProcessManager()


class TestShutdownServer:
    """ShutdownServer 단위 테스트"""

    def test_start_and_callback(self):
        """서버 시작 → POST /shutdown → 콜백 호출"""
        import threading

        called = threading.Event()

        def on_shutdown():
            called.set()

        server = start_shutdown_server(0, on_shutdown)
        port = server.server_address[1]

        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/shutdown",
                method="POST",
                data=b"",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            assert resp.status == 200

            # 콜백은 0.1초 후 실행
            assert called.wait(timeout=2), "콜백이 호출되지 않음"
        finally:
            server.shutdown()

    def test_404_on_wrong_path(self):
        """잘못된 경로에는 404 반환"""
        server = start_shutdown_server(0, lambda: None)
        port = server.server_address[1]

        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/wrong",
                method="POST",
                data=b"",
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req, timeout=3)
            assert exc_info.value.code == 404
        finally:
            server.shutdown()


class TestKillProcessTree:
    """_kill_process_tree 테스트"""

    def test_kills_parent_and_children(self, pm, tmp_path):
        """부모 프로세스와 자식을 모두 종료"""
        # 자식 프로세스를 생성하는 부모 프로세스 실행
        script = (
            "import subprocess, sys, time; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "time.sleep(60)"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=str(tmp_path),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        # 자식이 생성될 때까지 대기
        time.sleep(1)

        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        assert len(children) > 0, "자식 프로세스가 생성되지 않음"

        # 트리 킬
        pm._kill_process_tree(proc.pid)
        time.sleep(0.5)

        # 부모 종료 확인
        assert proc.poll() is not None

        # 자식 종료 확인
        for child in children:
            assert not child.is_running()

    def test_no_error_on_nonexistent_pid(self, pm):
        """존재하지 않는 PID에 대해 에러 없이 처리"""
        pm._kill_process_tree(999999)  # NoSuchProcess 예외 무시


class TestGracefulShutdownRequest:
    """_request_graceful_shutdown 테스트"""

    def test_successful_request(self, pm):
        """실행 중인 HTTP 서버에 요청 성공"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            result = pm._request_graceful_shutdown(
                f"http://127.0.0.1:{port}/shutdown"
            )
            assert result is True
        finally:
            server.shutdown()

    def test_failed_request_no_server(self, pm):
        """서버가 없으면 False 반환 (예외 발생 안 함)"""
        result = pm._request_graceful_shutdown(
            "http://127.0.0.1:59999/shutdown", timeout=1.0
        )
        assert result is False


class TestStopGraceful:
    """stop() 메서드의 graceful shutdown 흐름 테스트"""

    def test_stop_without_shutdown_url_uses_tree_kill(self, pm, tmp_path):
        """shutdown_url 없으면 프로세스 트리 킬 사용"""
        cfg = ProcessConfig(
            name="no-url",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
            cwd=str(tmp_path),
        )
        pm.register(cfg)
        pm.start("no-url")
        assert pm.is_running("no-url")

        exit_code = pm.stop("no-url")
        assert not pm.is_running("no-url")
        assert exit_code is not None

    def test_stop_with_shutdown_url_graceful(self, pm, tmp_path):
        """shutdown_url이 있고 프로세스가 정상 종료하는 경우"""
        # HTTP 서버를 내장한 프로세스 실행
        script = (
            "import threading, os\n"
            "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_POST(self):\n"
            "        self.send_response(200)\n"
            "        self.end_headers()\n"
            "        threading.Timer(0.1, lambda: os._exit(0)).start()\n"
            "    def log_message(self, *a): pass\n"
            "s = HTTPServer(('127.0.0.1', 0), H)\n"
            "port = s.server_address[1]\n"
            "# 포트를 파일에 기록\n"
            "import sys\n"
            f"with open(r'{tmp_path / 'port.txt'}', 'w') as f:\n"
            "    f.write(str(port))\n"
            "s.serve_forever()\n"
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            cwd=str(tmp_path),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        # 프로세스가 포트 파일을 생성할 때까지 대기
        port_file = tmp_path / "port.txt"
        for _ in range(30):
            if port_file.exists():
                port = int(port_file.read_text().strip())
                break
            time.sleep(0.1)
        else:
            proc.kill()
            pytest.fail("프로세스가 포트 파일을 생성하지 않음")

        # ProcessManager에 등록 (이미 실행 중인 프로세스를 직접 주입)
        cfg = ProcessConfig(
            name="graceful-test",
            command=sys.executable,
            args=[],
            cwd=str(tmp_path),
            shutdown_url=f"http://127.0.0.1:{port}/shutdown",
        )
        pm.register(cfg)
        pm._procs["graceful-test"] = proc
        state = pm._states["graceful-test"]
        state.pid = proc.pid
        state.status = ProcessStatus.RUNNING

        exit_code = pm.stop("graceful-test")
        assert exit_code == 0  # graceful 종료 성공

    def test_stop_with_shutdown_url_fallback(self, pm, tmp_path):
        """shutdown_url 요청 실패 시 트리 킬로 폴백"""
        cfg = ProcessConfig(
            name="fallback-test",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
            cwd=str(tmp_path),
            # 존재하지 않는 포트로 요청 → 실패
            shutdown_url="http://127.0.0.1:59998/shutdown",
        )
        pm.register(cfg)
        pm.start("fallback-test")
        assert pm.is_running("fallback-test")

        exit_code = pm.stop("fallback-test")
        assert not pm.is_running("fallback-test")
        assert exit_code is not None
