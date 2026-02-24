"""
첨부 파일 추출 모듈

Claude Code 출력에서 [ATTACH:path] 패턴을 찾아 첨부 파일을 추출하고
보안 검증을 수행합니다.
"""

import re
from pathlib import Path
from typing import List, Tuple

from seosoyoung.soul.constants import MAX_ATTACHMENT_SIZE, DANGEROUS_EXTENSIONS


class AttachmentExtractor:
    """
    첨부 파일 추출기

    출력 텍스트에서 [ATTACH:path] 패턴을 찾아 안전한 첨부 파일 경로를 추출합니다.
    """

    def __init__(self, workspace_dir: str):
        """
        Args:
            workspace_dir: 허용된 작업 디렉토리 경로
        """
        self._workspace_dir = workspace_dir

    def extract_attachments(self, text: str) -> Tuple[str, List[str]]:
        """
        출력에서 [ATTACH:path] 패턴을 추출합니다.

        Args:
            text: 파싱할 텍스트

        Returns:
            (정리된 텍스트, 첨부 파일 경로 목록) 튜플
        """
        pattern = r'\[ATTACH:([^\]]+)\]'
        attachments = []

        for match in re.finditer(pattern, text):
            path = match.group(1).strip()
            if self.is_safe_attachment_path(path):
                attachments.append(path)

        cleaned = re.sub(pattern, '', text).strip()
        return cleaned, attachments

    def is_safe_attachment_path(self, path: str) -> bool:
        """
        첨부 파일 경로가 안전한지 검증합니다.

        Args:
            path: 검증할 파일 경로

        Returns:
            안전하면 True, 아니면 False
        """
        try:
            resolved = Path(path).resolve()
            resolved_str = str(resolved)

            # 허용된 디렉토리 검사
            allowed = False
            if resolved_str.startswith(self._workspace_dir):
                allowed = True
            if resolved_str.startswith('/tmp/claude-code-'):
                allowed = True

            if not allowed:
                return False

            # 위험한 확장자 검사
            if resolved.suffix.lower() in DANGEROUS_EXTENSIONS:
                return False

            # 파일 존재 여부 검사
            if not resolved.exists():
                return False

            # 디렉토리 여부 검사
            if resolved.is_dir():
                return False

            # 파일 크기 검사
            if resolved.stat().st_size > MAX_ATTACHMENT_SIZE:
                return False

            return True

        except Exception:
            return False
