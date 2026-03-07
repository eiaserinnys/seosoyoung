"""SoulstreamBackendImpl 테스트

presentation이 전달되지 않은 경우 자동 구성 로직을 검증합니다.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from seosoyoung.slackbot.formatting import build_trello_header, format_trello_progress
from seosoyoung.slackbot.plugin_backends import SoulstreamBackendImpl
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.soulstream.result_processor import ResultProcessor


def _make_backend(**overrides):
    """SoulstreamBackendImpl 인스턴스를 생성하는 헬퍼."""
    defaults = dict(
        executor=MagicMock(),
        session_manager=MagicMock(),
        restart_manager=MagicMock(is_pending=False),
        data_dir=Path("/tmp/test"),
        slack_client=MagicMock(),
    )
    defaults.update(overrides)
    return SoulstreamBackendImpl(**defaults)


class TestBuildPresentation:
    """_build_presentation 단위 테스트"""

    def test_builds_presentation_with_all_fields(self):
        """모든 필드가 올바르게 설정됨"""
        mock_client = MagicMock()
        backend = _make_backend(slack_client=mock_client)

        pctx = backend._build_presentation(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.5679",
            session_id="sess-abc",
            role="admin",
            dm_channel_id="D456",
            dm_thread_ts="9999.0001",
        )

        assert pctx.channel == "C123"
        assert pctx.thread_ts == "1234.5678"
        assert pctx.msg_ts == "1234.5679"
        assert pctx.client is mock_client
        assert pctx.effective_role == "admin"
        assert pctx.session_id == "sess-abc"
        assert pctx.is_trello_mode is True
        assert pctx.dm_channel_id == "D456"
        assert pctx.dm_thread_ts == "9999.0001"
        assert pctx.last_msg_ts == "1234.5678"
        assert pctx.main_msg_ts == "1234.5679"

    def test_builds_presentation_without_dm(self):
        """DM 정보 없이 구성"""
        backend = _make_backend()
        pctx = backend._build_presentation(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.5678",
            session_id=None,
            role="viewer",
        )

        assert pctx.dm_channel_id is None
        assert pctx.dm_thread_ts is None
        assert pctx.effective_role == "viewer"
        assert pctx.session_id is None

    def test_say_function_calls_client(self):
        """say 함수가 client.chat_postMessage를 호출함"""
        mock_client = MagicMock()
        backend = _make_backend(slack_client=mock_client)

        pctx = backend._build_presentation(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.5678",
            session_id=None,
            role="admin",
        )

        pctx.say(text="hello", thread_ts="1234.5678")
        mock_client.chat_postMessage.assert_called_once_with(
            channel="C123",
            text="hello",
            thread_ts="1234.5678",
        )

    def test_raises_without_slack_client(self):
        """slack_client가 없으면 RuntimeError"""
        backend = _make_backend(slack_client=None)

        with pytest.raises(RuntimeError, match="slack_client가 설정되지 않아"):
            backend._build_presentation(
                channel="C123",
                thread_ts="1234.5678",
                msg_ts="1234.5678",
                session_id=None,
                role="admin",
            )


class TestRunAutoPresentation:
    """run()에서 presentation 자동 구성 테스트"""

    @pytest.mark.asyncio
    async def test_auto_constructs_presentation_when_missing(self):
        """presentation kwarg가 없으면 자동 구성하여 executor에 전달"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None
        mock_client = MagicMock()

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
            slack_client=mock_client,
        )

        result = await backend.run(
            prompt="test prompt",
            channel="C123",
            thread_ts="1234.5678",
            role="admin",
        )

        # executor가 호출됐는지 확인
        mock_executor.assert_called_once()
        call_kwargs = mock_executor.call_args
        presentation = call_kwargs.kwargs.get("presentation") or call_kwargs[1].get("presentation")

        # presentation이 None이 아닌 PresentationContext여야 함
        assert presentation is not None
        assert presentation.channel == "C123"
        assert presentation.thread_ts == "1234.5678"
        assert presentation.client is mock_client

    @pytest.mark.asyncio
    async def test_uses_provided_presentation(self):
        """presentation kwarg가 있으면 그대로 사용"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None
        custom_pctx = MagicMock()

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
            presentation=custom_pctx,
        )

        call_kwargs = mock_executor.call_args
        presentation = call_kwargs.kwargs.get("presentation") or call_kwargs[1].get("presentation")
        assert presentation is custom_pctx

    @pytest.mark.asyncio
    async def test_passes_dm_info_to_presentation(self):
        """dm_channel_id, dm_thread_ts가 presentation에 반영됨"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
            dm_channel_id="D456",
            dm_thread_ts="9999.0001",
        )

        call_kwargs = mock_executor.call_args
        presentation = call_kwargs.kwargs.get("presentation") or call_kwargs[1].get("presentation")
        assert presentation.dm_channel_id == "D456"
        assert presentation.dm_thread_ts == "9999.0001"


