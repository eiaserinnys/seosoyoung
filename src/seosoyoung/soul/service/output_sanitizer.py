"""
출력 민감 정보 마스킹 모듈

Claude Code 출력에서 API 키, 토큰 등 민감 정보를 마스킹합니다.
"""

import re
from typing import List, Tuple


# 민감 정보 패턴 목록 (pattern, replacement)
SENSITIVE_PATTERNS: List[Tuple[str, str]] = [
    # Anthropic API keys
    (r'sk-[a-zA-Z0-9-_]{20,}', 'sk-***REDACTED***'),
    (r'sk-ant-[a-zA-Z0-9-_]+', 'sk-ant-***REDACTED***'),
    # GitHub tokens
    (r'ghp_[a-zA-Z0-9]{30,}', 'ghp_***REDACTED***'),
    (r'gho_[a-zA-Z0-9]{30,}', 'gho_***REDACTED***'),
    (r'github_pat_[a-zA-Z0-9_]{20,}', 'github_pat_***REDACTED***'),
    # Slack tokens
    (r'xoxb-[a-zA-Z0-9-]+', 'xoxb-***REDACTED***'),
    (r'xoxp-[a-zA-Z0-9-]+', 'xoxp-***REDACTED***'),
    # Environment variables with sensitive names
    (r'DISCORD_[A-Z_]*=\S+', 'DISCORD_***=REDACTED'),
    (r'[a-zA-Z_]*PASSWORD[a-zA-Z_]*=\S+', '***PASSWORD***=REDACTED'),
    (r'[a-zA-Z_]*SECRET[a-zA-Z_]*=\S+', '***SECRET***=REDACTED'),
    (r'[a-zA-Z_]*TOKEN[a-zA-Z_]*=\S+', '***TOKEN***=REDACTED'),
    (r'[a-zA-Z_]*KEY[a-zA-Z_]*=\S+', '***KEY***=REDACTED'),
]


def sanitize_output(text: str) -> str:
    """
    출력에서 민감 정보를 마스킹합니다.

    Args:
        text: 마스킹할 텍스트

    Returns:
        민감 정보가 마스킹된 텍스트
    """
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result
