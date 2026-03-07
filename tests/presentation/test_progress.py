"""build_event_callbacks 유닛 테스트

PresentationContext를 캡처하는 콜백의 동작을 검증합니다.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
from seosoyoung.slackbot.presentation.progress import (
    build_event_callbacks,
)


def _make_pctx(**overrides) -> PresentationContext:
    """테스트용 PresentationContext 생성"""
    client = MagicMock()
    # conversations_replies 기본 반환값: 메시지 없음 (stale 아님)
    client.conversations_replies.return_value = {"messages": []}
    defaults = {
        "channel": "C123",
        "thread_ts": "1234.5678",
        "msg_ts": "1234.9999",
        "say": MagicMock(),
        "client": client,
        "effective_role": "admin",
        "session_id": "sess-001",
        "last_msg_ts": "1234.6000",
    }
    defaults.update(overrides)
    return PresentationContext(**defaults)


class TestPresentationContextMutation:
    """PresentationContext의 mutable 필드 갱신 검증"""

    def test_pctx_fields_accessible(self):
        """PresentationContext 필드가 올바르게 접근 가능하다"""
        pctx = _make_pctx(
            user_id="U999",
            trello_card=MagicMock(card_id="card-1"),
            is_trello_mode=True,
        )

        assert pctx.channel == "C123"
        assert pctx.thread_ts == "1234.5678"
        assert pctx.user_id == "U999"
        assert pctx.is_trello_mode is True
        assert pctx.trello_card.card_id == "card-1"


# ============================================================================
# build_event_callbacks 테스트
# ============================================================================


def _make_event_cbs(mode="clean", placeholder_ts=None, **pctx_overrides):
    """테스트용 build_event_callbacks 호출 헬퍼

    Returns:
        (event_cbs dict, pctx, node_map, client)
    """
    pctx = _make_pctx(**pctx_overrides)
    node_map = SlackNodeMap()
    cbs = build_event_callbacks(pctx, node_map, mode, initial_placeholder_ts=placeholder_ts)
    return cbs, pctx, node_map, pctx.client


class TestReturnInterface:
    """build_event_callbacks 반환 인터페이스 검증"""

    def test_has_on_progress_key(self):
        """반환 dict에 on_progress 키가 있다"""
        cbs, _, _, _ = _make_event_cbs()
        assert "on_progress" in cbs
        assert callable(cbs["on_progress"])

    def test_no_cleanup_progress_key(self):
        """반환 dict에 _cleanup_progress 키가 없다"""
        cbs, _, _, _ = _make_event_cbs()
        assert "_cleanup_progress" not in cbs

    def test_has_cleanup_key(self):
        """반환 dict에 cleanup 키가 있다"""
        cbs, _, _, _ = _make_event_cbs()
        assert "cleanup" in cbs
        assert callable(cbs["cleanup"])

    def test_has_all_event_callbacks(self):
        """반환 dict에 모든 이벤트 콜백이 있다"""
        cbs, _, _, _ = _make_event_cbs()
        expected_keys = {
            "on_progress",
            "on_thinking", "on_text_start", "on_text_delta",
            "on_text_end", "on_tool_start", "on_tool_result",
            "on_input_request", "on_compact", "cleanup",
        }
        assert set(cbs.keys()) == expected_keys


class TestOnProgress:
    """on_progress 콜백 테스트: placeholder를 진행 텍스트로 갱신"""

    @pytest.mark.asyncio
    async def test_updates_placeholder_with_progress_text(self):
        """on_progress가 placeholder를 chat_update로 갱신한다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_progress", client=client,
        )

        await cbs["on_progress"]("코드를 분석합니다...")

        client.chat_update.assert_called_once()
        call_kwargs = client.chat_update.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert call_kwargs["ts"] == "ph_ts_progress"
        assert "코드를 분석합니다..." in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_no_update_without_placeholder(self):
        """placeholder_ts가 None이면 chat_update를 호출하지 않는다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts=None, client=client,
        )

        await cbs["on_progress"]("progress text")

        client.chat_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_throttles_rapid_updates(self):
        """스로틀로 빠른 연속 호출 시 첫 번째만 갱신한다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_throttle", client=client,
        )

        # 첫 번째 호출: 갱신됨
        await cbs["on_progress"]("step 1")
        assert client.chat_update.call_count == 1

        # 즉시 두 번째 호출: 스로틀에 의해 무시됨
        await cbs["on_progress"]("step 2")
        assert client.chat_update.call_count == 1

    @pytest.mark.asyncio
    async def test_update_after_throttle_interval(self):
        """스로틀 간격이 지나면 다시 갱신한다"""
        import time
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_interval", client=client,
        )

        # 첫 호출
        await cbs["on_progress"]("step 1")
        assert client.chat_update.call_count == 1

        # time.monotonic을 모킹하여 간격 경과를 시뮬레이션
        original_monotonic = time.monotonic
        try:
            time.monotonic = lambda: original_monotonic() + 2.0
            await cbs["on_progress"]("step 2")
            assert client.chat_update.call_count == 2
        finally:
            time.monotonic = original_monotonic

    @pytest.mark.asyncio
    async def test_update_failure_does_not_raise(self):
        """chat_update 실패 시 예외가 전파되지 않는다"""
        client = MagicMock()
        client.chat_update.side_effect = Exception("Slack API error")
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_fail", client=client,
        )

        # 예외가 전파되지 않아야 함
        await cbs["on_progress"]("some progress")

    @pytest.mark.asyncio
    async def test_no_update_after_cleanup(self):
        """cleanup() 후에는 on_progress가 갱신하지 않는다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_post_cleanup", client=client,
        )

        await cbs["cleanup"]()
        client.chat_update.reset_mock()

        await cbs["on_progress"]("late progress")
        client.chat_update.assert_not_called()


class TestPlaceholder:
    """초기 placeholder 메시지 라이프사이클 테스트

    Phase 2 이후: placeholder는 개별 이벤트에서 삭제되지 않고,
    cleanup() 호출 시에만 삭제된다.
    """

    @pytest.mark.asyncio
    async def test_placeholder_not_deleted_on_thinking(self):
        """on_thinking 호출 시 placeholder가 삭제되지 않는다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "thinking_ts"}
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_001", client=client,
        )

        await cbs["on_thinking"]("analyzing...", "evt1", None)

        # placeholder 삭제가 호출되지 않아야 함
        for c in client.chat_delete.call_args_list:
            assert c != call(channel="C123", ts="ph_ts_001")

    @pytest.mark.asyncio
    async def test_placeholder_not_deleted_on_text_start(self):
        """on_text_start 호출 시 placeholder가 삭제되지 않는다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "text_ts"}
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_002", client=client,
        )

        await cbs["on_text_start"]("evt1", None)

        for c in client.chat_delete.call_args_list:
            assert c != call(channel="C123", ts="ph_ts_002")

    @pytest.mark.asyncio
    async def test_placeholder_not_deleted_on_text_delta(self):
        """on_text_delta 호출 시 placeholder가 삭제되지 않는다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "thinking_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(
            placeholder_ts="ph_ts_003", client=client,
        )

        # thinking 노드를 먼저 생성
        await cbs["on_thinking"]("initial", "evt1", None)
        client.chat_delete.reset_mock()

        await cbs["on_text_delta"]("more text", "evt2", None)

        for c in client.chat_delete.call_args_list:
            assert c != call(channel="C123", ts="ph_ts_003")

    @pytest.mark.asyncio
    async def test_placeholder_not_deleted_on_tool_start(self):
        """on_tool_start 호출 시 placeholder가 삭제되지 않는다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "tool_ts"}
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_004", client=client,
        )

        await cbs["on_tool_start"]("Grep", {"pattern": "foo"}, "tu1", "evt1", None)

        for c in client.chat_delete.call_args_list:
            assert c != call(channel="C123", ts="ph_ts_004")

    @pytest.mark.asyncio
    async def test_placeholder_deleted_on_cleanup(self):
        """cleanup() 호출 시 placeholder가 삭제된다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_cleanup", client=client,
        )

        await cbs["cleanup"]()

        client.chat_delete.assert_called_once_with(channel="C123", ts="ph_ts_cleanup")

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self):
        """cleanup()을 두 번 호출해도 삭제는 한 번만 시도한다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_idem", client=client,
        )

        await cbs["cleanup"]()
        await cbs["cleanup"]()

        assert client.chat_delete.call_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_no_placeholder_no_delete(self):
        """placeholder_ts가 None이면 cleanup()이 삭제를 시도하지 않는다"""
        client = MagicMock()
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts=None, client=client,
        )

        await cbs["cleanup"]()

        client.chat_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_delete_failure_does_not_raise(self):
        """cleanup() 삭제 실패 시 예외가 전파되지 않는다"""
        client = MagicMock()
        client.chat_delete.side_effect = Exception("message_not_found")
        cbs, pctx, _, _ = _make_event_cbs(
            placeholder_ts="ph_ts_fail", client=client,
        )

        # 예외가 전파되지 않아야 함
        await cbs["cleanup"]()


class TestCompactCompletion:
    """오토 컴팩트 완료 메시지 테스트 (build_event_callbacks 기반)"""

    @pytest.mark.asyncio
    async def test_compact_stores_ts(self):
        """on_compact가 전송한 메시지의 ts를 compact_msg_ts에 저장한다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_msg_001"}
        cbs, pctx, _, _ = _make_event_cbs(client=client)

        assert pctx.compact_msg_ts is None
        await cbs["on_compact"]("auto", "compacting")
        assert pctx.compact_msg_ts == "compact_msg_001"

    @pytest.mark.asyncio
    async def test_compact_updates_previous_compact_message(self):
        """두 번째 compact 호출 시 이전 compact 메시지를 완료로 갱신한다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_msg_002"}
        cbs, pctx, _, _ = _make_event_cbs(client=client, compact_msg_ts="compact_msg_001")

        await cbs["on_compact"]("auto", "compacting again")

        # chat_update로 이전 메시지 갱신
        client.chat_update.assert_called_once()
        update_kwargs = client.chat_update.call_args[1]
        assert update_kwargs["ts"] == "compact_msg_001"
        assert "완료" in update_kwargs["text"]

        # 새 메시지 ts 저장
        assert pctx.compact_msg_ts == "compact_msg_002"

    @pytest.mark.asyncio
    async def test_compact_auto_trigger(self):
        """on_compact auto 트리거 시 자동 압축 알림"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_ts_1"}
        cbs, pctx, _, _ = _make_event_cbs(client=client)

        await cbs["on_compact"]("auto", "context compacted")

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["thread_ts"] == "1234.5678"
        assert "자동 압축" in call_kwargs["text"]
        assert pctx.compact_msg_ts == "compact_ts_1"

    @pytest.mark.asyncio
    async def test_compact_manual_trigger(self):
        """on_compact manual 트리거 시 수동 압축 알림"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_ts_2"}
        cbs, pctx, _, _ = _make_event_cbs(client=client)

        await cbs["on_compact"]("manual", "user requested compact")

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "압축" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_compact_update_failure_does_not_block(self):
        """compact 완료 갱신 실패 시 다음 처리가 계속 진행된다"""
        client = MagicMock()
        client.chat_update.side_effect = Exception("update failed")
        client.chat_postMessage.return_value = {"ts": "new_compact_ts"}
        cbs, pctx, _, _ = _make_event_cbs(client=client, compact_msg_ts="old_ts")

        # 예외가 전파되지 않고 새 메시지가 전송되어야 함
        await cbs["on_compact"]("auto", "compacting")
        assert pctx.compact_msg_ts == "new_compact_ts"

    @pytest.mark.asyncio
    async def test_compact_error_handled_gracefully(self):
        """on_compact 에러가 예외를 전파하지 않는다"""
        client = MagicMock()
        client.chat_postMessage.side_effect = Exception("Slack API error")
        cbs, pctx, _, _ = _make_event_cbs(client=client)

        # 예외가 전파되지 않아야 함
        await cbs["on_compact"]("auto", "message")


class TestThinkingComplete:
    """on_text_end 재설계: 공통 갱신 + 모드별 삭제 테스트

    SSE 이벤트 모델: thinking과 text는 같은 parent를 공유한다.
    - on_thinking(text, event_id=T, parent_event_id=P) -> node 생성
    - on_text_end(event_id=TE, parent_event_id=P) -> find_thinking_for_text(P)로 노드 검색
    """

    @pytest.mark.asyncio
    @patch("seosoyoung.slackbot.presentation.progress._event_delete_delay", return_value=0)
    async def test_emoji_changes_on_text_end_clean(self, mock_delay):
        """clean 모드: text_end 시 이모지 변경 + 내용 갱신 후 삭제"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "thinking_msg_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(mode="clean", client=client)

        # thinking 시작 (parent_event_id=None)
        await cbs["on_thinking"]("analyzing code...", "evt_t1", None)

        # text_end 트리거 — thinking과 같은 parent_event_id=None
        await cbs["on_text_end"]("evt_text_end", None)

        # chat_update가 format_thinking_complete() 결과로 호출됨
        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "thinking_msg_ts"
        ]
        assert len(update_calls) >= 1
        last_update = update_calls[-1]
        # format_thinking_complete는 done 이모지를 포함
        assert "생각합니다" in last_update[1]["text"]

        # _schedule_delete로 삭제됨
        delete_calls = [
            c for c in client.chat_delete.call_args_list
            if c[1].get("ts") == "thinking_msg_ts"
        ]
        assert len(delete_calls) == 1

    @pytest.mark.asyncio
    async def test_emoji_changes_on_text_end_keep(self):
        """keep 모드: text_end 시 이모지 변경, 삭제 안 함"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "thinking_msg_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(mode="keep", client=client)

        # thinking 시작 (parent_event_id=None)
        await cbs["on_thinking"]("analyzing...", "evt_t1", None)

        # text_end 트리거 — thinking과 같은 parent_event_id=None
        await cbs["on_text_end"]("evt_text_end", None)

        # chat_update가 format_thinking_complete() 결과로 호출됨
        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "thinking_msg_ts"
        ]
        assert len(update_calls) >= 1

        # chat_delete가 이 메시지에 대해 호출되지 않음
        delete_calls = [
            c for c in client.chat_delete.call_args_list
            if c[1].get("ts") == "thinking_msg_ts"
        ]
        assert len(delete_calls) == 0


class TestToolResult:
    """on_tool_result 재설계: 공통 갱신 + 모드별 삭제 테스트"""

    @pytest.mark.asyncio
    @patch("seosoyoung.slackbot.presentation.progress._event_delete_delay", return_value=0)
    async def test_content_replaced_on_result_clean(self, mock_delay):
        """clean 모드: tool_result 시 결과 교체 후 삭제"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "tool_msg_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(mode="clean", client=client)

        # tool 시작
        await cbs["on_tool_start"]("Grep", {"pattern": "error"}, "tu_001", "evt_t1", None)

        # tool 결과 수신
        await cbs["on_tool_result"]("3 matches found", "tu_001", False, "evt_result", "evt_t1")

        # chat_update가 format_tool_result() 결과로 호출됨
        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "tool_msg_ts"
        ]
        assert len(update_calls) >= 1
        last_update = update_calls[-1]
        assert "Grep" in last_update[1]["text"]

        # _schedule_delete로 삭제됨
        delete_calls = [
            c for c in client.chat_delete.call_args_list
            if c[1].get("ts") == "tool_msg_ts"
        ]
        assert len(delete_calls) == 1

    @pytest.mark.asyncio
    async def test_content_replaced_on_result_keep(self):
        """keep 모드: tool_result 시 결과 교체, 삭제 안 함"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "tool_msg_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(mode="keep", client=client)

        # tool 시작
        await cbs["on_tool_start"]("Read", {"file_path": "/a/b.py"}, "tu_002", "evt_t2", None)

        # tool 결과 수신
        await cbs["on_tool_result"]("file content here", "tu_002", False, "evt_result", "evt_t2")

        # chat_update가 format_tool_result() 결과로 호출됨
        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "tool_msg_ts"
        ]
        assert len(update_calls) >= 1

        # chat_delete가 이 메시지에 대해 호출되지 않음
        delete_calls = [
            c for c in client.chat_delete.call_args_list
            if c[1].get("ts") == "tool_msg_ts"
        ]
        assert len(delete_calls) == 0

    @pytest.mark.asyncio
    async def test_tool_error_result_displays_error(self):
        """tool_result에서 is_error=True일 때 에러 포맷으로 표시"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "tool_msg_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(mode="keep", client=client)

        await cbs["on_tool_start"]("Bash", {"command": "exit 1"}, "tu_003", "evt_t3", None)
        await cbs["on_tool_result"]("command failed", "tu_003", True, "evt_result", "evt_t3")

        update_calls = [
            c for c in client.chat_update.call_args_list
            if c[1].get("ts") == "tool_msg_ts"
        ]
        assert len(update_calls) >= 1
        last_text = update_calls[-1][1]["text"]
        # format_tool_result(is_error=True)는 :x: 이모지를 사용
        assert ":x:" in last_text


