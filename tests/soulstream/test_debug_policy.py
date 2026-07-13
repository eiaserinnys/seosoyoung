"""Slack에 게시 가능한 Soulstream debug 메시지 정책 테스트."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.soulstream.debug_policy import is_user_facing_debug_message
from seosoyoung.slackbot.soulstream.engine_types import ClaudeResult
from seosoyoung.slackbot.soulstream.executor import ClaudeExecutor
from seosoyoung.slackbot.soulstream.session import SessionManager, SessionRuntime


def _make_executor(tmp_path):
    return ClaudeExecutor(
        session_manager=SessionManager(session_dir=tmp_path / "sessions"),
        session_runtime=SessionRuntime(),
        restart_manager=MagicMock(),
        send_long_message=MagicMock(),
        send_restart_confirmation=MagicMock(),
        update_message_fn=MagicMock(),
    )


def _make_pctx() -> PresentationContext:
    return PresentationContext(
        channel="C123",
        thread_ts="1234.5678",
        msg_ts="1234.0001",
        say=MagicMock(),
        client=MagicMock(),
        effective_role="admin",
        session_id="sess-001",
    )


async def _noop_compact(_trigger, _message):
    pass


@pytest.mark.parametrize(
    "message",
    [
        "rate limit warning: 80% used",
        "⚠️ rate_limit `rate_limited` (CLI 자체 처리 중, type=five_hour)",
        "⚠️ 주간 사용량 중 80%를 넘었습니다",
    ],
)
def test_user_facing_rate_limit_debug_is_allowed(message):
    assert is_user_facing_debug_message(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "Ignored Codex app-server notification: configWarning",
        "Ignored Codex app-server notification: future/unknownDebug",
        "[low:rate_limit] internal notification",
        "ordinary debug info",
        "",
    ],
)
def test_internal_or_unknown_debug_is_rejected(message):
    assert is_user_facing_debug_message(message) is False


def test_internal_and_unknown_debug_not_sent_to_slack(tmp_path):
    """Codex 내부 상태와 미래 unknown debug는 Slack 게시 경계를 통과하지 않음"""
    executor = _make_executor(tmp_path)
    executor.session_manager.create(
        thread_ts="1234.5678",
        channel_id="C123",
        user_id="U123",
        role="admin",
    )
    pctx = _make_pctx()
    captured_on_debug = None

    async def mock_execute(**kwargs):
        nonlocal captured_on_debug
        captured_on_debug = kwargs.get("on_debug")
        return ClaudeResult(success=True, output="done", session_id="sess-1")

    mock_adapter = MagicMock()
    mock_adapter.execute = mock_execute

    with patch.object(executor, "_get_service_adapter", return_value=mock_adapter):
        executor._execute_remote(
            "1234.5678", "hello",
            on_compact=_noop_compact,
            presentation=pctx,
            session_id="sess-001",
            user_message=None,
            on_result=None,
        )

    assert captured_on_debug is not None
    internal_messages = [
        "Ignored Codex app-server notification: configWarning",
        "Ignored Codex app-server notification: remoteControl/status/changed",
        "Ignored Codex app-server notification: mcpServer/startupStatus/updated",
        "Ignored Codex app-server notification: thread/tokenUsage/updated",
        "Ignored Codex app-server notification: account/rateLimits/updated",
        "Ignored Codex app-server notification: future/unknownDebug",
    ]

    loop = asyncio.new_event_loop()
    try:
        for message in internal_messages:
            loop.run_until_complete(captured_on_debug(message))
    finally:
        loop.close()

    pctx.client.chat_postMessage.assert_not_called()
