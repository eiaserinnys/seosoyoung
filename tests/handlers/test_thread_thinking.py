"""스레드 후속 대화에서 사고 과정 업데이트 테스트

process_thread_message가 thinking 메시지를 전송하고
PresentationContext.last_msg_ts에 올바르게 설정하는지 검증합니다.
"""

import pytest
from unittest.mock import MagicMock, patch, ANY


def _make_session(**overrides):
    """테스트용 세션 mock 생성"""
    session = MagicMock()
    session.session_id = "sess_123"
    session.source_type = "thread"
    session.last_seen_ts = ""
    session.user_id = "U_USER"
    session.message_count = 1
    for k, v in overrides.items():
        setattr(session, k, v)
    return session


class TestProcessThreadMessageThinking:
    """process_thread_message의 thinking 메시지 전송 테스트"""

    @patch("seosoyoung.slackbot.handlers.message.Config")
    def test_sends_thinking_message_for_admin(self, mock_config):
        """admin 역할일 때 '소영이 생각합니다...' 메시지 전송

        run_with_event_callbacks가 placeholder + activity board 두 메시지를
        순서대로 게시하므로, 첫 번째 호출이 thinking placeholder인지 검증합니다.
        """
        from seosoyoung.slackbot.handlers.message import process_thread_message

        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "thinking_ts"}

        say = MagicMock()
        session = _make_session()
        get_user_role = MagicMock(return_value={
            "username": "tester", "role": "admin",
            "user_id": "U_USER", "allowed_tools": [],
        })
        run_claude = MagicMock()

        event = {
            "user": "U_USER",
            "text": "후속 질문입니다",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
            "channel": "C_TEST",
        }

        result = process_thread_message(
            event, "후속 질문입니다", "1234.5678", "1234.9999",
            "C_TEST", session, say, client,
            get_user_role, run_claude,
        )

        assert result is True

        # 첫 번째 호출: thinking placeholder, 두 번째: activity board
        assert client.chat_postMessage.call_count >= 1
        first_call_kwargs = client.chat_postMessage.call_args_list[0][1]
        assert first_call_kwargs["channel"] == "C_TEST"
        assert first_call_kwargs["thread_ts"] == "1234.5678"
        assert "소영이 생각합니다" in first_call_kwargs["text"]

    @patch("seosoyoung.slackbot.handlers.message.Config")
    def test_sends_placeholder_for_viewer(self, mock_config):
        """viewer 역할일 때도 placeholder가 정상 전송됨 (Phase 2: 역할별 분기 제거)

        첫 번째 chat_postMessage 호출이 thinking placeholder인지 검증합니다.
        """
        from seosoyoung.slackbot.handlers.message import process_thread_message
        from seosoyoung.slackbot.formatting import format_initial_placeholder

        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "thinking_ts"}

        say = MagicMock()
        session = _make_session()
        get_user_role = MagicMock(return_value={
            "username": "viewer", "role": "viewer",
            "user_id": "U_VIEWER", "allowed_tools": [],
        })
        run_claude = MagicMock()

        event = {
            "user": "U_VIEWER",
            "text": "조회용 질문입니다",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
            "channel": "C_TEST",
        }

        process_thread_message(
            event, "조회용 질문입니다", "1234.5678", "1234.9999",
            "C_TEST", session, say, client,
            get_user_role, run_claude,
        )

        first_call_kwargs = client.chat_postMessage.call_args_list[0][1]
        assert first_call_kwargs["text"] == format_initial_placeholder()

    @patch("seosoyoung.slackbot.handlers.message.Config")
    def test_pctx_last_msg_ts_is_none_initially(self, mock_config):
        """PresentationContext.last_msg_ts는 None (Phase 2: placeholder ts는 내부에서 관리)"""
        from seosoyoung.slackbot.handlers.message import process_thread_message

        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "placeholder_ts"}

        say = MagicMock()
        session = _make_session()
        get_user_role = MagicMock(return_value={
            "username": "tester", "role": "admin",
            "user_id": "U_USER", "allowed_tools": [],
        })
        run_claude = MagicMock()

        event = {
            "user": "U_USER",
            "text": "후속 질문입니다",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
            "channel": "C_TEST",
        }

        process_thread_message(
            event, "후속 질문입니다", "1234.5678", "1234.9999",
            "C_TEST", session, say, client,
            get_user_role, run_claude,
        )

        # run_claude_in_session에 전달된 presentation 인자 확인
        run_claude.assert_called_once()
        call_kwargs = run_claude.call_args[1]
        pctx = call_kwargs["presentation"]
        # Phase 2 이후: last_msg_ts는 None으로 초기화되고,
        # placeholder ts는 build_event_callbacks 내부에서 관리됨
        assert pctx.last_msg_ts is None

    @patch("seosoyoung.slackbot.handlers.message.Config")
    def test_empty_message_skips_thinking(self, mock_config):
        """빈 메시지는 thinking 메시지를 전송하지 않음"""
        from seosoyoung.slackbot.handlers.message import process_thread_message

        client = MagicMock()
        say = MagicMock()
        session = _make_session()
        get_user_role = MagicMock()
        run_claude = MagicMock()

        event = {
            "user": "U_USER",
            "text": "",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
            "channel": "C_TEST",
        }

        result = process_thread_message(
            event, "", "1234.5678", "1234.9999",
            "C_TEST", session, say, client,
            get_user_role, run_claude,
        )

        assert result is False
        client.chat_postMessage.assert_not_called()
        run_claude.assert_not_called()