class TestOnInputRequest:
    """on_input_request 콜백 테스트"""

    @pytest.mark.asyncio
    async def test_posts_block_kit_message(self):
        """on_input_request가 Block Kit 버튼 메시지를 게시"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "ir_msg_ts"}
        cbs, pctx, node_map, _ = _make_event_cbs(client=client)

        questions = [{"question": "어떤 방향?", "options": [{"label": "A"}, {"label": "B"}]}]
        await cbs["on_input_request"]("req-001", questions, "sess-001")

        # chat_postMessage가 blocks 파라미터로 호출됨
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "blocks" in call_kwargs
        assert call_kwargs["channel"] == pctx.channel
        assert call_kwargs["thread_ts"] == pctx.thread_ts

    @pytest.mark.asyncio
    async def test_registers_in_node_map(self):
        """on_input_request가 node_map에 InputRequestNode를 등록"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "ir_msg_ts_2"}
        cbs, pctx, node_map, _ = _make_event_cbs(client=client)

        questions = [{"question": "Q1", "options": [{"label": "Yes"}]}]
        await cbs["on_input_request"]("req-002", questions, "sess-002")

        node = node_map.find_input_request("req-002")
        assert node is not None
        assert node.msg_ts == "ir_msg_ts_2"
        assert node.agent_session_id == "sess-002"
        assert node.questions == questions
        assert node.answered is False

    @pytest.mark.asyncio
    async def test_empty_questions_no_post(self):
        """빈 질문 목록이면 메시지를 게시하지 않음"""
        client = MagicMock()
        cbs, pctx, node_map, _ = _make_event_cbs(client=client)

        await cbs["on_input_request"]("req-003", [], "sess-003")

        # chat_postMessage가 on_input_request에서 호출되지 않아야 함
        # (placeholder를 위한 호출은 있을 수 있으므로 blocks 파라미터 검사)
        for call_args in client.chat_postMessage.call_args_list:
            if "blocks" in (call_args[1] if len(call_args) > 1 else {}):
                pytest.fail("빈 질문이면 블록 메시지를 게시하면 안 됨")

    @pytest.mark.asyncio
    async def test_post_failure_does_not_raise(self):
        """게시 실패 시 예외가 전파되지 않음"""
        client = MagicMock()
        client.chat_postMessage.side_effect = Exception("Slack API error")
        cbs, pctx, node_map, _ = _make_event_cbs(client=client)

        questions = [{"question": "Q", "options": [{"label": "A"}]}]
        # 예외가 전파되지 않아야 함
        await cbs["on_input_request"]("req-004", questions, "sess-004")
