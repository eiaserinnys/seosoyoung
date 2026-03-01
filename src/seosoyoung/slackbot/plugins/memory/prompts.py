"""Observer/Reflector 프롬프트

Mastra의 Observational Memory 프롬프트를 서소영 컨텍스트에 맞게 조정한 프롬프트입니다.

프롬프트 텍스트는 prompt_files/ 디렉토리의 외부 파일에서 로드됩니다.
"""

import json
from datetime import datetime, timezone

from seosoyoung.slackbot.plugins.memory.prompt_loader import load_prompt_cached


def _load(filename: str) -> str:
    """내부 헬퍼: 캐시된 프롬프트 로드"""
    return load_prompt_cached(filename)


def build_observer_system_prompt() -> str:
    """Observer 시스템 프롬프트를 반환합니다."""
    return _load("om_observer_system.txt")


def build_observer_user_prompt(
    existing_observations: list[dict] | None,
    messages: list[dict],
    current_time: datetime | None = None,
) -> str:
    """Observer 사용자 프롬프트를 구성합니다."""
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # 기존 관찰 로그 섹션
    if existing_observations:
        existing_section = (
            "EXISTING OBSERVATIONS (update and merge with new observations):\n"
            + json.dumps(existing_observations, ensure_ascii=False, indent=2)
        )
    else:
        existing_section = (
            "EXISTING OBSERVATIONS: [] (this is the first observation for this user)"
        )

    # 대화 내용 포매팅
    conversation_text = _format_messages(messages)

    template = _load("om_observer_user.txt")
    return template.format(
        current_time=current_time.strftime("%Y-%m-%d %H:%M UTC"),
        existing_observations_section=existing_section,
        conversation=conversation_text,
    )


def _format_messages(messages: list[dict]) -> str:
    """메시지 목록을 Observer 입력용 텍스트로 변환"""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")
        prefix = f"[{timestamp}] " if timestamp else ""
        lines.append(f"{prefix}{role}: {content}")
    return "\n".join(lines)


def build_reflector_system_prompt() -> str:
    """Reflector 시스템 프롬프트를 반환합니다."""
    return _load("om_reflector_system.txt")


def build_reflector_retry_prompt(token_count: int, target: int) -> str:
    """Reflector 재시도 프롬프트를 반환합니다."""
    return _load("om_reflector_retry.txt").format(
        token_count=token_count, target=target
    )


def build_promoter_prompt(
    existing_persistent: list[dict],
    candidate_entries: list[dict],
) -> str:
    """Promoter 프롬프트를 구성합니다."""
    existing_json = (
        json.dumps(existing_persistent, ensure_ascii=False, indent=2)
        if existing_persistent
        else "[]"
    )
    candidates_json = (
        json.dumps(candidate_entries, ensure_ascii=False, indent=2)
        if candidate_entries
        else "[]"
    )
    return _load("om_promoter_system.txt").format(
        existing_persistent=existing_json,
        candidate_entries=candidates_json,
    )


def build_compactor_prompt(
    persistent_memory: list[dict],
    target_tokens: int,
) -> str:
    """Compactor 프롬프트를 구성합니다."""
    memory_json = json.dumps(persistent_memory, ensure_ascii=False, indent=2)
    return _load("om_compactor_system.txt").format(
        target_tokens=target_tokens,
        persistent_memory=memory_json,
    )
