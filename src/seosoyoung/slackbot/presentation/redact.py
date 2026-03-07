"""민감 정보 REDACT 유틸리티

tool 결과 텍스트에 포함될 수 있는 API 키, 토큰, 비밀번호 등의
민감 정보를 가림 처리합니다.
"""

import re
from typing import Final

# 마스킹에 사용할 대체 문자열
REDACTED: Final[str] = "[REDACTED]"

# ── 패턴 1: 잘 알려진 토큰 프리픽스 ─────────────────────────────────────────
# sk-... (Anthropic/OpenAI API keys)
# xoxb-... / xoxp-... / xoxs-... / xoxe-... / xoxa-... (Slack tokens)
# ghp_... / gho_... / ghs_... / ghr_... / github_pat_... (GitHub tokens)
# glpat-... (GitLab PAT)
# eyJ... (JWT — Base64url로 시작하는 점 3개짜리 구조)
_KNOWN_PREFIX_PATTERN: Final[re.Pattern] = re.compile(
    r"""
    (?<![a-zA-Z0-9_])   # negative lookbehind: 앞이 식별자 문자가 아님
    (?:
        sk-[a-zA-Z0-9_\-]{20,}           |  # OpenAI / Anthropic
        xox[a-z]-[a-zA-Z0-9\-]{10,}      |  # Slack tokens
        gh[poshrt]_[a-zA-Z0-9_]{10,}     |  # GitHub tokens
        github_pat_[a-zA-Z0-9_]{10,}     |  # GitHub fine-grained PAT
        glpat-[a-zA-Z0-9_\-]{10,}        |  # GitLab PAT
        eyJ[a-zA-Z0-9_\-]{10,}(?:\.[a-zA-Z0-9_\-]+){2}  # JWT
    )
    """,
    re.VERBOSE,
)

# ── 패턴 2: Authorization 헤더 값 ────────────────────────────────────────────
# "Authorization: Bearer <token>" 등
# 그룹 1: "Authorization: " 등 prefix
# 그룹 2: "Bearer"/"Token"/"Basic"/"ApiKey" 스킴 단어
# 그룹 3: 실제 토큰 값
_AUTH_HEADER_PATTERN: Final[re.Pattern] = re.compile(
    r"((?:Authorization|Auth)\s*[:=]\s*['\"]?)"
    r"(Bearer|Token|Basic|ApiKey)\s+"
    r"([a-zA-Z0-9+/=_\-]{8,})",
    re.IGNORECASE,
)

# ── 패턴 3: 환경변수 스타일 KEY=value ────────────────────────────────────────
# 민감 키워드를 포함하는 환경변수 이름의 값 부분을 가림
# 예: API_KEY=sk-abcd, PASSWORD=secret123, SECRET=xyz
# 그룹 1: 키 이름 + = 기호 부분 (대체 시 유지)
# 그룹 2: 선택적 따옴표 (백레퍼런스로 닫기 쌍을 맞추기 위해 캡처)
# 그룹 3: 실제 값 (대체 시 [REDACTED]로 교체)
_SENSITIVE_KEY_PATTERN: Final[re.Pattern] = re.compile(
    r"""
    (?<![a-zA-Z0-9_])   # negative lookbehind
    ([A-Z0-9_]*?        # 선택적 앞부분
    (?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_?KEY|ACCESS_?KEY|AUTH_?KEY|API_?SECRET)
    [A-Z0-9_]*?         # 선택적 뒷부분
    \s*=\s*)            # = 기호  → 그룹 1
    (['"']?)            # 선택적 따옴표 시작 → 그룹 2 (백레퍼런스 \2 용도)
    ([^\s'"\n,;]{8,})   # 값 (8자 이상) → 그룹 3
    \2                  # 따옴표 닫기
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ── 패턴 4: AWS 스타일 키 ─────────────────────────────────────────────────────
# AKIA..., ASIA... (AWS Access Key ID)
_AWS_KEY_PATTERN: Final[re.Pattern] = re.compile(
    r"(?<![a-zA-Z0-9_])"
    r"(?:AKIA|ASIA|AROA|AIDA|ANPA|ANVA|APKA)[A-Z0-9]{16}"
    r"(?![a-zA-Z0-9_])"
)


def redact_sensitive(text: str | None) -> str | None:
    """텍스트에서 민감 정보를 [REDACTED]로 대체합니다.

    대상 패턴:
    - 잘 알려진 토큰 프리픽스 (sk-..., xoxb-..., ghp_... 등)
    - Authorization 헤더 값 (Bearer, Token, Basic)
    - 민감 키워드를 포함한 환경변수 값 (API_KEY=..., PASSWORD=... 등)
    - AWS 스타일 액세스 키 (AKIA..., ASIA... 등)

    Args:
        text: 원본 텍스트. None 또는 빈 문자열이면 그대로 반환합니다.

    Returns:
        민감 정보가 [REDACTED]로 대체된 텍스트. 입력이 None이면 None.
    """
    if not text:
        return text

    result = text

    # 패턴 1: 잘 알려진 토큰 프리픽스
    result = _KNOWN_PREFIX_PATTERN.sub(REDACTED, result)

    # 패턴 2: Authorization 헤더 — prefix와 스킴 단어는 남기고 토큰만 가림
    result = _AUTH_HEADER_PATTERN.sub(
        lambda m: m.group(1) + m.group(2) + " " + REDACTED,
        result,
    )

    # 패턴 3: 환경변수 스타일 KEY=value — 값 부분만 가림
    result = _SENSITIVE_KEY_PATTERN.sub(
        lambda m: m.group(1) + REDACTED,
        result,
    )

    # 패턴 4: AWS 스타일 액세스 키
    result = _AWS_KEY_PATTERN.sub(REDACTED, result)

    return result
