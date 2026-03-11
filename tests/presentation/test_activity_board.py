"""ActivityBoard 단위 테스트

플레이스홀더 B의 항목 관리 및 슬랙 메시지 갱신 동작을 검증합니다.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, call

from seosoyoung.slackbot.presentation.activity_board import (
    ActivityBoard,
    BOARD_EMPTY_TEXT,
)


def _make_board(client=None, channel="C123", msg_ts="board_ts"):
    """테스트용 ActivityBoard 생성"""
    if client is None:
        client = MagicMock()
    return ActivityBoard(client, channel, msg_ts), client


class TestProperties:
    """기본 속성 검증"""

    def test_msg_ts(self):
        """msg_ts 프로퍼티가 생성 시 전달된 값을 반환"""
        board, _ = _make_board(msg_ts="1234.5678")
        assert board.msg_ts == "1234.5678"


class TestAdd:
    """add() 동작 검증"""

    def test_add_renders_and_syncs(self):
        """add 호출 시 항목이 렌더링되어 메시지가 갱신된다"""
        board, client = _make_board()
        board.add("item_1", "> thinking...")

        client.chat_update.assert_called_once()
        kwargs = client.chat_update.call_args[1]
        assert kwargs["ts"] == "board_ts"
        assert "> thinking..." in kwargs["text"]

    def test_add_multiple_items(self):
        """여러 항목이 줄바꿈으로 합쳐져 렌더링된다"""
        board, client = _make_board()
        board.add("item_1", "first")
        board.add("item_2", "second")

        # 마지막 갱신에 두 항목이 모두 포함
        last_call = client.chat_update.call_args_list[-1]
        text = last_call[1]["text"]
        assert "first" in text
        assert "second" in text


class TestUpdate:
    """update() 동작 검증"""

    def test_update_changes_content(self):
        """update 호출 시 해당 항목의 내용이 교체된다"""
        board, client = _make_board()
        board.add("item_1", "initial")
        client.chat_update.reset_mock()

        board.update("item_1", "updated")

        client.chat_update.assert_called_once()
        text = client.chat_update.call_args[1]["text"]
        assert "updated" in text
        assert "initial" not in text

    def test_update_nonexistent_item_skips_sync(self):
        """존재하지 않는 항목 update 시 sync를 건너뜀"""
        board, client = _make_board()
        board.add("item_1", "content")
        client.chat_update.reset_mock()

        # 존재하지 않는 항목 update — sync가 호출되지 않음
        board.update("nonexistent", "new_content")
        client.chat_update.assert_not_called()


class TestRemove:
    """remove() 동작 검증"""

    def test_remove_item(self):
        """remove 호출 시 항목이 제거되고 메시지가 갱신된다"""
        board, client = _make_board()
        board.add("item_1", "first")
        board.add("item_2", "second")
        client.chat_update.reset_mock()

        board.remove("item_1")

        text = client.chat_update.call_args[1]["text"]
        assert "first" not in text
        assert "second" in text

    def test_remove_last_item_shows_empty(self):
        """마지막 항목 제거 시 BOARD_EMPTY_TEXT가 표시된다"""
        board, client = _make_board()
        board.add("item_1", "only item")
        client.chat_update.reset_mock()

        board.remove("item_1")

        text = client.chat_update.call_args[1]["text"]
        assert text == BOARD_EMPTY_TEXT

    def test_remove_nonexistent_no_error(self):
        """존재하지 않는 항목 제거 시 에러 없이 동작"""
        board, client = _make_board()
        board.add("item_1", "content")
        client.chat_update.reset_mock()

        board.remove("nonexistent")  # 에러 없음
        client.chat_update.assert_called_once()


class TestScheduleRemove:
    """schedule_remove() 동작 검증"""

    @pytest.mark.asyncio
    async def test_schedule_remove_zero_delay(self):
        """delay=0일 때 즉시 항목이 제거된다"""
        board, client = _make_board()
        board.add("item_1", "content")
        client.chat_update.reset_mock()

        board.schedule_remove("item_1", 0)
        # create_task가 예약한 코루틴 실행
        await asyncio.sleep(0)

        # 마지막 갱신이 empty text
        text = client.chat_update.call_args[1]["text"]
        assert text == BOARD_EMPTY_TEXT

    @pytest.mark.asyncio
    async def test_schedule_remove_cancels_previous(self):
        """같은 item_id에 대한 이전 예약이 취소된다"""
        board, client = _make_board()
        board.add("item_1", "content")

        # 첫 번째 예약 (긴 딜레이)
        board.schedule_remove("item_1", 999)
        # 두 번째 예약 (즉시)
        board.schedule_remove("item_1", 0)
        await asyncio.sleep(0)

        # 항목이 제거되어 empty text 표시
        text = client.chat_update.call_args[1]["text"]
        assert text == BOARD_EMPTY_TEXT


class TestCancelAllPending:
    """cancel_all_pending() 동작 검증"""

    @pytest.mark.asyncio
    async def test_cancels_all_tasks(self):
        """cancel_all_pending 호출 시 모든 대기 중 태스크가 취소된다"""
        board, client = _make_board()
        board.add("item_1", "a")
        board.add("item_2", "b")

        board.schedule_remove("item_1", 999)
        board.schedule_remove("item_2", 999)

        board.cancel_all_pending()

        # 잠시 대기 — 취소된 태스크가 실행되지 않아야 함
        await asyncio.sleep(0.01)

        # 항목이 여전히 남아있음 (제거되지 않음)
        last_text = client.chat_update.call_args[1]["text"]
        assert "a" in last_text
        assert "b" in last_text


class TestRender:
    """_render() 동작 검증"""

    def test_empty_board_renders_empty_text(self):
        """항목이 없을 때 BOARD_EMPTY_TEXT 반환"""
        board, _ = _make_board()
        assert board._render() == BOARD_EMPTY_TEXT

    def test_single_item_renders_content(self):
        """단일 항목은 그대로 반환"""
        from seosoyoung.slackbot.presentation.activity_board import ActivityItem
        board, _ = _make_board()
        board._items = [ActivityItem("id1", "content one")]
        assert board._render() == "content one"

    def test_multiple_items_joined(self):
        """여러 항목은 \\n\\n으로 합쳐짐"""
        from seosoyoung.slackbot.presentation.activity_board import ActivityItem
        board, _ = _make_board()
        board._items = [
            ActivityItem("id1", "first"),
            ActivityItem("id2", "second"),
            ActivityItem("id3", "third"),
        ]
        assert board._render() == "first\n\nsecond\n\nthird"


class TestSyncFailure:
    """_sync() 실패 시 예외가 전파되지 않는 검증"""

    def test_sync_failure_does_not_raise(self):
        """chat_update 실패 시 예외가 전파되지 않는다"""
        client = MagicMock()
        client.chat_update.side_effect = Exception("Slack API error")
        board, _ = _make_board(client=client)

        # 예외가 전파되지 않아야 함
        board.add("item_1", "content")


class TestCleanupIntegration:
    """cleanup에서 board가 올바르게 처리되는지 통합 검증"""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_board_message(self):
        """cleanup 시 board의 메시지가 삭제된다"""
        from seosoyoung.slackbot.presentation.progress import build_event_callbacks
        from seosoyoung.slackbot.presentation.node_map import SlackNodeMap

        client = MagicMock()
        board = MagicMock()
        board.msg_ts = "board_msg_ts"

        pctx = MagicMock()
        pctx.channel = "C123"
        node_map = SlackNodeMap()

        cbs = build_event_callbacks(
            pctx, node_map, "clean",
            initial_placeholder_ts="ph_ts",
            initial_board=board,
        )

        await cbs["cleanup"]()

        # A placeholder 삭제
        assert any(
            c == call(channel="C123", ts="ph_ts")
            for c in client.chat_delete.call_args_list
        ) or any(
            c[1].get("ts") == "ph_ts"
            for c in pctx.client.chat_delete.call_args_list
        )

        # B placeholder: cancel_all_pending 호출 후 삭제
        board.cancel_all_pending.assert_called_once()
        pctx.client.chat_delete.assert_any_call(channel="C123", ts="board_msg_ts")
