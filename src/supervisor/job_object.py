"""Windows Job Object를 사용한 자식 프로세스 수명 관리.

supervisor가 종료되면(정상/비정상 모두) Windows 커널이
Job에 소속된 모든 자식 프로세스를 자동으로 종료한다.

Non-Windows 환경에서는 no-op으로 동작.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading

logger = logging.getLogger("supervisor")

_job_handle = None  # 모듈 수준 싱글턴
_lock = threading.Lock()


def _is_windows() -> bool:
    return os.name == "nt"


# Windows API 구조체 및 함수 시그니처 정의
if _is_windows():
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32

    # 함수 시그니처 선언 (64-bit HANDLE 안전하게 처리)
    kernel32.CreateJobObjectW.restype = ctypes.wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [
        ctypes.wintypes.LPVOID,   # LPSECURITY_ATTRIBUTES
        ctypes.wintypes.LPCWSTR,  # lpName
    ]

    kernel32.SetInformationJobObject.restype = ctypes.wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.wintypes.HANDLE,  # hJob
        ctypes.c_int,            # JobObjectInformationClass
        ctypes.c_void_p,         # lpJobObjectInformation
        ctypes.wintypes.DWORD,   # cbJobObjectInformationLength
    ]

    kernel32.AssignProcessToJobObject.restype = ctypes.wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [
        ctypes.wintypes.HANDLE,  # hJob
        ctypes.wintypes.HANDLE,  # hProcess
    ]

    kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),  # ULONG_PTR
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def create_job_object() -> None:
    """KILL_ON_JOB_CLOSE 플래그가 설정된 Job Object를 생성한다.

    이 핸들이 닫히면(프로세스 종료/크래시 포함) 모든 자식이 즉시 종료된다.
    """
    global _job_handle

    if not _is_windows():
        return

    with _lock:
        if _job_handle is not None:
            return  # 이미 생성됨

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            logger.warning(
                "Job Object 생성 실패 (GetLastError=%d)", ctypes.GetLastError()
            )
            return

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation = 9

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        success = kernel32.SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )

        if not success:
            logger.warning(
                "Job Object 설정 실패 (GetLastError=%d)", ctypes.GetLastError()
            )
            kernel32.CloseHandle(handle)
            return

        _job_handle = handle
        logger.info("Job Object 생성 완료 (KILL_ON_JOB_CLOSE)")


def assign_process(proc: subprocess.Popen) -> bool:
    """자식 프로세스를 Job Object에 등록한다.

    Returns:
        True면 등록 성공, False면 실패 (non-Windows 포함).
    """
    if not _is_windows() or _job_handle is None:
        return False

    # subprocess.Popen은 Windows에서 _handle 속성으로 프로세스 핸들을 노출.
    # CPython 구현 세부사항이지만 안정적으로 사용됨 (pywin32 등도 동일 패턴).
    proc_handle = getattr(proc, "_handle", None)
    if proc_handle is None:
        logger.debug("프로세스 핸들을 가져올 수 없음 (pid=%s)", proc.pid)
        return False

    success = kernel32.AssignProcessToJobObject(_job_handle, proc_handle)
    if not success:
        error_code = ctypes.GetLastError()
        logger.debug(
            "Job Object 등록 실패 (pid=%s, GetLastError=%d)",
            proc.pid,
            error_code,
        )
        return False

    return True


def close_job_object() -> None:
    """Job Object 핸들을 명시적으로 닫는다. 멱등(idempotent).

    정상 종료 시 호출. 비정상 종료 시에는 OS가 핸들을 자동으로 닫는다.
    """
    global _job_handle

    if not _is_windows():
        return

    with _lock:
        if _job_handle is None:
            return
        kernel32.CloseHandle(_job_handle)
        _job_handle = None
        logger.info("Job Object 닫힘")
