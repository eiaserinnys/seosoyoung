"""채널 관찰 프롬프트

서소영 시점에서 채널 대화를 패시브하게 관찰하여 digest를 갱신하고
반응을 판단하는 프롬프트입니다.

프롬프트 텍스트는 prompt_files/ 디렉토리의 외부 파일에서 로드됩니다.
"""

from datetime import datetime, timezone

from seosoyoung.memory.prompt_loader import load_prompt_cached


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


def get_intervention_mode_system_prompt() -> str:
    """개입 모드 시스템 프롬프트를 반환합니다."""
    return _load("intervention_mode_system.txt")


def build_intervention_mode_prompt(
    remaining_turns: int,
    channel_id: str,
    new_messages: list[dict],
    digest: str | None = None,
) -> str:
    """개입 모드 사용자 프롬프트를 구성합니다."""
    messages_text = _format_channel_messages(new_messages) or "(없음)"
    digest_text = digest or "(없음)"

    last_turn_instruction = ""
    if remaining_turns <= 1:
        last_turn_instruction = _load("intervention_mode_last_turn.txt")

    template = _load("intervention_mode_user.txt")
    return template.format(
        channel_id=channel_id,
        remaining_turns=remaining_turns,
        digest=digest_text,
        messages=messages_text,
        last_turn_instruction=last_turn_instruction,
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
) -> str:
    """채널 개입 응답 생성 사용자 프롬프트를 구성합니다."""
    digest_text = digest or "(없음)"
    recent_text = _format_channel_messages(recent_messages) or "(없음)"

    if trigger_message:
        ts = trigger_message.get("ts", "")
        user = trigger_message.get("user", "unknown")
        text = trigger_message.get("text", "")
        trigger_text = f"[{ts}] <{user}>: {text}"
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
) -> str:
    """리액션 판단 전용 사용자 프롬프트를 구성합니다."""
    digest_text = digest or "(없음)"
    judged_text = _format_channel_messages(judged_messages) or "(없음)"
    pending_text = _format_channel_messages(pending_messages) or "(없음)"

    template = _load("judge_user.txt")
    return template.format(
        channel_id=channel_id,
        digest=digest_text,
        judged_messages=judged_text,
        pending_messages=pending_text,
    )


def _format_channel_messages(messages: list[dict]) -> str:
    """채널 루트 메시지를 텍스트로 변환"""
    if not messages:
        return ""
    lines = []
    for msg in messages:
        ts = msg.get("ts", "")
        user = msg.get("user", "unknown")
        text = msg.get("text", "")
        lines.append(f"[{ts}] <{user}>: {text}")
    return "\n".join(lines)


def _format_thread_messages(thread_buffers: dict[str, list[dict]]) -> str:
    """스레드 메시지를 텍스트로 변환"""
    if not thread_buffers:
        return ""
    sections = []
    for thread_ts, messages in sorted(thread_buffers.items()):
        lines = [f"--- thread:{thread_ts} ---"]
        for msg in messages:
            ts = msg.get("ts", "")
            user = msg.get("user", "unknown")
            text = msg.get("text", "")
            lines.append(f"  [{ts}] <{user}>: {text}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
