"""supervisor 서비스 cogito Reflector 싱글톤

SupervisorReflector.get_level3()가 managed_processes 필드를 추가하여
자식 프로세스들의 로그 파일 경로를 반환한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cogito import Reflector


class SupervisorReflector(Reflector):
    """supervisor용 Reflector. Level 3에 managed_processes 로그 경로를 추가한다.

    ProcessManager는 순환 임포트를 피하기 위해 생성 시점이 아닌
    set_process_manager()로 늦게 주입한다.
    set_process_manager()가 호출되지 않으면 managed_processes 키는 응답에서 생략된다.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._process_manager: Any = None

    def set_process_manager(self, process_manager: Any) -> None:
        """ProcessManager 주입. dashboard.create_app()에서 mount_cogito() 전에 호출한다."""
        self._process_manager = process_manager

    def get_level3(self) -> dict:
        base = super().get_level3()
        if self._process_manager is not None:
            base["managed_processes"] = self._process_manager.log_paths()
        return base


reflect = SupervisorReflector(
    name="supervisor",
    description="seosoyoung 프로세스 관리자",
    source_root=str(Path(__file__).resolve().parent),
    port=8042,
)
