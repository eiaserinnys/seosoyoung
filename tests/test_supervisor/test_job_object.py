"""Job Object 단위 테스트"""

import os
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from supervisor import job_object


@pytest.fixture(autouse=True)
def _reset_job_handle():
    """각 테스트 전후로 모듈 싱글턴 초기화"""
    old = job_object._job_handle
    job_object._job_handle = None
    yield
    # 테스트 중 생성된 핸들 닫기
    if job_object._job_handle is not None and os.name == "nt":
        job_object.close_job_object()
    job_object._job_handle = old


class TestNonWindows:
    """Non-Windows 환경에서의 no-op 동작"""

    @patch.object(job_object, "_is_windows", return_value=False)
    def test_create_noop(self, mock_win):
        job_object.create_job_object()
        assert job_object._job_handle is None

    @patch.object(job_object, "_is_windows", return_value=False)
    def test_assign_noop(self, mock_win):
        proc = MagicMock()
        assert job_object.assign_process(proc) is False

    @patch.object(job_object, "_is_windows", return_value=False)
    def test_close_noop(self, mock_win):
        job_object.close_job_object()  # 에러 없이 반환


@pytest.mark.skipif(os.name != "nt", reason="Windows 전용")
class TestWindowsJobObject:
    """Windows에서의 실제 Job Object 테스트"""

    def test_create_job_object(self):
        job_object.create_job_object()
        assert job_object._job_handle is not None
        assert job_object._job_handle != 0

    def test_create_idempotent(self):
        job_object.create_job_object()
        first_handle = job_object._job_handle
        job_object.create_job_object()
        assert job_object._job_handle is first_handle

    def test_assign_process(self):
        job_object.create_job_object()

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            result = job_object.assign_process(proc)
            assert result is True
        finally:
            proc.kill()
            proc.wait()

    def test_assign_without_job(self):
        """Job Object 미생성 시 False 반환"""
        proc = MagicMock()
        assert job_object.assign_process(proc) is False

    def test_close_job_object(self):
        job_object.create_job_object()
        assert job_object._job_handle is not None
        job_object.close_job_object()
        assert job_object._job_handle is None

    def test_close_idempotent(self):
        job_object.close_job_object()  # 핸들 없어도 에러 없음

    def test_kill_on_job_close(self):
        """Job Object 핸들을 닫으면 자식 프로세스가 종료되는지 검증"""
        job_object.create_job_object()

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        job_object.assign_process(proc)

        # 프로세스가 실행 중인지 확인
        assert proc.poll() is None

        # Job Object 닫기 → 자식 프로세스 자동 종료
        job_object.close_job_object()

        # 프로세스가 종료될 때까지 대기 (최대 5초)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Job Object 닫기 후 5초 내 프로세스가 종료되지 않음")

        assert proc.poll() is not None