class TestRunAutoProgressCallbacks:
    """run()에서 세분화 이벤트 콜백 자동 생성 테스트"""

    @pytest.mark.asyncio
    async def test_auto_builds_event_callbacks_when_none(self):
        """on_progress가 None이고 update_message_fn이 있으면 세분화 콜백이 자동 생성됨"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None
        mock_update_fn = MagicMock()

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
            update_message_fn=mock_update_fn,
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
            role="admin",
        )

        call_kwargs = mock_executor.call_args
        on_progress = call_kwargs.kwargs.get("on_progress")
        on_compact = call_kwargs.kwargs.get("on_compact")
        on_thinking = call_kwargs.kwargs.get("on_thinking")
        on_tool_start = call_kwargs.kwargs.get("on_tool_start")

        # on_progress는 더 이상 자동 생성하지 않음 (Phase 2: 세분화 콜백이 대체)
        assert on_progress is None, "on_progress should NOT be auto-built (replaced by granular event callbacks)"
        assert on_compact is not None, "on_compact should be auto-built"
        assert callable(on_compact)
        # 세분화 콜백이 자동 구성됨
        assert on_thinking is not None, "on_thinking should be auto-built"
        assert on_tool_start is not None, "on_tool_start should be auto-built"
        assert callable(on_thinking)
        assert callable(on_tool_start)

    @pytest.mark.asyncio
    async def test_preserves_explicit_progress_callbacks(self):
        """on_progress/on_compact가 명시적으로 전달되면 그대로 사용"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None

        explicit_progress = AsyncMock()
        explicit_compact = AsyncMock()

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
            update_message_fn=MagicMock(),
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
            on_progress=explicit_progress,
            on_compact=explicit_compact,
        )

        call_kwargs = mock_executor.call_args
        assert call_kwargs.kwargs["on_progress"] is explicit_progress
        assert call_kwargs.kwargs["on_compact"] is explicit_compact

    @pytest.mark.asyncio
    async def test_no_auto_build_without_update_message_fn(self):
        """update_message_fn이 None이면 on_progress=None 그대로 전달 (하위 호환)"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
        )

        call_kwargs = mock_executor.call_args
        assert call_kwargs.kwargs.get("on_progress") is None
        assert call_kwargs.kwargs.get("on_compact") is None

    @pytest.mark.asyncio
    async def test_auto_built_callbacks_use_correct_presentation(self):
        """자동 생성된 세분화 콜백이 올바른 PresentationContext를 캡처하는지 확인"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None
        mock_client = MagicMock()
        mock_update_fn = MagicMock()

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
            slack_client=mock_client,
            update_message_fn=mock_update_fn,
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
            role="admin",
            dm_channel_id="D456",
            dm_thread_ts="9999.0001",
        )

        call_kwargs = mock_executor.call_args
        presentation = call_kwargs.kwargs.get("presentation")
        on_thinking = call_kwargs.kwargs.get("on_thinking")

        # presentation과 세분화 콜백이 자동 구성됨
        assert presentation is not None
        assert on_thinking is not None
        # presentation의 DM 정보가 올바른지 확인
        assert presentation.dm_channel_id == "D456"
        assert presentation.dm_thread_ts == "9999.0001"


