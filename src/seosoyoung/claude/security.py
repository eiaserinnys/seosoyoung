"""보안 레이어

프롬프트 인젝션 방어, 출력 마스킹, 경로 제한 등을 처리합니다.
"""

import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# 프롬프트에서 차단할 패턴들
BLOCKED_PROMPT_PATTERNS = [
    # 환경 변수 / 민감 정보 요청
    r"\.env",
    r"환경\s*변수",
    r"api[_\s-]?key",
    r"secret[_\s-]?key",
    r"token",
    r"credential",
    r"password",
    r"비밀번호",

    # 시스템 명령어 패턴
    r"system\s*prompt",
    r"시스템\s*프롬프트",
    r"ignore\s*(previous|above)",
    r"이전\s*(지시|명령).*무시",

    # 위험한 경로 접근
    r"seosoyoung_runtime",
    r"\.env",
    r"/etc/passwd",
    r"c:\\windows",
]

# 출력에서 마스킹할 패턴들
MASK_PATTERNS = [
    # Slack 토큰
    (r"xoxb-[a-zA-Z0-9\-]+", "[SLACK_BOT_TOKEN]"),
    (r"xapp-[a-zA-Z0-9\-]+", "[SLACK_APP_TOKEN]"),
    (r"xoxp-[a-zA-Z0-9\-]+", "[SLACK_USER_TOKEN]"),

    # Anthropic API 키
    (r"sk-ant-[a-zA-Z0-9\-]+", "[ANTHROPIC_API_KEY]"),

    # 일반적인 API 키 패턴
    (r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9\-_]{20,}['\"]?", "[API_KEY_REDACTED]"),

    # Bearer 토큰
    (r"Bearer\s+[a-zA-Z0-9\-_.]+", "Bearer [TOKEN]"),
]

def get_allowed_paths() -> list[Path]:
    """허용된 작업 디렉토리 (런타임에 평가)"""
    return [Path.cwd()]


# 차단된 경로 패턴
BLOCKED_PATH_PATTERNS = [
    r"seosoyoung_runtime",
    r"\.env$",
    r"\.git/config",
    r"credentials",
]


class SecurityError(Exception):
    """보안 관련 에러"""
    pass


class SecurityChecker:
    """보안 검사기"""

    def __init__(
        self,
        blocked_patterns: Optional[list[str]] = None,
        mask_patterns: Optional[list[tuple[str, str]]] = None,
    ):
        self.blocked_patterns = blocked_patterns or BLOCKED_PROMPT_PATTERNS
        self.mask_patterns = mask_patterns or MASK_PATTERNS

        # 정규식 컴파일
        self._blocked_re = [
            re.compile(p, re.IGNORECASE) for p in self.blocked_patterns
        ]
        self._mask_re = [
            (re.compile(p, re.IGNORECASE), replacement)
            for p, replacement in self.mask_patterns
        ]

    def check_prompt(self, prompt: str) -> tuple[bool, Optional[str]]:
        """프롬프트 검사

        Returns:
            (is_safe, blocked_reason): 안전하면 (True, None), 위험하면 (False, 이유)
        """
        for pattern in self._blocked_re:
            match = pattern.search(prompt)
            if match:
                matched_text = match.group()
                logger.warning(f"차단된 프롬프트 패턴: {matched_text}")
                return False, f"차단된 패턴: {matched_text}"

        return True, None

    def mask_output(self, output: str) -> str:
        """출력에서 민감 정보 마스킹"""
        result = output

        for pattern, replacement in self._mask_re:
            result = pattern.sub(replacement, result)

        return result

    def check_path(self, path: str) -> tuple[bool, Optional[str]]:
        """경로 접근 검사

        Returns:
            (is_allowed, blocked_reason): 허용이면 (True, None), 차단이면 (False, 이유)
        """
        # 차단된 경로 패턴 검사
        for pattern in BLOCKED_PATH_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                logger.warning(f"차단된 경로 접근: {path}")
                return False, f"차단된 경로: {path}"

        # 허용된 디렉토리 내인지 검사
        try:
            target = Path(path).resolve()
            for allowed in get_allowed_paths():
                allowed_resolved = allowed.resolve()
                if target == allowed_resolved or allowed_resolved in target.parents:
                    return True, None
        except Exception:
            pass

        # 기본적으로 eb_renpy 외부 경로는 경고만 (차단은 안 함)
        # Claude Code가 자체적으로 필요한 경로에 접근할 수 있어야 함
        return True, None


def validate_prompt(prompt: str) -> str:
    """프롬프트 검증 및 정제

    Raises:
        SecurityError: 차단된 패턴이 발견된 경우
    """
    checker = SecurityChecker()
    is_safe, reason = checker.check_prompt(prompt)

    if not is_safe:
        raise SecurityError(f"보안 검사 실패: {reason}")

    return prompt


def mask_sensitive_data(output: str) -> str:
    """출력에서 민감 정보 마스킹"""
    checker = SecurityChecker()
    return checker.mask_output(output)


# 첨부 파일 차단 패턴
BLOCKED_ATTACH_PATTERNS = [
    r"\.env$",
    r"\.env\.",
    r"\.git[/\\]",
    r"__pycache__",
    r"node_modules",
    r"\.pyc$",
    r"seosoyoung_runtime",
    r"credentials",
    r"\.key$",
    r"\.pem$",
]

# 첨부 허용 확장자 (화이트리스트)
ALLOWED_ATTACH_EXTENSIONS = {
    # 텍스트/문서
    ".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".tsv",
    # 코드 (읽기 전용 공유)
    ".py", ".js", ".ts", ".html", ".css",
    # 이미지
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    # 기타
    ".pdf", ".log",
}


def validate_attach_path(file_path: str, workspace_root: Path) -> tuple[bool, Optional[str]]:
    """첨부 파일 경로 검증

    Args:
        file_path: 첨부할 파일의 경로
        workspace_root: 허용된 워크스페이스 루트 경로

    Returns:
        (is_valid, error_message): 유효하면 (True, None), 아니면 (False, 에러 메시지)
    """
    try:
        # 절대 경로로 변환 (symlink 해제)
        target = Path(file_path).resolve()
        workspace = workspace_root.resolve()

        # 1. workspace 내부인지 확인
        try:
            target.relative_to(workspace)
        except ValueError:
            return False, f"workspace 외부 경로: {file_path}"

        # 2. 차단 패턴 검사
        path_str = str(target)
        for pattern in BLOCKED_ATTACH_PATTERNS:
            if re.search(pattern, path_str, re.IGNORECASE):
                return False, f"차단된 경로 패턴: {pattern}"

        # 3. 파일 존재 확인
        if not target.exists():
            return False, f"파일이 존재하지 않음: {file_path}"

        if not target.is_file():
            return False, f"파일이 아님: {file_path}"

        # 4. 확장자 확인
        ext = target.suffix.lower()
        if ext not in ALLOWED_ATTACH_EXTENSIONS:
            return False, f"허용되지 않은 확장자: {ext}"

        # 5. 파일 크기 확인 (20MB 제한)
        max_size = 20 * 1024 * 1024  # 20MB
        file_size = target.stat().st_size
        if file_size > max_size:
            return False, f"파일 크기 초과: {file_size / 1024 / 1024:.1f}MB > 20MB"

        return True, None

    except Exception as e:
        logger.error(f"경로 검증 오류: {e}")
        return False, f"검증 오류: {str(e)}"
