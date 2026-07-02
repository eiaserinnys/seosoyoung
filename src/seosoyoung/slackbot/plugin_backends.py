"""Plugin SDK backend implementations.

This module provides the actual implementations of plugin_sdk APIs.
Called during startup to inject backends into plugin_sdk modules.

These backends wrap the existing seosoyoung infrastructure
(slack_client, claude executor, session manager, etc.)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from seosoyoung.plugin_sdk import slack, soulstream, mention
from seosoyoung.plugin_sdk.slack import (
    FileInfo,
    Message,
    MessagePage,
    Reaction,
    ReactionResult,
    SendMessageResult,
    SlackBackend,
    UserInfo,
)
from seosoyoung.slackbot.slack.formatting import build_section_blocks
from seosoyoung.plugin_sdk.soulstream import (
    CompactResult,
    RunResult,
    RunStatus,
    SoulstreamBackend,
)

if TYPE_CHECKING:
    from seosoyoung.slackbot.handlers.mention_tracker import MentionTracker
    from seosoyoung.slackbot.soulstream.session import SessionManager

logger = logging.getLogger(__name__)


async def _noop_compact(_session_id: str, _msg: str) -> None:
    """text_only 모드용 no-op compact 콜백."""


# ============================================================================
# Slack Backend Implementation
# ============================================================================


def _parse_reactions(raw: list[dict]) -> list[Reaction]:
    """Slack API 응답의 reactions 필드를 Reaction 목록으로 변환."""
    return [
        Reaction(name=r["name"], count=r["count"], users=r.get("users", []))
        for r in raw
    ]


def _parse_files(raw: list[dict]) -> list[FileInfo]:
    """Slack API 응답의 files 필드를 FileInfo 목록으로 변환."""
    return [
        FileInfo(
            name=f.get("name", ""),
            title=f.get("title", ""),
            mimetype=f.get("mimetype", ""),
            permalink=f.get("permalink", ""),
        )
        for f in raw
    ]


def _parse_message(raw: dict, *, channel: str) -> Message:
    """Slack API message dict를 plugin_sdk Message로 변환."""
    return Message(
        ts=raw.get("ts", ""),
        text=raw.get("text", ""),
        user=raw.get("user", ""),
        thread_ts=raw.get("thread_ts"),
        channel=channel,
        subtype=raw.get("subtype", ""),
        bot_id=raw.get("bot_id", ""),
        reactions=_parse_reactions(raw.get("reactions", [])),
        files=_parse_files(raw.get("files", [])),
        blocks=raw.get("blocks", []),
    )


class SlackBackendImpl(SlackBackend):
    """Slack backend implementation using slack_sdk client."""

    def __init__(self, client):
        """Initialize with Slack WebClient.

        Args:
            client: slack_sdk.WebClient instance
        """
        self._client = client

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> SendMessageResult:
        """Send a message to a channel."""
        try:
            result = self._client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                **kwargs,
            )
            return SendMessageResult(
                ok=True,
                ts=result.get("ts", ""),
                channel=result.get("channel", channel),
            )
        except Exception as e:
            logger.error(f"send_message failed: {e}")
            return SendMessageResult(ok=False, error=str(e))

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        **kwargs: Any,
    ) -> SendMessageResult:
        """Update an existing message.

        blocks를 명시적으로 전달하지 않으면 text를 mrkdwn section block으로 자동 감싸서 전달합니다.
        """
        if "blocks" not in kwargs:
            kwargs["blocks"] = build_section_blocks(text)
        try:
            result = self._client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                **kwargs,
            )
            return SendMessageResult(
                ok=True,
                ts=result.get("ts", ts),
                channel=result.get("channel", channel),
            )
        except Exception as e:
            logger.error(f"update_message failed: {e}")
            return SendMessageResult(ok=False, error=str(e))

    async def add_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> ReactionResult:
        """Add a reaction to a message."""
        try:
            self._client.reactions_add(
                channel=channel,
                timestamp=ts,
                name=emoji,
            )
            return ReactionResult(ok=True)
        except Exception as e:
            # Already reacted is not an error
            if "already_reacted" in str(e):
                return ReactionResult(ok=True)
            logger.error(f"add_reaction failed: {e}")
            return ReactionResult(ok=False, error=str(e))

    async def remove_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> ReactionResult:
        """Remove a reaction from a message."""
        try:
            self._client.reactions_remove(
                channel=channel,
                timestamp=ts,
                name=emoji,
            )
            return ReactionResult(ok=True)
        except Exception as e:
            # Not reacted is not an error
            if "no_reaction" in str(e):
                return ReactionResult(ok=True)
            logger.error(f"remove_reaction failed: {e}")
            return ReactionResult(ok=False, error=str(e))

    async def get_user_info(self, user_id: str) -> UserInfo | None:
        """Get information about a user.

        R-5 G-15 (2026-05-11): `avatar_url`(profile.image_192) + `email`(profile.email)
        채움 추가 — `build_slack_caller_info` 6-arg 호출에 forward되어 reaction
        trigger 등 plugin 측 진입의 caller_info에 신원이 박힘.
        host slackbot `auth.py:62-63 get_user_role` 패턴과 §9 대칭.
        """
        try:
            result = self._client.users_info(user=user_id)
            user = result.get("user", {})
            profile = user.get("profile", {})
            return UserInfo(
                id=user.get("id", user_id),
                name=user.get("name", ""),
                real_name=profile.get("real_name", ""),
                display_name=profile.get("display_name", ""),
                is_bot=user.get("is_bot", False),
                avatar_url=profile.get("image_192", ""),  # R-5 G-15
                email=profile.get("email", ""),            # R-5 G-15
            )
        except Exception as e:
            logger.error(f"get_user_info failed: {e}")
            return None

    async def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get replies in a thread."""
        try:
            result = self._client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                limit=limit,
            )
            return [_parse_message(msg, channel=channel) for msg in result.get("messages", [])]
        except Exception as e:
            logger.error(f"get_thread_replies failed: {e}")
            return []

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get recent messages in a channel."""
        try:
            result = self._client.conversations_history(
                channel=channel,
                limit=limit,
            )
            return [_parse_message(msg, channel=channel) for msg in result.get("messages", [])]
        except Exception as e:
            logger.error(f"get_channel_history failed: {e}")
            return []

    async def get_channel_history_page(
        self,
        channel: str,
        oldest: str | None = None,
        latest: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> MessagePage:
        """Get one paginated channel history page."""
        try:
            params: dict[str, Any] = {
                "channel": channel,
                "limit": limit,
            }
            if oldest is not None:
                params["oldest"] = oldest
            if latest is not None:
                params["latest"] = latest
            if cursor is not None:
                params["cursor"] = cursor

            result = self._client.conversations_history(**params)
            metadata = result.get("response_metadata", {}) or {}
            return MessagePage(
                messages=[
                    _parse_message(msg, channel=channel)
                    for msg in result.get("messages", [])
                ],
                next_cursor=metadata.get("next_cursor", "") or "",
                has_more=bool(result.get("has_more", False)),
            )
        except Exception as e:
            logger.error(f"get_channel_history_page failed: {e}")
            return MessagePage()

    async def open_dm(self, user_id: str) -> str | None:
        """Open a DM channel with a user."""
        try:
            result = self._client.conversations_open(users=user_id)
            return result.get("channel", {}).get("id")
        except Exception as e:
            logger.error(f"open_dm failed: {e}")
            return None


# ============================================================================
# Soulstream Backend Implementation
# ============================================================================


class SoulstreamBackendImpl(SoulstreamBackend):
    """Soulstream backend implementation using ClaudeExecutor."""

    def __init__(
        self,
        executor,
        session_manager: "SessionManager",
        restart_manager,
        data_dir: Path,
        slack_client=None,
        update_message_fn=None,
    ):
        """Initialize with Claude executor and session manager.

        Args:
            executor: ClaudeExecutor.run bound method
            session_manager: SessionManager instance
            restart_manager: RestartManager instance
            data_dir: Data directory for plugin storage
            slack_client: Slack WebClient instance (for auto-constructing PresentationContext)
            update_message_fn: (client, channel, ts, text, *, blocks=None) -> None
                               전달하면 on_compact가 None일 때 자동 생성됨
        """
        self._executor = executor
        self._session_manager = session_manager
        self._restart_manager = restart_manager
        self._data_dir = data_dir
        self._slack_client = slack_client
        self._update_message_fn = update_message_fn

    def _build_presentation(
        self,
        channel: str,
        thread_ts: str,
        msg_ts: str,
        session_id: str | None,
        role: str,
        *,
        dm_channel_id: str | None = None,
        dm_thread_ts: str | None = None,
        trello_card: Any = None,
    ):
        """presentation이 전달되지 않은 호출(워처 등)을 위해 PresentationContext를 자동 구성.

        slack_client가 없으면 RuntimeError를 발생시킵니다.
        """
        if self._slack_client is None:
            raise RuntimeError(
                "SoulstreamBackendImpl에 slack_client가 설정되지 않아 "
                "PresentationContext를 자동 구성할 수 없습니다. "
                "init_plugin_backends 호출 시 slack_client를 전달하세요."
            )

        from seosoyoung.slackbot.presentation.types import PresentationContext

        client = self._slack_client

        def say(*, text: str, thread_ts: str | None = None, **kw):
            client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                **kw,
            )

        return PresentationContext(
            channel=channel,
            thread_ts=thread_ts,
            msg_ts=msg_ts,
            say=say,
            client=client,
            effective_role=role,
            session_id=session_id,
            last_msg_ts=thread_ts,
            main_msg_ts=msg_ts,
            is_trello_mode=True,
            trello_card=trello_card,
            dm_channel_id=dm_channel_id,
            dm_thread_ts=dm_thread_ts,
        )

    async def run(
        self,
        prompt: str,
        channel: str,
        thread_ts: str,
        role: str = "admin",
        session_id: str | None = None,
        on_compact=None,
        context: list[dict] | None = None,
        folder_id: str | None = None,
        system_prompt: str | None = None,
        agent_id: str | None = None,
        caller_info: dict | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """Execute Claude Code with the given prompt.

        Args:
            text_only (bool, kwarg): True이면 Slack 게시 없이 텍스트만 생성합니다.
                presentation을 None으로 설정하여 executor가 결과를 슬랙에 게시하지 않으며,
                on_result 콜백으로 출력 텍스트를 캡처하여 RunResult.output에 담아 반환합니다.
        """
        text_only = kwargs.pop("text_only", False)
        model = kwargs.pop("model", None)
        _system_prompt = system_prompt
        _folder_id = folder_id
        _agent_id = agent_id

        try:
            loop = asyncio.get_running_loop()

            # Get or use provided session_id
            if session_id is None:
                session = self._session_manager.get(thread_ts)
                if session:
                    session_id = session.session_id

            # on_result_fn은 text_only 모드에서만 사용 (capture_result).
            # text_only=False일 때는 None이 정상 — executor가 _process_result()로 자체 처리.
            on_result_fn = None

            # 블록 단위 utterance 매치 누적 (text_only 모드에서만 사용).
            # 사이클 260518.01: 누적 transcript 정책 폐기 — thinking / text_start~end /
            # complete 각 블록의 *그 블록 텍스트만*에서 ``<utterance>`` 매치 추출.
            # 우발 토큰이 다른 블록의 닫힘 태그와 짝지어지지 않는다.
            captured_utterances: list[str] = []
            # text 블록 버퍼 — text_start ~ text_end 사이 delta 누적, text_end에서 처리.
            text_block_buffer: list[str] = []

            if text_only:
                # text_only 모드: presentation 없이 실행하여 슬랙 게시를 건너뜀
                # on_result 콜백으로 출력 텍스트를 캡처
                captured_output: list[str] = []

                # async/sync 경계 안전성 근거:
                #   self._executor 내부는 run_in_new_loop(coro) →
                #   별도 스레드에서 asyncio.run으로 새 이벤트 루프를 띄워 SSE 처리
                #   코루틴을 실행한다 (utils/async_bridge.py:13-43).
                #   service_client.py에서 ``await on_thinking(...)`` /
                #   ``await on_text_delta(...)`` / ``await on_text_end(...)`` 호출은
                #   그 새 이벤트 루프 안에서 발생하므로 async 콜백 정의는 안전.
                #   누적기는 list.append/extend만 수행하여 GIL로 thread-safe.
                # kwargs.pop으로 빼서 비-text_only 분기 진입 시(이 분기는 take되지
                # 않지만, 안전상) executor에 중복 전달되지 않도록 정리. 본 분기 안에서는
                # 게이트 콜백만 executor에 전달한다 (정본 하나).
                caller_on_text_delta = kwargs.pop("on_text_delta", None)
                caller_on_thinking = kwargs.pop("on_thinking", None)
                caller_on_text_start = kwargs.pop("on_text_start", None)
                caller_on_text_end = kwargs.pop("on_text_end", None)

                from seosoyoung.plugin_sdk.utterance import (
                    extract_utterance_matches,
                )

                def _flush_text_buffer() -> None:
                    """잔여 buffer를 추출·비움. text_start / text_end / 종료 fallback에서 공통 사용.

                    SSE 이벤트가 사실상 단일 thread 순차 처리되어 ``text_end`` 누락은
                    드물지만, 블록 경계 boundary signal로 ``text_start``를 추가해
                    두 트리오의 텍스트가 한 블록으로 잘못 합쳐지는 동질 결함을 차단한다
                    (code-reviewer P2 권고, 사이클 260518.01).
                    """
                    if text_block_buffer:
                        block_text = "".join(text_block_buffer)
                        text_block_buffer.clear()
                        captured_utterances.extend(
                            extract_utterance_matches(block_text)
                        )

                def capture_result(result, _thread_ts, _user_message):
                    out = result.output or ""
                    captured_output.append(out)
                    # complete 블록: final output 안에서도 매치 검색.
                    # text 블록에 이미 같은 본문이 잡혔어도 backend는 dedupe하지 않는다 —
                    # 호출자(``_execute_intervene``)가 strip 동일성으로 1회만 게시.
                    if out:
                        captured_utterances.extend(extract_utterance_matches(out))

                async def _on_thinking_block(text, _eid):
                    # thinking 블록: 한 이벤트 = 한 블록. 즉시 매치 검색.
                    if text:
                        captured_utterances.extend(extract_utterance_matches(text))
                    if caller_on_thinking:
                        await caller_on_thinking(text, _eid)

                async def _on_text_start_block(_eid):
                    # 새 text 블록 진입 — 직전 블록 buffer에 잔여가 있으면 먼저 flush.
                    # ``text_end`` 누락 시 두 트리오가 한 블록으로 합쳐지는 결함 차단.
                    _flush_text_buffer()
                    if caller_on_text_start:
                        await caller_on_text_start(_eid)

                async def _on_text_delta_buffer(text, _eid):
                    # text 블록 진행 중 — buffer에 누적만. 매치는 text_end에서.
                    if text:
                        text_block_buffer.append(text)
                    if caller_on_text_delta:
                        await caller_on_text_delta(text, _eid)

                async def _on_text_end_block(_eid):
                    # text 블록 종료 — buffer 전체에서 매치 검색 후 비움.
                    _flush_text_buffer()
                    if caller_on_text_end:
                        await caller_on_text_end(_eid)

                await loop.run_in_executor(
                    None,
                    lambda: self._executor(
                        prompt=prompt,
                        thread_ts=thread_ts,
                        msg_ts=kwargs.get("msg_ts", thread_ts),
                        on_compact=_noop_compact,
                        presentation=None,
                        session_id=session_id,
                        role=role,
                        context=context,
                        on_result=capture_result,
                        on_text_start=_on_text_start_block,
                        on_text_delta=_on_text_delta_buffer,
                        on_text_end=_on_text_end_block,
                        on_thinking=_on_thinking_block,
                        model=model,
                        folder_id=_folder_id,
                        system_prompt=_system_prompt,
                        profile=_agent_id,
                        caller_info=caller_info,
                    ),
                )
            else:
                # Resolve presentation context
                presentation = kwargs.get("presentation")
                if presentation is None:
                    presentation = self._build_presentation(
                        channel=channel,
                        thread_ts=thread_ts,
                        msg_ts=kwargs.get("msg_ts", thread_ts),
                        session_id=session_id,
                        role=role,
                        dm_channel_id=kwargs.get("dm_channel_id"),
                        dm_thread_ts=kwargs.get("dm_thread_ts"),
                        trello_card=kwargs.get("trello_card"),
                    )

                # Auto-build event callbacks when update_message_fn is available
                if self._update_message_fn is not None:
                    from seosoyoung.slackbot.presentation.execution import (
                        run_with_event_callbacks,
                    )

                    await loop.run_in_executor(
                        None,
                        lambda: run_with_event_callbacks(
                            presentation,
                            self._executor,
                            dict(
                                prompt=prompt,
                                thread_ts=thread_ts,
                                msg_ts=kwargs.get("msg_ts", thread_ts),
                                presentation=presentation,
                                session_id=session_id,
                                role=role,
                                context=context,
                                on_result=on_result_fn,
                                folder_id=_folder_id,
                                system_prompt=_system_prompt,
                                profile=_agent_id,
                                caller_info=caller_info,
                            ),
                            on_compact_override=on_compact,
                        ),
                    )
                else:
                    # update_message_fn 없음 — 세분화 콜백 없이 실행
                    await loop.run_in_executor(
                        None,
                        lambda: self._executor(
                            prompt=prompt,
                            thread_ts=thread_ts,
                            msg_ts=kwargs.get("msg_ts", thread_ts),
                            on_compact=on_compact,
                            presentation=presentation,
                            session_id=session_id,
                            role=role,
                            context=context,
                            on_result=on_result_fn,
                            folder_id=_folder_id,
                            system_prompt=_system_prompt,
                            profile=_agent_id,
                            caller_info=caller_info,
                        ),
                    )

            # Get updated session_id
            session = self._session_manager.get(thread_ts)
            new_session_id = session.session_id if session else session_id
            output = captured_output[0] if (text_only and captured_output) else ""

            # 누락 보호: text 블록이 ``text_end`` 없이 종료된 케이스(SSE 비정상 종료 등)에
            # 대비하여 잔여 buffer에서도 마지막 한 번 매치 검색.
            # 정상 흐름에서는 ``_on_text_end_block`` / ``_on_text_start_block``의
            # ``_flush_text_buffer``가 buffer를 비웠으므로 no-op.
            if text_only and text_block_buffer:
                from seosoyoung.plugin_sdk.utterance import (
                    extract_utterance_matches,
                )

                trailing = "".join(text_block_buffer)
                text_block_buffer.clear()
                captured_utterances.extend(extract_utterance_matches(trailing))

            return RunResult(
                ok=True,
                status=RunStatus.COMPLETED,
                session_id=new_session_id,
                output=output,
                utterances=list(captured_utterances) if text_only else [],
            )
        except Exception as e:
            logger.error(f"soulstream.run failed: {e}")
            return RunResult(
                ok=False,
                status=RunStatus.FAILED,
                error=str(e),
            )

    async def compact(self, session_id: str) -> CompactResult:
        """Compact a Claude Code session."""
        try:
            from seosoyoung.slackbot.soulstream import get_claude_runner

            runner = get_claude_runner()
            result = await runner.compact_session(session_id)

            if result.success:
                return CompactResult(
                    ok=True,
                    session_id=result.session_id,
                )
            else:
                return CompactResult(
                    ok=False,
                    error=result.error or "Compact failed",
                )
        except Exception as e:
            logger.error(f"soulstream.compact failed: {e}")
            return CompactResult(ok=False, error=str(e))

    def get_session_id(self, thread_ts: str) -> str | None:
        """Get the Claude Code session ID for a thread."""
        session = self._session_manager.get(thread_ts)
        return session.session_id if session else None

    def is_restart_pending(self) -> bool:
        """Check if a restart is pending."""
        return self._restart_manager.is_pending

    def get_data_dir(self) -> Path:
        """Get the data directory for plugin storage."""
        return self._data_dir


# ============================================================================
# Mention Tracking Backend Implementation
# ============================================================================


class MentionTrackingBackendImpl:
    """Mention tracking backend wrapping the existing MentionTracker."""

    def __init__(self, tracker: "MentionTracker"):
        self._tracker = tracker

    def mark(self, thread_ts: str) -> None:
        self._tracker.mark(thread_ts)

    def is_handled(self, thread_ts: str) -> bool:
        return self._tracker.is_handled(thread_ts)

    def unmark(self, thread_ts: str) -> None:
        self._tracker.unmark(thread_ts)


# ============================================================================
# Initialization
# ============================================================================


def init_plugin_backends(
    slack_client,
    executor,
    session_manager: "SessionManager",
    restart_manager,
    data_dir: Path,
    update_message_fn=None,
    mention_tracker: "MentionTracker | None" = None,
) -> None:
    """Initialize plugin SDK backends.

    Call this during startup after slack_client and executor are ready.

    Args:
        slack_client: Slack WebClient instance
        executor: ClaudeExecutor instance
        session_manager: SessionManager instance
        restart_manager: RestartManager instance
        data_dir: Data directory for plugin storage
        update_message_fn: (client, channel, ts, text, *, blocks=None) -> None
                           전달하면 워처 등에서 on_compact가 자동 생성됨
        mention_tracker: MentionTracker instance for mention tracking backend
    """
    # Initialize Slack backend
    slack_backend = SlackBackendImpl(slack_client)
    slack.set_backend(slack_backend)
    logger.info("plugin_sdk.slack backend initialized")

    # Initialize Soulstream backend
    soulstream_backend = SoulstreamBackendImpl(
        executor, session_manager, restart_manager, data_dir,
        slack_client=slack_client,
        update_message_fn=update_message_fn,
    )
    soulstream.set_backend(soulstream_backend)
    logger.info("plugin_sdk.soulstream backend initialized")

    # Initialize Mention tracking backend
    if mention_tracker is not None:
        mention_backend = MentionTrackingBackendImpl(mention_tracker)
        mention.set_backend(mention_backend)
        logger.info("plugin_sdk.mention backend initialized")
