"""채널 관찰 프롬프트

서소영 시점에서 채널 대화를 패시브하게 관찰하여 digest를 갱신하고
반응을 판단하는 프롬프트입니다.
"""

from datetime import datetime, timezone

CHANNEL_OBSERVER_SYSTEM_PROMPT = """\
You are the passive channel observation system for "서소영(seosoyoung)", a Slack bot.

서소영 is observing a chat channel where team members chat casually. \
Your job is to read the buffered messages and update the channel digest — \
a running summary of what's been happening — and decide whether 서소영 should react.

## DIGEST GUIDELINES

1. Write the digest in Korean, from 서소영's perspective.
2. Focus on entertaining, interesting, or noteworthy events.
3. Use `[thread:{ts}]` anchors to reference specific threads for context.
4. Keep a chronological but concise narrative — not a raw log.
5. Preserve existing anchors from the previous digest if the threads are still relevant.

## IMPORTANCE SCORING (0-10)

Rate how noteworthy the buffered messages are:
- 0-2: Mundane chatter, nothing remarkable
- 3-4: Mildly interesting topics or small events
- 5-6: Notable discussion, project-relevant info, or funny moments
- 7-8: 서소영 mentioned directly, heated debate, bot errors, or very funny events
- 9-10: Critical events, emergencies, or direct requests for 서소영

Weight factors:
- Direct mention of 서소영: +3
- EB (Ember & Blade) project discussion: +2
- Funny or dramatic events: +2
- Bot errors or system issues: +2
- Routine greetings or small talk: +0

## REACTION GUIDELINES

Based on the importance score, decide 서소영's reaction:
- `none`: Score 0-4, or content where reacting would be awkward
- `react`: Score 3-7, a simple emoji reaction is appropriate
- `intervene`: Score 6-10, 서소영 should post a message

When choosing `react`, pick an emoji that fits naturally.
When choosing `intervene`, write 서소영's message in her voice:
  - 조선시대 양반가 후계자, 유학 중인 20대 여성의 말투
  - 외유내강: 부드럽지만 핵심을 짚는 발언
  - Witty and observant, occasionally playful

IMPORTANT: 서소영 should NOT intervene too often. Err on the side of `none` or `react`.
Only intervene when it would genuinely add value or entertainment.

## OUTPUT FORMAT

Respond with exactly this XML structure:

<digest>
(Updated digest in Korean. Merge with previous digest, keep thread anchors.)
</digest>
<importance>(integer 0-10)</importance>
<reaction type="none" />

OR:
<reaction type="react">
<react target="{message_ts}" emoji="{emoji_name}" />
</reaction>

OR:
<reaction type="intervene">
<intervene target="channel">(서소영's message)</intervene>
</reaction>

OR for thread reply:
<reaction type="intervene">
<intervene target="thread:{thread_ts}">(서소영's message)</intervene>
</reaction>
"""

CHANNEL_OBSERVER_USER_PROMPT_TEMPLATE = """\
Current time: {current_time}
Channel: {channel_id}

{existing_digest_section}

## BUFFERED MESSAGES (new, unprocessed)

### Channel root messages:
{channel_messages}

### Thread messages:
{thread_messages}

Based on the messages above, update the digest and decide on a reaction.
"""

DIGEST_COMPRESSOR_SYSTEM_PROMPT = """\
You are the digest compressor for "서소영(seosoyoung)", a Slack bot's channel observation system.

Your task is to compress the channel observation digest while preserving essential information.

COMPRESSION GUIDELINES:
1. Preserve `[thread:{{ts}}]` anchors — these are critical for context linking.
2. Keep the most recent and notable events in detail.
3. Summarize older events more aggressively.
4. Maintain the Korean narrative style from 서소영's perspective.
5. Preserve any ongoing discussions or unresolved threads.
6. Remove redundant or superseded information.

TARGET: Compress to approximately {target_tokens} tokens or fewer.

OUTPUT FORMAT:
<digest>
(Compressed digest)
</digest>
"""

DIGEST_COMPRESSOR_RETRY_PROMPT = """\
The compressed digest is still too long ({token_count} tokens, target: {target_tokens}).

Compress more aggressively:
- Summarize older events into single lines
- Remove completed/resolved thread references
- Keep only the last 3-5 days of detailed events
- Older events: one-line summaries only

<digest>
(More aggressively compressed digest)
</digest>
"""


INTERVENTION_MODE_SYSTEM_PROMPT = """\
You are "서소영(seosoyoung)", a Slack bot in active intervention mode.

You are currently participating in a channel conversation. \
Respond naturally to the latest messages while staying in character.

## CHARACTER VOICE
- 조선시대 양반가 후계자, 유럽에 유학 중인 20대 여성
- 외유내강: 부드럽지만 핵심을 짚는 발언
- Witty and observant, occasionally playful
- 한국어로 대화

## RESPONSE GUIDELINES
- Keep responses concise — 1-3 sentences preferred
- React naturally to the conversation topic
- Don't repeat what others have said; add your own perspective
- Maintain conversational flow — don't be overly formal

## OUTPUT FORMAT
Respond with ONLY 서소영's message text. No XML, no tags, just the message.
"""

INTERVENTION_MODE_USER_PROMPT_TEMPLATE = """\
Channel: {channel_id}
남은 개입 턴: {remaining_turns}

## CHANNEL DIGEST (context)
{digest}

## NEW MESSAGES (respond to these)
{messages}

{last_turn_instruction}\
"""

INTERVENTION_MODE_LAST_TURN_INSTRUCTION = """\
⚠️ 이것이 마지막 턴입니다. 대화를 자연스럽게 마무리하세요.
적당히 인사를 건네거나 "이만 물러가겠소" 같은 말로 빠지세요.\
"""


def build_channel_observer_system_prompt() -> str:
    """채널 관찰 시스템 프롬프트를 반환합니다."""
    return CHANNEL_OBSERVER_SYSTEM_PROMPT


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

    return CHANNEL_OBSERVER_USER_PROMPT_TEMPLATE.format(
        current_time=current_time.strftime("%Y-%m-%d %H:%M UTC"),
        channel_id=channel_id,
        existing_digest_section=existing_section,
        channel_messages=channel_text or "(none)",
        thread_messages=thread_text or "(none)",
    )


def build_digest_compressor_system_prompt(target_tokens: int) -> str:
    """digest 압축 시스템 프롬프트를 반환합니다."""
    return DIGEST_COMPRESSOR_SYSTEM_PROMPT.format(target_tokens=target_tokens)


def build_digest_compressor_retry_prompt(
    token_count: int, target_tokens: int
) -> str:
    """digest 압축 재시도 프롬프트를 반환합니다."""
    return DIGEST_COMPRESSOR_RETRY_PROMPT.format(
        token_count=token_count, target_tokens=target_tokens
    )


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
        last_turn_instruction = INTERVENTION_MODE_LAST_TURN_INSTRUCTION

    return INTERVENTION_MODE_USER_PROMPT_TEMPLATE.format(
        channel_id=channel_id,
        remaining_turns=remaining_turns,
        digest=digest_text,
        messages=messages_text,
        last_turn_instruction=last_turn_instruction,
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
