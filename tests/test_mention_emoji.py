"""멘션 모드 이모지 리액션 테스트

변경 사항:
1. 멘션 수신 시 M(멘션 메시지)에 ssy-thinking 리액션 추가
2. 성공 시 ssy-thinking 제거 + ssy-happy 추가
3. 에러 시 ssy-thinking 제거 + ssy-angry 추가
4. _is_last_message 제거, _replace_thinking_message 단순화 (항상 chat_update)
"""

from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock, patch, call, AsyncMock

import pytest

from seosoyoung.claude.executor import ClaudeExecutor
from seosoyoung.claude.reaction_manager import (
    MENTION_REACTIONS,
    TRELLO_REACTIONS,
    add_reaction,
    remove_reaction,
)
from seosoyoung.claude.agent_runner import ClaudeResult


@dataclass
class FakeSession:
    thread_ts: str = "thread_123"
    session_id: Optional[str] = "session_abc"
    user_id: str = "U_TEST"
    role: str = "admin"
    channel_id: str = "C_TEST"
    username: str = "tester"
    message_count: int = 1


def make_executor(**overrides) -> ClaudeExecutor:
    """테스트용 ClaudeExecutor 생성"""
    defaults = dict(
        session_manager=MagicMock(),
        get_session_lock=MagicMock(),
        mark_session_running=MagicMock(),
        mark_session_stopped=MagicMock(),
        get_running_session_count=MagicMock(return_value=1),
        restart_manager=MagicMock(is_pending=False),
        upload_file_to_slack=MagicMock(return_value=(True, "")),
        send_long_message=MagicMock(),
        send_restart_confirmation=MagicMock(),
    )
    defaults.update(overrides)
    return ClaudeExecutor(**defaults)


def make_claude_result(**overrides) -> ClaudeResult:
    """테스트용 ClaudeResult 생성"""
    defaults = dict(
        success=True,
        output="테스트 응답",
        session_id="session_abc",
        interrupted=False,
    )
    defaults.update(overrides)
    return ClaudeResult(**defaults)


class TestMentionReactions:
    """멘션 모드 이모지 리액션 상수 테스트"""

    def test_mention_reactions_has_thinking(self):
        """MENTION_REACTIONS에 thinking 키가 있음"""
        assert "thinking" in MENTION_REACTIONS

    def test_mention_reactions_has_success(self):
        """MENTION_REACTIONS에 success 키가 있음"""
        assert "success" in MENTION_REACTIONS

    def test_mention_reactions_has_error(self):
        """MENTION_REACTIONS에 error 키가 있음"""
        assert "error" in MENTION_REACTIONS

    def test_mention_thinking_uses_planning_emoji(self):
        """thinking은 EMOJI_PLANNING(ssy-thinking) 사용"""
        assert MENTION_REACTIONS["thinking"] == TRELLO_REACTIONS["planning"]

    def test_mention_success_uses_success_emoji(self):
        """success는 EMOJI_SUCCESS(ssy-happy) 사용"""
        assert MENTION_REACTIONS["success"] == TRELLO_REACTIONS["success"]

    def test_mention_error_uses_error_emoji(self):
        """error는 EMOJI_ERROR(ssy-angry) 사용"""
        assert MENTION_REACTIONS["error"] == TRELLO_REACTIONS["error"]


class TestNormalModeSuccessEmoji:
    """일반 모드(멘션) 성공 시 이모지 처리"""

    @patch("seosoyoung.claude.executor.get_runner_for_role")
    def test_success_removes_thinking_adds_happy(self, mock_get_runner):
        """성공 시 ssy-thinking 제거 + ssy-happy 추가"""
        executor = make_executor()
        session = FakeSession()
        client = MagicMock()
        say = MagicMock()

        # chat_postMessage → 초기 메시지 ts 반환
        client.chat_postMessage.return_value = {"ts": "init_msg_ts"}

        # runner mock
        result = make_claude_result(output="응답 내용")
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        mock_get_runner.return_value = mock_runner

        # 락 획득 성공
        lock = MagicMock()
        lock.acquire.return_value = True
        executor.get_session_lock = MagicMock(return_value=lock)

        executor.run(
            session=session,
            prompt="질문",
            msg_ts="mention_msg_ts",
            channel="C_TEST",
            say=say,
            client=client,
            is_existing_thread=False,
            initial_msg_ts="init_msg_ts",
        )

        # ssy-thinking 제거 호출 확인
        client.reactions_remove.assert_any_call(
            channel="C_TEST",
            timestamp="mention_msg_ts",
            name=MENTION_REACTIONS["thinking"],
        )
        # ssy-happy 추가 호출 확인
        client.reactions_add.assert_any_call(
            channel="C_TEST",
            timestamp="mention_msg_ts",
            name=MENTION_REACTIONS["success"],
        )


