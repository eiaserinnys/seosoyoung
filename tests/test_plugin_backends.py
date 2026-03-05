"""SoulstreamBackendImpl 테스트

presentation이 전달되지 않은 경우 자동 구성 로직을 검증합니다.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from seosoyoung.slackbot.plugin_backends import SoulstreamBackendImpl


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
    """run()에서 on_progress/on_compact 자동 생성 테스트"""

    @pytest.mark.asyncio
    async def test_auto_builds_progress_callbacks_when_none(self):
        """on_progress/on_compact가 None이고 update_message_fn이 있으면 자동 생성"""
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

        assert on_progress is not None, "on_progress should be auto-built"
        assert on_compact is not None, "on_compact should be auto-built"
        assert callable(on_progress)
        assert callable(on_compact)

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
        """자동 생성된 콜백이 올바른 PresentationContext를 캡처하는지 확인"""
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
        on_progress = call_kwargs.kwargs.get("on_progress")

        # presentation과 on_progress 둘 다 자동 구성됨
        assert presentation is not None
        assert on_progress is not None
        # presentation의 DM 정보가 올바른지 확인
        assert presentation.dm_channel_id == "D456"
        assert presentation.dm_thread_ts == "9999.0001"
