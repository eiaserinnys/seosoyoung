"""보안 레이어

프롬프트 인젝션 방어, 출력 마스킹, 경로 제한 등을 처리합니다.
"""

import re
import logging
from pathlib import Path
from typing import Optional

from seosoyoung.config import Config

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

# 허용된 작업 디렉토리
ALLOWED_PATHS = [
    Path(Config.EB_RENPY_PATH),
]

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
            for allowed in ALLOWED_PATHS:
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
