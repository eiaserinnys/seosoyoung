"""
세션 검증 모듈

Claude Code 세션의 유효성을 검증하고 세션 파일을 찾습니다.
"""

import re
from pathlib import Path
from typing import Optional


# 세션 에러 코드
SESSION_NOT_FOUND_CODE = "SESSION_NOT_FOUND"


def find_session_file(session_id: str) -> Optional[Path]:
    """세션 파일을 찾습니다."""
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    session_file_name = f"{session_id}.jsonl"
    for project_dir in claude_dir.iterdir():
        if project_dir.is_dir():
            session_file = project_dir / session_file_name
            if session_file.exists():
                return session_file

    return None


def validate_session(session_id: str) -> Optional[str]:
    """세션 ID가 유효한지 검증합니다."""
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )

    if not uuid_pattern.match(session_id):
        return f"유효하지 않은 세션 ID 형식입니다: {session_id}"

    session_file = find_session_file(session_id)
    if session_file is None:
        return f"세션을 찾을 수 없습니다: {session_id}"

    return None
