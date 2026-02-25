"""응용 마커 파서

Claude Code 출력에서 응용 마커(UPDATE, RESTART, LIST_RUN)를 파싱합니다.
claude/ 엔진 패키지 밖에 위치하여, 엔진 독립성을 유지합니다.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedMarkers:
    """파싱된 응용 마커"""

    update_requested: bool = False
    restart_requested: bool = False
    list_run: Optional[str] = None


def parse_markers(output: str) -> ParsedMarkers:
    """출력 텍스트에서 응용 마커를 파싱합니다.

    Args:
        output: Claude Code 실행 결과 텍스트

    Returns:
        파싱된 마커 정보
    """
    update_requested = "<!-- UPDATE -->" in output
    restart_requested = "<!-- RESTART -->" in output

    list_run_match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
    list_run = list_run_match.group(1).strip() if list_run_match else None

    return ParsedMarkers(
        update_requested=update_requested,
        restart_requested=restart_requested,
        list_run=list_run,
    )
