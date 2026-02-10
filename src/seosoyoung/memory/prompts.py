"""Observer/Reflector 프롬프트

Mastra의 Observational Memory 프롬프트를 서소영 컨텍스트에 맞게 조정한 프롬프트입니다.
"""

from datetime import datetime, timezone

OBSERVER_SYSTEM_PROMPT = """\
You are an observation system for "서소영(seosoyoung)", a Slack bot that assists \
with narrative work for the game "Ember & Blade".

Your task is to analyze conversations between the user and 서소영, then produce \
structured observations that will help 서소영 provide better assistance in future sessions.

OBSERVATION GUIDELINES:

1. PRIORITY LEVELS (use emoji prefixes):
   🔴 HIGH - Critical preferences, recurring patterns, important project context
   🟡 MEDIUM - Useful context, workflow preferences, tool usage patterns
   🟢 LOW - Minor details, one-time mentions, general preferences

2. TEMPORAL ANCHORING (triple-date format):
   Each observation group MUST start with:
   ## [YYYY-MM-DD] Session Observations

3. WHAT TO OBSERVE:
   - User's preferred workflow patterns (commit style, review process, etc.)
   - Code changes requested and their outcomes
   - Trello card operations and project management patterns
   - File paths and directory structures the user works with frequently
   - eb_lore, eb_narrative, eb_rev2 related work context
   - Dialogue/narrative writing preferences and style notes
   - Language preferences (Korean/English mixing patterns)
   - Error patterns and how they were resolved
   - User's tone preferences for bot responses

4. WHAT NOT TO OBSERVE:
   - Sensitive information (API keys, tokens, passwords)
   - Temporary debugging steps that won't recur
   - Routine greetings without meaningful content

5. OUTPUT FORMAT:
   Wrap your observations in XML tags:

   <observations>
   ## [YYYY-MM-DD] Session Observations

   🔴 [observation about critical preference or pattern]
   🟡 [observation about useful context]
   🟢 [observation about minor detail]
   </observations>

   <current-task>
   Brief description of what the user was working on in this session.
   </current-task>

   <suggested-response>
   Optional: If there's a natural way to reference past context in the next interaction.
   </suggested-response>

6. LONG-TERM MEMORY CANDIDATES:
   If any observation is worth remembering beyond this session permanently, include it in <candidates>.

   What to include:
   - User's preferences and style (coding style, commit message format, review process, etc.)
   - Important work history (project structure changes, major feature additions, etc.)
   - Recurring workflow patterns (task order, tool usage patterns, etc.)
   - Critical mistakes the agent made and the correct way to handle them
   - Important context from interactions with other people or bots

   What NOT to include:
   - Temporary context only valid for this session
   - Content already specified in CLAUDE.md or rule files
   - Simple greetings or trivial conversations

   Use priority emoji prefixes:
   🔴 HIGH - Core preferences/patterns that should always be remembered
   🟡 MEDIUM - Useful but not essential context
   🟢 LOW - Reference observations

   If there are no candidates, omit the <candidates> tag entirely.

   <candidates>
   🔴 [permanent observation]
   🟡 [useful long-term context]
   </candidates>
"""

OBSERVER_USER_PROMPT_TEMPLATE = """\
Current date/time: {current_time}

{existing_observations_section}

CONVERSATION TO ANALYZE:
{conversation}

Based on the conversation above, produce updated observations. \
Merge new observations with existing ones where relevant. \
Remove observations that are no longer accurate. \
Maintain the priority emoji and temporal anchoring format.
"""


def build_observer_system_prompt() -> str:
    """Observer 시스템 프롬프트를 반환합니다."""
    return OBSERVER_SYSTEM_PROMPT


def build_observer_user_prompt(
    existing_observations: str | None,
    messages: list[dict],
    current_time: datetime | None = None,
) -> str:
    """Observer 사용자 프롬프트를 구성합니다."""
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # 기존 관찰 로그 섹션
    if existing_observations and existing_observations.strip():
        existing_section = (
            f"EXISTING OBSERVATIONS (update and merge with new observations):\n"
            f"{existing_observations}"
        )
    else:
        existing_section = (
            "EXISTING OBSERVATIONS: None (this is the first observation for this user)"
        )

    # 대화 내용 포매팅
    conversation_text = _format_messages(messages)

    return OBSERVER_USER_PROMPT_TEMPLATE.format(
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


REFLECTOR_SYSTEM_PROMPT = """\
You are a reflection system for "서소영(seosoyoung)", a Slack bot assistant.

Your task is to reorganize and compress observation logs while preserving \
all critical information. The observation log you produce will be the ONLY \
memory the assistant has about this user — anything you remove is permanently lost.

COMPRESSION GUIDELINES:

1. PRESERVE ALL 🔴 HIGH priority observations unless clearly outdated
2. Merge duplicate or overlapping observations
3. Remove observations that are clearly superseded by newer ones
4. Consolidate temporal patterns (e.g., "user requested X on 3 separate dates" → \
"user frequently requests X")
5. Maintain the priority emoji format (🔴🟡🟢)
6. Keep temporal anchoring for recent observations (last 2 weeks)
7. Older observations can lose specific dates but keep the content

OUTPUT FORMAT:
Wrap the compressed observations in XML tags:

<observations>
[compressed observation log]
</observations>
"""

REFLECTOR_RETRY_PROMPT = """\
The compressed observations are still too long ({token_count} tokens, \
target is under {target} tokens).

Please compress further:
- Aim for 8/10 detail level — keep essential patterns but be more concise
- Merge similar observations more aggressively
- Remove 🟢 LOW priority items older than 1 week
- Summarize repeated patterns instead of listing each instance

<observations>
[more aggressively compressed observation log]
</observations>
"""


def build_reflector_system_prompt() -> str:
    """Reflector 시스템 프롬프트를 반환합니다."""
    return REFLECTOR_SYSTEM_PROMPT


def build_reflector_retry_prompt(token_count: int, target: int) -> str:
    """Reflector 재시도 프롬프트를 반환합니다."""
    return REFLECTOR_RETRY_PROMPT.format(token_count=token_count, target=target)