class TestBuildTrelloHeaderDefense:
    """build_trello_header에 None card 전달 시 방어 처리 테스트"""

    def test_none_card_returns_fallback_header(self):
        """card=None이면 '카드 정보 없음' 폴백 헤더 반환"""
        header = build_trello_header(None, "sess-12345678")
        assert "카드 정보 없음" in header
        assert "sess-123" in header

    def test_none_card_without_session_id(self):
        """card=None, session_id 없을 때도 에러 없이 반환"""
        header = build_trello_header(None)
        assert "카드 정보 없음" in header

    def test_normal_card_unchanged(self):
        """정상 카드는 기존 동작 유지"""
        mock_card = MagicMock()
        mock_card.card_name = "테스트 카드"
        mock_card.card_url = "https://trello.com/c/abc123"
        header = build_trello_header(mock_card, "sess-abc")
        assert "테스트 카드" in header
        assert "https://trello.com/c/abc123" in header

    def test_format_trello_progress_none_card(self):
        """format_trello_progress에 card=None 전달 시 에러 없이 반환"""
        result = format_trello_progress("진행 중...", None, "sess-abc")
        assert "카드 정보 없음" in result
        assert "진행 중..." in result


class TestBuildPresentationTrelloCard:
    """_build_presentation에 trello_card 전달 테스트"""

    def test_trello_card_set_when_provided(self):
        """trello_card가 전달되면 PresentationContext에 설정됨"""
        mock_card = MagicMock()
        mock_card.card_name = "테스트 카드"
        mock_card.card_url = "https://trello.com/c/abc123"
        backend = _make_backend()

        pctx = backend._build_presentation(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.5678",
            session_id=None,
            role="admin",
            trello_card=mock_card,
        )

        assert pctx.trello_card is mock_card
        assert pctx.is_trello_mode is True

    def test_trello_card_none_when_not_provided(self):
        """trello_card 미전달 시 None (하위호환)"""
        backend = _make_backend()

        pctx = backend._build_presentation(
            channel="C123",
            thread_ts="1234.5678",
            msg_ts="1234.5678",
            session_id=None,
            role="admin",
        )

        assert pctx.trello_card is None
        assert pctx.is_trello_mode is True


class TestRunPassesTrelloCard:
    """run()에서 trello_card kwarg 전달 테스트"""

    @pytest.mark.asyncio
    async def test_trello_card_passed_to_presentation(self):
        """run()에 trello_card kwarg를 전달하면 presentation에 설정됨"""
        mock_executor = MagicMock()
        mock_session_mgr = MagicMock()
        mock_session_mgr.get.return_value = None
        mock_card = MagicMock()
        mock_card.card_name = "테스트 카드"
        mock_card.card_url = "https://trello.com/c/abc123"

        backend = _make_backend(
            executor=mock_executor,
            session_manager=mock_session_mgr,
        )

        await backend.run(
            prompt="test",
            channel="C123",
            thread_ts="1234.5678",
            role="admin",
            trello_card=mock_card,
        )

        call_kwargs = mock_executor.call_args
        presentation = call_kwargs.kwargs.get("presentation")
        assert presentation is not None
        assert presentation.trello_card is mock_card


def _make_pctx_trello_none(**overrides):
    """trello_card=None인 트렐로 모드 PresentationContext 생성 헬퍼"""
    defaults = dict(
        channel="C123",
        thread_ts="1234.5678",
        msg_ts="1234.5678",
        say=MagicMock(),
        client=MagicMock(),
        effective_role="admin",
        session_id="sess-abc",
        last_msg_ts="1234.5678",
        main_msg_ts="1234.9999",
        is_trello_mode=True,
        trello_card=None,
    )
    defaults.update(overrides)
    return PresentationContext(**defaults)


