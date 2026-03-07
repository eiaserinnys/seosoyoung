"""execution.py 유닛 테스트

run_with_event_callbacks와 wrap_on_compact_with_memory에 대한 단위 테스트.
"""

import asyncio
import logging
from unittest.mock import MagicMock, patch, call

import pytest

from seosoyoung.slackbot.presentation.execution import (
    run_with_event_callbacks,
    wrap_on_compact_with_memory,
)
from seosoyoung.slackbot.presentation.types import PresentationContext


def _make_pctx(**overrides) -> PresentationContext:
    """테스트용 PresentationContext 생성"""
    client = MagicMock()
    defaults = {
        "channel": "C123",
        "thread_ts": "1234.5678",
        "msg_ts": "1234.9999",
        "say": MagicMock(),
        "client": client,
        "effective_role": "admin",
        "session_id": "sess-001",
    }
    defaults.update(overrides)
    return PresentationContext(**defaults)


class TestRunWithEventCallbacks:
    """run_with_event_callbacks 테스트"""

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_placeholder_posted_and_cleanup_called(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """placeholder 게시 -> executor 실행 -> cleanup 순서 검증"""
        mock_post_placeholder.return_value = "ph_ts"

        mock_cleanup = MagicMock()
        mock_on_compact = MagicMock()
        mock_build_cbs.return_value = {
            "on_compact": mock_on_compact,
            "on_thinking": MagicMock(),
            "on_text_start": MagicMock(),
            "on_text_delta": MagicMock(),
            "on_text_end": MagicMock(),
            "on_tool_start": MagicMock(),
            "on_tool_result": MagicMock(),
            "cleanup": mock_cleanup,
        }

        pctx = _make_pctx()
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop"
        ) as mock_run_loop:
            run_with_event_callbacks(
                pctx, executor_fn, {"prompt": "hello"},
            )

        # placeholder 게시 확인
        mock_post_placeholder.assert_called_once_with(
            pctx.client, pctx.channel, pctx.thread_ts,
        )

        # executor 실행 확인
        executor_fn.assert_called_once()

        # cleanup 호출 확인
        mock_run_loop.assert_called_once()

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_on_compact_override_used_when_provided(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """on_compact_override가 None이 아니면 event_cbs 기본값 대신 사용"""
        mock_post_placeholder.return_value = "ph_ts"
        default_on_compact = MagicMock(name="default_on_compact")
        mock_build_cbs.return_value = {
            "on_compact": default_on_compact,
            "on_thinking": MagicMock(),
            "on_text_start": MagicMock(),
            "on_text_delta": MagicMock(),
            "on_text_end": MagicMock(),
            "on_tool_start": MagicMock(),
            "on_tool_result": MagicMock(),
            "cleanup": MagicMock(),
        }

        pctx = _make_pctx()
        custom_on_compact = MagicMock(name="custom_on_compact")
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop"
        ):
            run_with_event_callbacks(
                pctx, executor_fn, {"prompt": "hello"},
                on_compact_override=custom_on_compact,
            )

        # executor에 전달된 on_compact가 custom인지 확인
        call_kwargs = executor_fn.call_args[1]
        assert call_kwargs["on_compact"] is custom_on_compact

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_on_compact_wrapper_applied_to_override(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """override + wrapper 동시 사용 시 wrapper가 override에 적용됨"""
        mock_post_placeholder.return_value = "ph_ts"
        mock_build_cbs.return_value = {
            "on_compact": MagicMock(name="default"),
            "on_thinking": MagicMock(),
            "on_text_start": MagicMock(),
            "on_text_delta": MagicMock(),
            "on_text_end": MagicMock(),
            "on_tool_start": MagicMock(),
            "on_tool_result": MagicMock(),
            "cleanup": MagicMock(),
        }

        pctx = _make_pctx()
        custom_on_compact = MagicMock(name="custom_on_compact")
        wrapped_result = MagicMock(name="wrapped_result")
        wrapper = MagicMock(return_value=wrapped_result)
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop"
        ):
            run_with_event_callbacks(
                pctx, executor_fn, {"prompt": "hello"},
                on_compact_override=custom_on_compact,
                on_compact_wrapper=wrapper,
            )

        # wrapper가 custom_on_compact에 적용됨
        wrapper.assert_called_once_with(custom_on_compact)
        # executor에는 wrapper 결과가 전달됨
        call_kwargs = executor_fn.call_args[1]
        assert call_kwargs["on_compact"] is wrapped_result

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_on_compact_wrapper_applied_to_default(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """override 없이 wrapper만 사용 시 event_cbs 기본값에 wrapper 적용"""
        mock_post_placeholder.return_value = "ph_ts"
        default_on_compact = MagicMock(name="default_on_compact")
        wrapped_result = MagicMock(name="wrapped_result")
        wrapper = MagicMock(return_value=wrapped_result)
        mock_build_cbs.return_value = {
            "on_compact": default_on_compact,
            "on_thinking": MagicMock(),
            "on_text_start": MagicMock(),
            "on_text_delta": MagicMock(),
            "on_text_end": MagicMock(),
            "on_tool_start": MagicMock(),
            "on_tool_result": MagicMock(),
            "cleanup": MagicMock(),
        }

        pctx = _make_pctx()
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop"
        ):
            run_with_event_callbacks(
                pctx, executor_fn, {"prompt": "hello"},
                on_compact_wrapper=wrapper,
            )

        # wrapper가 default에 적용됨
        wrapper.assert_called_once_with(default_on_compact)
        call_kwargs = executor_fn.call_args[1]
        assert call_kwargs["on_compact"] is wrapped_result

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_cleanup_failure_does_not_propagate(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """cleanup 실패 시 예외가 전파되지 않음 (warning 로그만)"""
        mock_post_placeholder.return_value = "ph_ts"
        mock_build_cbs.return_value = {
            "on_compact": MagicMock(),
            "on_thinking": MagicMock(),
            "on_text_start": MagicMock(),
            "on_text_delta": MagicMock(),
            "on_text_end": MagicMock(),
            "on_tool_start": MagicMock(),
            "on_tool_result": MagicMock(),
            "cleanup": MagicMock(),
        }

        pctx = _make_pctx()
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop",
            side_effect=RuntimeError("loop closed"),
        ):
            # 예외가 전파되지 않아야 함
            run_with_event_callbacks(
                pctx, executor_fn, {"prompt": "hello"},
            )

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_event_callbacks_injected_to_executor(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """on_thinking, on_text_start 등 세분화 콜백이 executor에 주입됨"""
        mock_post_placeholder.return_value = "ph_ts"
        mock_thinking = MagicMock(name="on_thinking")
        mock_text_start = MagicMock(name="on_text_start")
        mock_text_delta = MagicMock(name="on_text_delta")
        mock_text_end = MagicMock(name="on_text_end")
        mock_tool_start = MagicMock(name="on_tool_start")
        mock_tool_result = MagicMock(name="on_tool_result")
        mock_build_cbs.return_value = {
            "on_compact": MagicMock(),
            "on_thinking": mock_thinking,
            "on_text_start": mock_text_start,
            "on_text_delta": mock_text_delta,
            "on_text_end": mock_text_end,
            "on_tool_start": mock_tool_start,
            "on_tool_result": mock_tool_result,
            "cleanup": MagicMock(),
        }

        pctx = _make_pctx()
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop"
        ):
            run_with_event_callbacks(
                pctx, executor_fn, {"prompt": "hello"},
            )

        call_kwargs = executor_fn.call_args[1]
        assert call_kwargs["on_thinking"] is mock_thinking
        assert call_kwargs["on_text_start"] is mock_text_start
        assert call_kwargs["on_text_delta"] is mock_text_delta
        assert call_kwargs["on_text_end"] is mock_text_end
        assert call_kwargs["on_tool_start"] is mock_tool_start
        assert call_kwargs["on_tool_result"] is mock_tool_result

    @patch("seosoyoung.slackbot.presentation.execution.build_event_callbacks")
    @patch("seosoyoung.slackbot.presentation.execution.post_initial_placeholder")
    def test_executor_kwargs_passed_through(
        self, mock_post_placeholder, mock_build_cbs,
    ):
        """executor_kwargs의 추가 파라미터가 executor에 전달됨"""
        mock_post_placeholder.return_value = "ph_ts"
        mock_build_cbs.return_value = {
            "on_compact": MagicMock(),
            "on_thinking": MagicMock(),
            "on_text_start": MagicMock(),
            "on_text_delta": MagicMock(),
            "on_text_end": MagicMock(),
            "on_tool_start": MagicMock(),
            "on_tool_result": MagicMock(),
            "cleanup": MagicMock(),
        }

        pctx = _make_pctx()
        executor_fn = MagicMock()

        with patch(
            "seosoyoung.utils.async_bridge.run_in_new_loop"
        ):
            run_with_event_callbacks(
                pctx, executor_fn,
                {"prompt": "hello", "thread_ts": "ts1", "extra_arg": 42},
            )

        call_kwargs = executor_fn.call_args[1]
        assert call_kwargs["prompt"] == "hello"
        assert call_kwargs["thread_ts"] == "ts1"
        assert call_kwargs["extra_arg"] == 42