class TestNormalModeErrorEmoji:
    """일반 모드(멘션) 에러 시 이모지 처리"""

    @patch("seosoyoung.claude.executor.get_runner_for_role")
    def test_error_removes_thinking_adds_angry(self, mock_get_runner):
        """에러 시 ssy-thinking 제거 + ssy-angry 추가"""
        executor = make_executor()
        session = FakeSession()
        client = MagicMock()
        say = MagicMock()

        client.chat_postMessage.return_value = {"ts": "init_msg_ts"}

        # runner mock - 에러 결과
        result = make_claude_result(success=False, output="", error="테스트 에러")
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        mock_get_runner.return_value = mock_runner

        lock = MagicMock()
        lock.acquire.return_value = True
        executor.get_session_lock = MagicMock(return_value=lock)

        executor.run(
            session=session,
            prompt="질문",
            msg_ts="mention_msg_ts",
            channel="C_TEST",
            say=say,
            client=client,
            is_existing_thread=False,
            initial_msg_ts="init_msg_ts",
        )

        # ssy-thinking 제거 호출 확인
        client.reactions_remove.assert_any_call(
            channel="C_TEST",
            timestamp="mention_msg_ts",
            name=MENTION_REACTIONS["thinking"],
        )
        # ssy-angry 추가 호출 확인
        client.reactions_add.assert_any_call(
            channel="C_TEST",
            timestamp="mention_msg_ts",
            name=MENTION_REACTIONS["error"],
        )

    @patch("seosoyoung.claude.executor.get_runner_for_role")
    def test_exception_removes_thinking_adds_angry(self, mock_get_runner):
        """예외 발생 시 ssy-thinking 제거 + ssy-angry 추가"""
        executor = make_executor()
        session = FakeSession()
        client = MagicMock()
        say = MagicMock()

        client.chat_postMessage.return_value = {"ts": "init_msg_ts"}

        # runner mock - 예외 발생
        mock_runner = MagicMock()
        mock_runner.run_sync.side_effect = RuntimeError("unexpected error")
        mock_get_runner.return_value = mock_runner

        lock = MagicMock()
        lock.acquire.return_value = True
        executor.get_session_lock = MagicMock(return_value=lock)

        executor.run(
            session=session,
            prompt="질문",
            msg_ts="mention_msg_ts",
            channel="C_TEST",
            say=say,
            client=client,
            is_existing_thread=False,
            initial_msg_ts="init_msg_ts",
        )

        # ssy-thinking 제거 호출 확인
        client.reactions_remove.assert_any_call(
            channel="C_TEST",
            timestamp="mention_msg_ts",
            name=MENTION_REACTIONS["thinking"],
        )
        # ssy-angry 추가 호출 확인
        client.reactions_add.assert_any_call(
            channel="C_TEST",
            timestamp="mention_msg_ts",
            name=MENTION_REACTIONS["error"],
        )


class TestTrelloModeEmojiUnaffected:
    """트렐로 모드의 기존 이모지 동작이 영향받지 않는지 확인"""

    @patch("seosoyoung.claude.executor.get_runner_for_role")
    def test_trello_success_uses_trello_reactions(self, mock_get_runner):
        """트렐로 모드 성공 시 TRELLO_REACTIONS 사용"""
        executor = make_executor()
        session = FakeSession()
        client = MagicMock()
        say = MagicMock()

        result = make_claude_result(output="응답")
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        mock_get_runner.return_value = mock_runner

        lock = MagicMock()
        lock.acquire.return_value = True
        executor.get_session_lock = MagicMock(return_value=lock)

        # 트렐로 카드 mock
        trello_card = MagicMock()
        trello_card.has_execute = True
        trello_card.card_name = "테스트 카드"
        trello_card.card_url = "https://trello.com/c/test"

        executor.run(
            session=session,
            prompt="질문",
            msg_ts="trello_msg_ts",
            channel="C_TEST",
            say=say,
            client=client,
            trello_card=trello_card,
        )

        # 트렐로 성공 이모지가 추가되었는지 확인
        client.reactions_add.assert_any_call(
            channel="C_TEST",
            timestamp="trello_msg_ts",
            name=TRELLO_REACTIONS["success"],
        )


class TestReplaceThinkingMessageSimplified:
    """_replace_thinking_message가 항상 chat_update만 사용하는지 확인"""

    def test_always_uses_chat_update(self):
        """_replace_thinking_message는 항상 chat_update를 호출"""
        executor = make_executor()
        client = MagicMock()

        result_ts = executor._replace_thinking_message(
            client, "C_TEST", "old_ts",
            "new text", [{"type": "section", "text": {"type": "mrkdwn", "text": "new text"}}],
        )

        client.chat_update.assert_called_once_with(
            channel="C_TEST",
            ts="old_ts",
            text="new text",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "new text"}}],
        )
        assert result_ts == "old_ts"

    def test_no_delete_called(self):
        """chat_delete가 호출되지 않음"""
        executor = make_executor()
        client = MagicMock()

        executor._replace_thinking_message(
            client, "C_TEST", "old_ts",
            "new text", [],
        )

        client.chat_delete.assert_not_called()

    def test_no_conversations_replies_called(self):
        """conversations_replies가 호출되지 않음 (_is_last_message 제거 확인)"""
        executor = make_executor()
        client = MagicMock()

        executor._replace_thinking_message(
            client, "C_TEST", "old_ts",
            "new text", [],
        )

        client.conversations_replies.assert_not_called()
        client.conversations_history.assert_not_called()

    def test_is_last_message_removed(self):
        """_is_last_message 메서드가 제거되었음"""
        executor = make_executor()
        assert not hasattr(executor, "_is_last_message")