def _make_result_processor():
    """테스트용 ResultProcessor 생성 헬퍼"""
    return ResultProcessor(
        send_long_message=MagicMock(),
        restart_manager=MagicMock(is_pending=False),
        get_running_session_count=MagicMock(return_value=1),
        send_restart_confirmation=MagicMock(),
        update_message_fn=MagicMock(),
    )


class TestResultProcessorTrelloCardNone:
    """ResultProcessor에서 trello_card=None일 때 방어 처리 테스트"""

    def test_handle_interrupted_trello_card_none(self):
        """handle_interrupted에서 trello_card=None이면 에러 없이 중단 메시지 표시"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none()

        # 에러 없이 완료되어야 함
        rp.handle_interrupted(pctx)

        # update_message_fn이 호출되어야 함
        rp.update_message_fn.assert_called()
        call_args = rp.update_message_fn.call_args
        text_arg = call_args[0][3] if len(call_args[0]) > 3 else call_args.kwargs.get("text", "")
        assert "중단됨" in text_arg

    def test_handle_trello_success_trello_card_none(self):
        """handle_trello_success에서 trello_card=None이면 에러 없이 성공 처리"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none()
        mock_result = MagicMock()
        mock_result.session_id = "sess-new"
        mock_result.list_run = None

        # 에러 없이 완료되어야 함
        rp.handle_trello_success(pctx, mock_result, "작업 완료", False)

        rp.update_message_fn.assert_called()

    def test_handle_error_trello_card_none(self):
        """handle_error에서 trello_card=None이면 에러 없이 오류 메시지 표시"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none()

        # 에러 없이 완료되어야 함
        rp.handle_error(pctx, "테스트 오류")

        rp.update_message_fn.assert_called()


class TestResultProcessorMainMsgTsNone:
    """ResultProcessor에서 main_msg_ts=None일 때 방어 처리 테스트"""

    def test_handle_interrupted_main_msg_ts_none_trello(self):
        """handle_interrupted에서 트렐로 모드 + main_msg_ts=None이면 조용히 반환"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none(main_msg_ts=None)

        rp.handle_interrupted(pctx)

        # main_msg_ts가 None이므로 update_message_fn은 호출되지 않아야 함
        rp.update_message_fn.assert_not_called()

    def test_handle_trello_success_main_msg_ts_none_falls_back_to_send(self):
        """handle_trello_success에서 main_msg_ts=None이면 send_long_message 폴백"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none(main_msg_ts=None)
        mock_result = MagicMock()
        mock_result.session_id = "sess-new"
        mock_result.list_run = None

        rp.handle_trello_success(pctx, mock_result, "작업 완료", False)

        # update_message_fn은 호출되지 않아야 함
        rp.update_message_fn.assert_not_called()
        # send_long_message로 폴백
        rp.send_long_message.assert_called_once()

    def test_handle_trello_success_main_msg_ts_none_list_run(self):
        """handle_trello_success에서 main_msg_ts=None + is_list_run이면 send_long_message 폴백"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none(main_msg_ts=None)
        mock_result = MagicMock()
        mock_result.session_id = "sess-new"
        mock_result.list_run = "📌 PLAN: test"

        rp.handle_trello_success(pctx, mock_result, "작업 완료", True)

        rp.update_message_fn.assert_not_called()
        rp.send_long_message.assert_called_once()

    def test_handle_error_main_msg_ts_none_trello_falls_back_to_say(self):
        """handle_error에서 트렐로 모드 + main_msg_ts=None이면 say로 폴백"""
        rp = _make_result_processor()
        pctx = _make_pctx_trello_none(main_msg_ts=None)

        rp.handle_error(pctx, "테스트 오류")

        # update_message_fn은 호출되지 않아야 함 (main_msg_ts가 None)
        rp.update_message_fn.assert_not_called()
        # say로 폴백
        pctx.say.assert_called_once()
        call_kwargs = pctx.say.call_args[1]
        assert "오류" in call_kwargs["text"]
