"""채널 관찰 프롬프트

서소영 시점에서 채널 대화를 패시브하게 관찰하여 digest를 갱신하고
반응을 판단하는 프롬프트입니다.

프롬프트 텍스트는 prompt_files/ 디렉토리의 외부 파일에서 로드됩니다.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from seosoyoung.memory.prompt_loader import load_prompt_cached

logger = logging.getLogger(__name__)


class DisplayNameResolver:
    """Slack user ID → 디스플레이네임 캐시 기반 변환기.

    같은 파이프라인 실행 내에서 중복 ID는 1회만 조회합니다.
    """

    def __init__(self, slack_client=None):
        self._client = slack_client
        self._cache: dict[str, str] = {}

    def resolve(self, user_id: str) -> str:
        """user_id를 '디스플레이네임 (UID)' 형식으로 변환합니다.

        slack_client가 없거나 조회 실패 시 원래 user_id를 반환합니다.
        """
        if user_id in self._cache:
            return self._cache[user_id]

        if not self._client:
            return user_id

        try:
            resp = self._client.users_info(user=user_id)
            if resp and resp.get("ok"):
                user_data = resp["user"]
                profile = user_data.get("profile", {})
                display_name = (
                    profile.get("display_name")
                    or profile.get("real_name")
                    or user_data.get("name")
                    or user_id
                )
                formatted = f"{display_name} ({user_id})"
                self._cache[user_id] = formatted
                return formatted
        except Exception as e:
            logger.debug(f"users_info 조회 실패 ({user_id}): {e}")

        self._cache[user_id] = user_id
        return user_id


def _load(filename: str) -> str:
    """내부 헬퍼: 캐시된 프롬프트 로드"""
    return load_prompt_cached(filename)


def build_channel_observer_system_prompt() -> str:
    """채널 관찰 시스템 프롬프트를 반환합니다."""
    return _load("channel_observer_system.txt")


def build_channel_observer_user_prompt(
    channel_id: str,
    existing_digest: str | None,
    channel_messages: list[dict],
    thread_buffers: dict[str, list[dict]],
    current_time: datetime | None = None,
) -> str:
    """채널 관찰 사용자 프롬프트를 구성합니다."""
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    if existing_digest and existing_digest.strip():
        existing_section = (
            "## EXISTING DIGEST (update and merge)\n"
            f"{existing_digest}"
        )
    else:
        existing_section = (
            "## EXISTING DIGEST: None (first observation for this channel)"
        )

    channel_text = _format_channel_messages(channel_messages)
    thread_text = _format_thread_messages(thread_buffers)

    template = _load("channel_observer_user.txt")
    return template.format(
        current_time=current_time.strftime("%Y-%m-%d %H:%M UTC"),
        channel_id=channel_id,
        existing_digest_section=existing_section,
        channel_messages=channel_text or "(none)",
        thread_messages=thread_text or "(none)",
    )


def build_digest_compressor_system_prompt(target_tokens: int) -> str:
    """digest 압축 시스템 프롬프트를 반환합니다."""
    return _load("digest_compressor_system.txt").format(target_tokens=target_tokens)


def build_digest_compressor_retry_prompt(
    token_count: int, target_tokens: int
) -> str:
    """digest 압축 재시도 프롬프트를 반환합니다."""
    return _load("digest_compressor_retry.txt").format(
        token_count=token_count, target_tokens=target_tokens
    )


def get_channel_intervene_system_prompt() -> str:
    """채널 개입 응답 생성 시스템 프롬프트를 반환합니다."""
    return _load("channel_intervene_system.txt")


def build_channel_intervene_user_prompt(
    digest: str | None,
    recent_messages: list[dict],
    trigger_message: dict | None,
    target: str,
    observer_reason: str | None = None,
    slack_client=None,
) -> str:
    """채널 개입 응답 생성 사용자 프롬프트를 구성합니다."""
    resolver = DisplayNameResolver(slack_client) if slack_client else None

    digest_text = digest or "(없음)"
    recent_text = _format_channel_messages(recent_messages, resolver=resolver) or "(없음)"

    if trigger_message:
        ts = trigger_message.get("ts", "")
        user = trigger_message.get("user", "unknown")
        sender = resolver.resolve(user) if resolver else user
        text = trigger_message.get("text", "")
        trigger_text = f"[{ts}] {sender}: {text}"
    else:
        trigger_text = "(없음)"

    observer_text = observer_reason or "(없음)"

    template = _load("channel_intervene_user.txt")
    return template.format(
        target=target,
        digest=digest_text,
        recent_messages=recent_text,
        trigger_message=trigger_text,
        observer_reason=observer_text,
    )


def build_digest_only_system_prompt() -> str:
    """소화 전용 시스템 프롬프트를 반환합니다."""
    return _load("digest_only_system.txt")


def build_digest_only_user_prompt(
    channel_id: str,
    existing_digest: str | None,
    judged_messages: list[dict],
    current_time: datetime | None = None,
) -> str:
    """소화 전용 사용자 프롬프트를 구성합니다."""
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    if existing_digest and existing_digest.strip():
        existing_section = (
            "## EXISTING DIGEST (update and merge)\n"
            f"{existing_digest}"
        )
    else:
        existing_section = (
            "## EXISTING DIGEST: None (first observation for this channel)"
        )

    judged_text = _format_channel_messages(judged_messages) or "(none)"

    template = _load("digest_only_user.txt")
    return template.format(
        current_time=current_time.strftime("%Y-%m-%d %H:%M UTC"),
        channel_id=channel_id,
        existing_digest_section=existing_section,
        judged_messages=judged_text,
    )


def build_judge_system_prompt() -> str:
    """리액션 판단 전용 시스템 프롬프트를 반환합니다."""
    return _load("judge_system.txt")


def build_judge_user_prompt(
    channel_id: str,
    digest: str | None,
    judged_messages: list[dict],
    pending_messages: list[dict],
    thread_buffers: dict[str, list[dict]] | None = None,
    bot_user_id: str | None = None,
    slack_client=None,
) -> str:
    """리액션 판단 전용 사용자 프롬프트를 구성합니다."""
    resolver = DisplayNameResolver(slack_client) if slack_client else None

    digest_text = digest or "(없음)"
    judged_text = _format_channel_messages(judged_messages, resolver=resolver) or "(없음)"
    pending_text = _format_pending_messages(
        pending_messages, bot_user_id=bot_user_id, resolver=resolver,
    ) or "(없음)"
    thread_text = _format_thread_messages(thread_buffers or {}, resolver=resolver) or "(없음)"

    template = _load("judge_user.txt")
    return template.format(
        channel_id=channel_id,
        digest=digest_text,
        judged_messages=judged_text,
        pending_messages=pending_text,
        thread_messages=thread_text,
    )


def _format_reactions(reactions: list[dict]) -> str:
    """reactions 리스트를 `:emoji:×count` 형식의 문자열로 변환"""
    if not reactions:
        return ""
    parts = [f":{r['name']}:×{r['count']}" for r in reactions]
    return " [" + " ".join(parts) + "]"


def _format_pending_messages(
    messages: list[dict],
    bot_user_id: str | None = None,
    resolver: Optional[DisplayNameResolver] = None,
) -> str:
    """pending 메시지를 텍스트로 변환.

    사람이 보낸 봇 멘션 메시지는 멘션 핸들러가 처리하므로 [ALREADY REACTED] 표기.
    봇이 보낸 멘션은 채널 모니터가 처리해야 하므로 태그하지 않음.
    """
    if not messages:
        return ""
    mention_pattern = f"<@{bot_user_id}>" if bot_user_id else None
    lines = []
    for msg in messages:
        ts = msg.get("ts", "")
        user = msg.get("user", "unknown")
        sender = resolver.resolve(user) if resolver else user
        text = msg.get("text", "")
        is_bot = bool(msg.get("bot_id"))
        tag = ""
        if mention_pattern and mention_pattern in text and not is_bot:
            tag = " [ALREADY REACTED]"
        reactions_str = _format_reactions(msg.get("reactions", []))
        lines.append(f"[{ts}] {sender}: {text}{tag}{reactions_str}")
    return "\n".join(lines)


def _format_channel_messages(
    messages: list[dict],
    resolver: Optional[DisplayNameResolver] = None,
) -> str:
    """채널 루트 메시지를 텍스트로 변환"""
    if not messages:
        return ""
    lines = []
    for msg in messages:
        ts = msg.get("ts", "")
        user = msg.get("user", "unknown")
        sender = resolver.resolve(user) if resolver else user
        text = msg.get("text", "")
        reactions_str = _format_reactions(msg.get("reactions", []))
        lines.append(f"[{ts}] {sender}: {text}{reactions_str}")
    return "\n".join(lines)


def _format_thread_messages(
    thread_buffers: dict[str, list[dict]],
    resolver: Optional[DisplayNameResolver] = None,
) -> str:
    """스레드 메시지를 텍스트로 변환"""
    if not thread_buffers:
        return ""
    sections = []
    for thread_ts, messages in sorted(thread_buffers.items()):
        lines = [f"--- thread:{thread_ts} ---"]
        for msg in messages:
            ts = msg.get("ts", "")
            user = msg.get("user", "unknown")
            sender = resolver.resolve(user) if resolver else user
            text = msg.get("text", "")
            reactions_str = _format_reactions(msg.get("reactions", []))
            lines.append(f"  [{ts}] {sender}: {text}{reactions_str}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
