"""채널 관찰 엔진

채널 버퍼를 읽고 digest를 갱신하며, 반응 판단(none/react/intervene)을 수행합니다.
DigestCompressor는 digest가 임계치를 초과할 때 압축합니다.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import openai

from seosoyoung.memory.channel_prompts import (
    build_channel_observer_system_prompt,
    build_channel_observer_user_prompt,
    build_digest_compressor_retry_prompt,
    build_digest_compressor_system_prompt,
    build_digest_only_system_prompt,
    build_digest_only_user_prompt,
    build_judge_system_prompt,
    build_judge_user_prompt,
)
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class ChannelObserverResult:
    """채널 관찰 결과 (하위호환 유지)"""

    digest: str = ""
    importance: int = 0
    reaction_type: str = "none"  # "none" | "react" | "intervene"
    reaction_target: Optional[str] = None  # ts, "channel", "thread:{ts}"
    reaction_content: Optional[str] = None  # emoji name or message text


@dataclass
class DigestResult:
    """소화 전용 결과"""

    digest: str
    token_count: int


@dataclass
class JudgeItem:
    """개별 메시지에 대한 리액션 판단 결과"""

    ts: str = ""
    importance: int = 0
    reaction_type: str = "none"  # "none" | "react" | "intervene"
    reaction_target: Optional[str] = None
    reaction_content: Optional[str] = None
    reasoning: Optional[str] = None
    emotion: Optional[str] = None
    addressed_to_me: bool = False
    addressed_to_me_reason: Optional[str] = None
    related_to_me: bool = False
    related_to_me_reason: Optional[str] = None
    is_instruction: bool = False
    is_instruction_reason: Optional[str] = None
    context_meaning: Optional[str] = None


@dataclass
class JudgeResult:
    """복수 메시지에 대한 리액션 판단 결과

    items가 있으면 메시지별 개별 판단 결과를 사용합니다.
    items가 없으면 하위호환용 단일 필드를 사용합니다.
    """

    items: list[JudgeItem] = field(default_factory=list)

    # 하위호환: items가 비어있으면 단일 필드 사용
    importance: int = 0
    reaction_type: str = "none"
    reaction_target: Optional[str] = None
    reaction_content: Optional[str] = None
    reasoning: Optional[str] = None
    emotion: Optional[str] = None
    addressed_to_me: bool = False
    addressed_to_me_reason: Optional[str] = None
    related_to_me: bool = False
    related_to_me_reason: Optional[str] = None
    is_instruction: bool = False
    is_instruction_reason: Optional[str] = None
    context_meaning: Optional[str] = None


@dataclass
class DigestCompressorResult:
    """digest 압축 결과"""

    digest: str
    token_count: int


def parse_channel_observer_output(text: str) -> ChannelObserverResult:
    """Observer 응답에서 XML 태그를 파싱합니다."""
    digest = _extract_tag(text, "digest")
    if not digest:
        digest = text.strip()

    # importance
    importance_str = _extract_tag(text, "importance")
    try:
        importance = int(importance_str)
    except (ValueError, TypeError):
        importance = 0
    importance = max(0, min(10, importance))

    # reaction
    reaction_type, reaction_target, reaction_content = _parse_reaction(text)

    return ChannelObserverResult(
        digest=digest,
        importance=importance,
        reaction_type=reaction_type,
        reaction_target=reaction_target,
        reaction_content=reaction_content,
    )


def parse_judge_output(text: str) -> JudgeResult:
    """Judge 응답에서 XML 태그를 파싱합니다.

    복수 <judgment ts="..."> 블록이 있으면 각각을 JudgeItem으로 파싱합니다.
    없으면 하위호환으로 단일 결과를 파싱합니다.
    """
    # 복수 judgment 블록 파싱 시도
    judgment_blocks = re.findall(
        r'<judgment\s+ts="([^"]+)">(.*?)</judgment>',
        text, re.DOTALL,
    )

    if judgment_blocks:
        items = []
        for ts, block in judgment_blocks:
            item = _parse_judge_item(ts, block)
            items.append(item)
        return JudgeResult(items=items)

    # 하위호환: 단일 결과 파싱
    reasoning = _extract_tag(text, "reasoning") or None
    emotion = _extract_tag(text, "emotion") or None
    context_meaning = _extract_tag(text, "context_meaning") or None

    addressed_to_me = _parse_yes_no(text, "addressed_to_me")
    addressed_to_me_reason = _extract_tag(text, "addressed_to_me_reason") or None
    related_to_me = _parse_yes_no(text, "related_to_me")
    related_to_me_reason = _extract_tag(text, "related_to_me_reason") or None
    is_instruction = _parse_yes_no(text, "is_instruction")
    is_instruction_reason = _extract_tag(text, "is_instruction_reason") or None

    importance_str = _extract_tag(text, "importance")
    try:
        importance = int(importance_str)
    except (ValueError, TypeError):
        importance = 0
    importance = max(0, min(10, importance))

    reaction_type, reaction_target, reaction_content = _parse_reaction(text)

    return JudgeResult(
        importance=importance,
        reaction_type=reaction_type,
        reaction_target=reaction_target,
        reaction_content=reaction_content,
        reasoning=reasoning,
        emotion=emotion,
        addressed_to_me=addressed_to_me,
        addressed_to_me_reason=addressed_to_me_reason,
        related_to_me=related_to_me,
        related_to_me_reason=related_to_me_reason,
        is_instruction=is_instruction,
        is_instruction_reason=is_instruction_reason,
        context_meaning=context_meaning,
    )


def _parse_yes_no(text: str, tag_name: str) -> bool:
    """yes/no 태그를 파싱합니다. 없거나 'no'면 False."""
    value = _extract_tag(text, tag_name).lower().strip()
    return value == "yes"


def _parse_judge_item(ts: str, block: str) -> JudgeItem:
    """개별 <judgment> 블록을 JudgeItem으로 파싱합니다."""
    reasoning = _extract_tag(block, "reasoning") or None
    emotion = _extract_tag(block, "emotion") or None
    context_meaning = _extract_tag(block, "context_meaning") or None

    addressed_to_me = _parse_yes_no(block, "addressed_to_me")
    addressed_to_me_reason = _extract_tag(block, "addressed_to_me_reason") or None
    related_to_me = _parse_yes_no(block, "related_to_me")
    related_to_me_reason = _extract_tag(block, "related_to_me_reason") or None
    is_instruction = _parse_yes_no(block, "is_instruction")
    is_instruction_reason = _extract_tag(block, "is_instruction_reason") or None

    importance_str = _extract_tag(block, "importance")
    try:
        importance = int(importance_str)
    except (ValueError, TypeError):
        importance = 0
    importance = max(0, min(10, importance))

    reaction_type, reaction_target, reaction_content = _parse_reaction(block)

    return JudgeItem(
        ts=ts,
        importance=importance,
        reaction_type=reaction_type,
        reaction_target=reaction_target,
        reaction_content=reaction_content,
        reasoning=reasoning,
        emotion=emotion,
        addressed_to_me=addressed_to_me,
        addressed_to_me_reason=addressed_to_me_reason,
        related_to_me=related_to_me,
        related_to_me_reason=related_to_me_reason,
        is_instruction=is_instruction,
        is_instruction_reason=is_instruction_reason,
        context_meaning=context_meaning,
    )


def _parse_reaction(text: str) -> tuple[str, Optional[str], Optional[str]]:
    """XML 텍스트에서 reaction 정보를 추출합니다."""
    reaction_type = "none"
    reaction_target = None
    reaction_content = None

    reaction_match = re.search(
        r'<reaction\s+type="(\w+)"', text
    )
    if reaction_match:
        reaction_type = reaction_match.group(1)

    if reaction_type == "react":
        react_match = re.search(
            r'<react\s+target="([^"]+)"\s+emoji="([^"]+)"',
            text,
        )
        if react_match:
            reaction_target = react_match.group(1)
            reaction_content = react_match.group(2)

    elif reaction_type == "intervene":
        intervene_match = re.search(
            r'<intervene\s+target="([^"]+)">(.*?)</intervene>',
            text,
            re.DOTALL,
        )
        if intervene_match:
            reaction_target = intervene_match.group(1)
            reaction_content = intervene_match.group(2).strip()

    return reaction_type, reaction_target, reaction_content


class ChannelObserver:
    """채널 대화를 관찰하여 digest를 갱신하고 반응을 판단"""

    def __init__(self, api_key: str, model: str = "gpt-5-mini"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def observe(
        self,
        channel_id: str,
        existing_digest: str | None,
        channel_messages: list[dict],
        thread_buffers: dict[str, list[dict]],
    ) -> ChannelObserverResult | None:
        """채널 버퍼를 분석하여 관찰 결과를 반환합니다 (하위호환).

        Args:
            channel_id: 채널 ID
            existing_digest: 기존 digest (없으면 None)
            channel_messages: 채널 루트 메시지 버퍼
            thread_buffers: {thread_ts: [messages]} 스레드 버퍼

        Returns:
            ChannelObserverResult 또는 None (API 오류 시)
        """
        system_prompt = build_channel_observer_system_prompt()
        user_prompt = build_channel_observer_user_prompt(
            channel_id=channel_id,
            existing_digest=existing_digest,
            channel_messages=channel_messages,
            thread_buffers=thread_buffers,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=16_000,
            )

            result_text = response.choices[0].message.content or ""
            return parse_channel_observer_output(result_text)

        except Exception as e:
            logger.error(f"ChannelObserver API 호출 실패: {e}")
            return None

    async def digest(
        self,
        channel_id: str,
        existing_digest: str | None,
        judged_messages: list[dict],
    ) -> DigestResult | None:
        """judged 메시지를 digest에 편입합니다 (소화 전용).

        Args:
            channel_id: 채널 ID
            existing_digest: 기존 digest (없으면 None)
            judged_messages: 편입할 메시지들

        Returns:
            DigestResult 또는 None (API 오류 시)
        """
        system_prompt = build_digest_only_system_prompt()
        user_prompt = build_digest_only_user_prompt(
            channel_id=channel_id,
            existing_digest=existing_digest,
            judged_messages=judged_messages,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=16_000,
            )

            result_text = response.choices[0].message.content or ""
            digest_text = _extract_tag(result_text, "digest")
            if not digest_text:
                digest_text = result_text.strip()

            token_counter = TokenCounter()
            token_count = token_counter.count_string(digest_text)

            return DigestResult(digest=digest_text, token_count=token_count)

        except Exception as e:
            logger.error(f"ChannelObserver.digest API 호출 실패: {e}")
            return None

    async def judge(
        self,
        channel_id: str,
        digest: str | None,
        judged_messages: list[dict],
        pending_messages: list[dict],
        thread_buffers: dict[str, list[dict]] | None = None,
        bot_user_id: str | None = None,
        slack_client=None,
    ) -> JudgeResult | None:
        """pending 메시지에 대해 리액션을 판단합니다 (판단 전용).

        Args:
            channel_id: 채널 ID
            digest: 현재 digest (컨텍스트)
            judged_messages: 이미 판단을 거친 최근 대화
            pending_messages: 아직 판단하지 않은 새 대화
            thread_buffers: {thread_ts: [messages]} 스레드 버퍼
            bot_user_id: 봇 사용자 ID (멘션 포함 메시지 마킹용)
            slack_client: Slack WebClient (디스플레이네임 조회용)

        Returns:
            JudgeResult 또는 None (API 오류 시)
        """
        system_prompt = build_judge_system_prompt()
        user_prompt = build_judge_user_prompt(
            channel_id=channel_id,
            digest=digest,
            judged_messages=judged_messages,
            pending_messages=pending_messages,
            thread_buffers=thread_buffers or {},
            bot_user_id=bot_user_id,
            slack_client=slack_client,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=8_000,
            )

            result_text = response.choices[0].message.content or ""
            return parse_judge_output(result_text)

        except Exception as e:
            logger.error(f"ChannelObserver.judge API 호출 실패: {e}")
            return None


class DigestCompressor:
    """digest가 임계치를 초과할 때 압축"""

    def __init__(self, api_key: str, model: str = "gpt-5.2"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.token_counter = TokenCounter()

    async def compress(
        self,
        digest: str,
        target_tokens: int = 5000,
    ) -> DigestCompressorResult | None:
        """digest를 압축합니다.

        Args:
            digest: 압축할 digest
            target_tokens: 목표 토큰 수

        Returns:
            DigestCompressorResult 또는 None (API 오류 시)
        """
        system_prompt = build_digest_compressor_system_prompt(target_tokens)

        try:
            # 1차 시도
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": digest},
                ],
                max_completion_tokens=16_000,
            )

            result_text = response.choices[0].message.content or ""
            compressed = _extract_tag(result_text, "digest") or result_text.strip()
            token_count = self.token_counter.count_string(compressed)

            logger.info(
                f"DigestCompressor 1차: {token_count} tokens (목표: {target_tokens})"
            )

            if token_count <= target_tokens:
                return DigestCompressorResult(
                    digest=compressed,
                    token_count=token_count,
                )

            # 2차 시도
            retry_prompt = build_digest_compressor_retry_prompt(
                token_count, target_tokens
            )
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": digest},
                    {"role": "assistant", "content": result_text},
                    {"role": "user", "content": retry_prompt},
                ],
                max_completion_tokens=16_000,
            )

            retry_text = response.choices[0].message.content or ""
            compressed = _extract_tag(retry_text, "digest") or retry_text.strip()
            token_count = self.token_counter.count_string(compressed)

            logger.info(
                f"DigestCompressor 2차: {token_count} tokens (목표: {target_tokens})"
            )

            return DigestCompressorResult(
                digest=compressed,
                token_count=token_count,
            )

        except Exception as e:
            logger.error(f"DigestCompressor API 호출 실패: {e}")
            return None


def _extract_tag(text: str, tag_name: str) -> str:
    """XML 태그 내용을 추출합니다. 없으면 빈 문자열."""
    pattern = rf"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""