class TestWrapOnCompactWithMemory:
    """wrap_on_compact_with_memory 테스트"""

    def test_no_pm_returns_original(self):
        """pm=None이면 원본 on_compact 그대로 반환"""
        original = MagicMock(name="original_on_compact")
        result = wrap_on_compact_with_memory(original, None, "1234.5678")
        assert result is original

    def test_empty_plugins_returns_original(self):
        """pm.plugins가 빈 dict이면 원본 반환"""
        original = MagicMock(name="original_on_compact")
        pm = MagicMock()
        pm.plugins = {}
        result = wrap_on_compact_with_memory(original, pm, "1234.5678")
        assert result is original

    def test_no_memory_plugin_returns_original(self):
        """memory 플러그인이 없으면 원본 반환"""
        original = MagicMock(name="original_on_compact")
        pm = MagicMock()
        pm.plugins = {"other_plugin": MagicMock()}
        result = wrap_on_compact_with_memory(original, pm, "1234.5678")
        assert result is original

    @pytest.mark.asyncio
    async def test_wraps_with_memory_flag(self):
        """memory 플러그인이 있으면 on_compact_flag 호출 후 원본 실행"""
        original = MagicMock(name="original_on_compact")
        # original이 async 함수인 것처럼 동작
        async def async_original(trigger, message):
            original(trigger, message)
        memory_plugin = MagicMock()
        pm = MagicMock()
        pm.plugins = {"memory": memory_plugin}

        wrapped = wrap_on_compact_with_memory(async_original, pm, "ts_001")

        assert wrapped is not async_original
        await wrapped("auto", "compact message")

        # on_compact_flag 호출 확인
        memory_plugin.on_compact_flag.assert_called_once_with("ts_001")
        # 원본 on_compact 호출 확인
        original.assert_called_once_with("auto", "compact message")

    @pytest.mark.asyncio
    async def test_memory_flag_failure_does_not_block(self):
        """on_compact_flag 실패 시 원본 on_compact는 여전히 실행됨"""
        call_log = []

        async def async_original(trigger, message):
            call_log.append(("original", trigger, message))

        memory_plugin = MagicMock()
        memory_plugin.on_compact_flag.side_effect = RuntimeError("flag error")
        pm = MagicMock()
        pm.plugins = {"memory": memory_plugin}

        wrapped = wrap_on_compact_with_memory(async_original, pm, "ts_002")

        # 예외가 전파되지 않아야 함
        await wrapped("auto", "msg")

        # flag 실패에도 원본은 실행됨
        memory_plugin.on_compact_flag.assert_called_once_with("ts_002")
        assert len(call_log) == 1
        assert call_log[0] == ("original", "auto", "msg")

    def test_pm_with_falsy_plugins_returns_original(self):
        """pm.plugins가 None이면 원본 반환"""
        original = MagicMock(name="original_on_compact")
        pm = MagicMock()
        pm.plugins = None
        result = wrap_on_compact_with_memory(original, pm, "1234.5678")
        assert result is original
