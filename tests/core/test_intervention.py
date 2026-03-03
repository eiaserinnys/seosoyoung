"""인터벤션(intervention) 기능 테스트

실행 중 새 메시지 도착 시:
1. interrupt fire → 현재 실행 중단 → pending 실행
2. 연속 인터벤션 정상 처리
3. 중단된 실행의 사고 과정 메시지 정리

NOTE: bot-refactor 이후 executor는 _active_runners dict 대신
모듈 레벨 get_runner()을 사용하여 러너를 조회합니다.
get_runner_for_role() 대신 ClaudeRunner를 직접 생성합니다.
interrupt()는 인자 없이 호출됩니다.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock, patch, call

import pytest

from seosoyoung.slackbot.soulstream.executor import ClaudeExecutor
from seosoyoung.slackbot.soulstream.intervention import PendingPrompt
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.soulstream.engine_types import ClaudeResult


def make_executor(**overrides) -> ClaudeExecutor:
    """테스트용 ClaudeExecutor 생성"""
    from seosoyoung.slackbot.soulstream.session import SessionRuntime
    runtime = MagicMock(spec=SessionRuntime)
    runtime.get_session_lock = overrides.pop("get_session_lock", MagicMock())
    runtime.mark_session_running = overrides.pop("mark_session_running", MagicMock())
    runtime.mark_session_stopped = overrides.pop("mark_session_stopped", MagicMock())
    runtime.get_running_session_count = overrides.pop("get_running_session_count", MagicMock(return_value=1))
    defaults = dict(
        session_manager=MagicMock(),
        session_runtime=runtime,
        restart_manager=MagicMock(is_pending=False),
        send_long_message=MagicMock(),
        send_restart_confirmation=MagicMock(),
        update_message_fn=MagicMock(),
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


def _make_pctx(**overrides) -> PresentationContext:
    """테스트용 PresentationContext 생성 헬퍼"""
    defaults = dict(
        channel="C_TEST",
        thread_ts="thread_123",
        msg_ts="msg_456",
        say=MagicMock(),
        client=MagicMock(),
        effective_role="admin",
        session_id="session_abc",
        user_id="U_TEST",
    )
    defaults.update(overrides)
    return PresentationContext(**defaults)


def _noop_progress(text):
    pass


async def _noop_compact(trigger, message):
    pass


class TestPendingPrompts:
    """_pending_prompts dict 기본 동작"""

    def test_initial_empty(self):
        executor = make_executor()
        assert executor._pending_prompts == {}

    def test_pop_pending_empty(self):
        executor = make_executor()
        assert executor._intervention.pop_pending("thread_123") is None

    def test_pop_pending_returns_and_removes(self):
        executor = make_executor()
        pending = PendingPrompt(
            prompt="test", msg_ts="msg_1",
            on_progress=_noop_progress, on_compact=_noop_compact,
            presentation=_make_pctx(),
        )
        executor._pending_prompts["thread_123"] = pending

        result = executor._intervention.pop_pending("thread_123")
        assert result is pending
        assert "thread_123" not in executor._pending_prompts

    def test_pending_overwrite(self):
        """연속 인터벤션 시 pending은 최신 것으로 덮어쓰기"""
        executor = make_executor()
        p1 = PendingPrompt(
            prompt="first", msg_ts="msg_1",
            on_progress=_noop_progress, on_compact=_noop_compact,
            presentation=_make_pctx(),
        )
        p2 = PendingPrompt(
            prompt="second", msg_ts="msg_2",
            on_progress=_noop_progress, on_compact=_noop_compact,
            presentation=_make_pctx(),
        )
        executor._pending_prompts["t1"] = p1
        executor._pending_prompts["t1"] = p2

        result = executor._intervention.pop_pending("t1")
        assert result.prompt == "second"


class TestInterventionHandling:
    """인터벤션 시 pending 저장 + interrupt"""

    def test_intervention_no_message(self):
        """락 실패 시 텍스트 메시지 없음"""
        executor = make_executor()
        say = MagicMock()
        pctx = _make_pctx(say=say)

        executor._handle_intervention(
            "thread_123", "새 질문", "msg_456",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            role="admin",
            user_message=None,
            on_result=None,
            session_id="session_abc",
        )

        # say (텍스트 메시지)는 호출되지 않음
        say.assert_not_called()

    def test_intervention_saves_pending(self):
        """인터벤션 시 pending에 프롬프트 저장"""
        executor = make_executor()
        pctx = _make_pctx()

        executor._handle_intervention(
            "thread_123", "새 질문", "msg_456",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            role="admin",
            user_message=None,
            on_result=None,
            session_id="session_abc",
        )

        pending = executor._pending_prompts.get("thread_123")
        assert pending is not None
        assert pending.prompt == "새 질문"
        assert pending.msg_ts == "msg_456"

    def test_intervention_fires_remote_interrupt(self):
        """인터벤션 시 fire_interrupt_remote가 호출됨"""
        executor = make_executor()
        pctx = _make_pctx()

        with patch.object(executor._intervention, "fire_interrupt_remote") as mock_fire:
            with patch.object(executor, "_get_service_adapter"):
                executor._handle_intervention(
                    "thread_123", "새 질문", "msg_456",
                    on_progress=_noop_progress,
                    on_compact=_noop_compact,
                    presentation=pctx,
                    role="admin",
                    user_message=None,
                    on_result=None,
                    session_id="session_abc",
                )

        mock_fire.assert_called_once()

    def test_intervention_saves_pending(self):
        """인터벤션 시 pending에 저장됨 (remote interrupt 실패해도)"""
        executor = make_executor()
        pctx = _make_pctx()

        executor._handle_intervention(
            "thread_123", "새 질문", "msg_456",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            role="admin",
            user_message=None,
            on_result=None,
            session_id="session_abc",
        )

        # pending에는 저장됨
        assert "thread_123" in executor._pending_prompts


class TestInterventionViaRun:
    """executor.run을 통한 인터벤션 흐름"""

    def test_run_lock_failure_triggers_intervention(self):
        """run에서 락 획득 실패 시 인터벤션 발동"""
        # 락 획득 실패 설정
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = False
        executor = make_executor(
            get_session_lock=MagicMock(return_value=mock_lock)
        )

        say = MagicMock()
        pctx = _make_pctx(say=say)

        executor.run(
            prompt="새 질문",
            thread_ts="thread_123",
            msg_ts="msg_456",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
        )

        # say는 호출되지 않아야 함
        say.assert_not_called()

        # pending에 저장됨
        assert "thread_123" in executor._pending_prompts


class TestInterruptedExecution:
    """interrupt로 중단된 실행의 메시지 정리"""

    def test_handle_interrupted_normal_mode(self):
        """일반 모드에서 중단 시 update_message_fn 호출"""
        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(
            client=client,
            last_msg_ts="msg_100",
            main_msg_ts=None,
            is_trello_mode=False,
            trello_card=None,
        )

        executor._result_processor.handle_interrupted(pctx)

        update_fn = executor._result_processor.update_message_fn
        update_fn.assert_called_once()
        call_args = update_fn.call_args[0]
        assert call_args[0] is client       # client
        assert call_args[1] == "C_TEST"     # channel
        assert call_args[2] == "msg_100"    # ts
        assert "(중단됨)" in call_args[3]   # text

    def test_handle_interrupted_trello_mode(self):
        """트렐로 모드에서 중단 시 헤더 포함 메시지 업데이트"""
        executor = make_executor()
        client = MagicMock()
        trello_card = MagicMock()
        trello_card.card_name = "Test Card"
        trello_card.has_execute = True

        pctx = _make_pctx(
            client=client,
            last_msg_ts=None,
            main_msg_ts="msg_200",
            is_trello_mode=True,
            trello_card=trello_card,
        )

        with patch("seosoyoung.slackbot.soulstream.result_processor.build_trello_header", return_value="[Trello Header]"):
            executor._result_processor.handle_interrupted(pctx)

        update_fn = executor._result_processor.update_message_fn
        update_fn.assert_called_once()
        call_args = update_fn.call_args[0]
        assert call_args[2] == "msg_200"               # ts
        assert "(중단됨)" in call_args[3]               # text
        assert "[Trello Header]" in call_args[3]        # header

    def test_handle_interrupted_no_target_ts(self):
        """target_ts가 없으면 업데이트 스킵"""
        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(
            client=client,
            last_msg_ts=None,
            main_msg_ts=None,
            is_trello_mode=False,
            trello_card=None,
        )

        executor._result_processor.handle_interrupted(pctx)

        executor._result_processor.update_message_fn.assert_not_called()


class TestExecuteOnceWithInterruption:
    """_execute_once에서 interrupted 결과 처리 (remote 모드)"""

    def test_interrupted_result_calls_handle_interrupted(self):
        """result.interrupted=True일 때 handle_interrupted 호출"""
        interrupted_result = make_claude_result(interrupted=True, success=True)

        executor = make_executor()
        pctx = _make_pctx()

        with patch("seosoyoung.slackbot.soulstream.executor.run_in_new_loop", return_value=interrupted_result):
            with patch.object(executor, "_get_service_adapter"):
                with patch.object(executor._result_processor, "handle_interrupted") as mock_interrupted:
                    executor._execute_once(
                        "thread_123", "test", "msg_456",
                        on_progress=_noop_progress,
                        on_compact=_noop_compact,
                        presentation=pctx,
                        session_id="session_abc",
                        role="admin",
                        user_message=None,
                        on_result=None,
                    )

                    mock_interrupted.assert_called_once()

    def test_normal_result_calls_handle_success(self):
        """result.interrupted=False, success=True일 때 handle_success 호출"""
        normal_result = make_claude_result(interrupted=False, success=True)

        executor = make_executor()
        pctx = _make_pctx()

        with patch("seosoyoung.slackbot.soulstream.executor.run_in_new_loop", return_value=normal_result):
            with patch.object(executor, "_get_service_adapter"):
                with patch.object(executor._result_processor, "handle_success") as mock_success:
                    executor._execute_once(
                        "thread_123", "test", "msg_456",
                        on_progress=_noop_progress,
                        on_compact=_noop_compact,
                        presentation=pctx,
                        session_id="session_abc",
                        role="admin",
                        user_message=None,
                        on_result=None,
                    )

                    mock_success.assert_called_once()

    def test_execute_once_calls_execute_remote(self):
        """_execute_once에서 _execute_remote가 호출됨"""
        executor = make_executor()
        pctx = _make_pctx()

        with patch.object(executor, "_execute_remote") as mock_remote:
            executor._execute_once(
                "thread_123", "test", "msg_456",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id="session_abc",
                role="admin",
                user_message=None,
                on_result=None,
            )

        mock_remote.assert_called_once()


class TestRunWithLockPendingLoop:
    """_run_with_lock의 while 루프로 pending 처리"""

    def test_no_pending_single_execution(self):
        """pending 없으면 한 번만 실행"""
        executor = make_executor()
        pctx = _make_pctx()

        with patch.object(executor, "_execute_once") as mock_execute:
            executor._run_with_lock(
                "thread_123", "first prompt", "msg_456",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id="session_abc",
                role="admin",
                user_message=None,
                on_result=None,
            )

        assert mock_execute.call_count == 1

    def test_pending_triggers_second_execution(self):
        """pending이 있으면 두 번 실행"""
        executor = make_executor()
        pctx = _make_pctx()

        # 첫 실행 후 pending이 있도록 설정
        pending = PendingPrompt(
            prompt="second prompt",
            msg_ts="msg_2",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=_make_pctx(),
        )
        executor._pending_prompts["thread_123"] = pending

        with patch.object(executor, "_execute_once") as mock_execute:
            executor._run_with_lock(
                "thread_123", "first prompt", "msg_456",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id="session_abc",
                role="admin",
                user_message=None,
                on_result=None,
            )

        # _execute_once가 두 번 호출됨 (첫 번째 + pending)
        assert mock_execute.call_count == 2
        # pending이 비워짐
        assert "thread_123" not in executor._pending_prompts

    def test_session_running_stopped_called(self):
        """mark_session_running/stopped이 호출됨"""
        mark_running = MagicMock()
        mark_stopped = MagicMock()
        executor = make_executor(
            mark_session_running=mark_running,
            mark_session_stopped=mark_stopped,
        )
        pctx = _make_pctx()

        with patch.object(executor, "_execute_once"):
            executor._run_with_lock(
                "thread_123", "test", "msg_456",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id="session_abc",
                role="admin",
                user_message=None,
                on_result=None,
            )

        mark_running.assert_called_once()
        mark_stopped.assert_called_once()


class TestConsecutiveInterventions:
    """연속 인터벤션 (A→B→C) 처리"""

    def test_multiple_interventions_keep_latest(self):
        """연속 인터벤션 시 pending은 마지막 것만 유지"""
        executor = make_executor()

        with patch.object(executor._intervention, "fire_interrupt_remote") as mock_fire:
            with patch.object(executor, "_get_service_adapter"):
                # A → B → C 순서로 인터벤션
                for i, prompt in enumerate(["A", "B", "C"]):
                    pctx = _make_pctx(msg_ts=f"msg_{i}")
                    executor._handle_intervention(
                        "thread_123", prompt, f"msg_{i}",
                        on_progress=_noop_progress,
                        on_compact=_noop_compact,
                        presentation=pctx,
                        role="admin",
                        user_message=None,
                        on_result=None,
                        session_id="session_abc",
                    )

        # pending에는 C만 남아있어야 함
        pending = executor._pending_prompts.get("thread_123")
        assert pending is not None
        assert pending.prompt == "C"

        # fire_interrupt_remote도 3번 호출됨
        assert mock_fire.call_count == 3


class TestAgentRunnerInterruptedFlag:
    """ClaudeResult.interrupted 플래그"""

    def test_interrupted_default_false(self):
        result = ClaudeResult(success=True, output="test")
        assert result.interrupted is False

    def test_interrupted_set_true(self):
        result = ClaudeResult(success=True, output="test", interrupted=True)
        assert result.interrupted is True


class TestRemoteInterruptPath:
    """remote 인터벤션 경로 테스트"""

    def test_intervention_calls_fire_interrupt_remote(self):
        """인터벤션 시 fire_interrupt_remote가 호출됨"""
        executor = make_executor()
        pctx = _make_pctx(thread_ts="thread_abc")

        with patch.object(executor._intervention, "fire_interrupt_remote") as mock_fire:
            with patch.object(executor, "_get_service_adapter"):
                executor._handle_intervention(
                    "thread_abc", "interrupt me", "msg_456",
                    on_progress=_noop_progress,
                    on_compact=_noop_compact,
                    presentation=pctx,
                    role="admin",
                    user_message=None,
                    on_result=None,
                    session_id="session_abc",
                )

        mock_fire.assert_called_once()

    def test_intervention_always_saves_pending(self):
        """인터벤션 시 pending에 항상 저장됨"""
        executor = make_executor()
        pctx = _make_pctx()

        executor._handle_intervention(
            "thread_123", "no runner", "msg_456",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            role="admin",
            user_message=None,
            on_result=None,
            session_id="session_abc",
        )

        # pending에는 저장됨
        assert "thread_123" in executor._pending_prompts


class TestNormalSuccessWithReplace:
    """_handle_normal_success에서 _replace_thinking_message 사용 확인"""

    def test_normal_success_calls_replace_thinking(self):
        """일반 성공 처리에서 replace_thinking_message가 호출됨"""
        executor = make_executor()
        result = make_claude_result(output="짧은 응답")
        client = MagicMock()

        pctx = _make_pctx(
            client=client,
            channel="C_TEST",
            thread_ts="thread_1",
            last_msg_ts="msg_thinking",
            msg_ts="msg_1",
            is_thread_reply=True,
        )

        with patch.object(executor._result_processor, "replace_thinking_message") as mock_replace:
            executor._result_processor.handle_normal_success(pctx, result, "짧은 응답", False)

        mock_replace.assert_called_once()
        call_kwargs = mock_replace.call_args
        assert call_kwargs[1]["thread_ts"] == "thread_1"

    def test_channel_root_success_passes_thread_ts(self):
        """채널 루트 응답에서도 P가 스레드에 있으므로 thread_ts 전달"""
        executor = make_executor()
        result = make_claude_result(output="짧은 응답")
        client = MagicMock()

        pctx = _make_pctx(
            client=client,
            channel="C_TEST",
            thread_ts="thread_1",
            last_msg_ts="msg_thinking",
            msg_ts="msg_1",
            is_thread_reply=False,
        )

        with patch.object(executor._result_processor, "replace_thinking_message") as mock_replace:
            executor._result_processor.handle_normal_success(pctx, result, "짧은 응답", False)

        mock_replace.assert_called_once()
        call_kwargs = mock_replace.call_args
        assert call_kwargs[1]["thread_ts"] == "thread_1"


class TestTrelloSuccessWithReplace:
    """_handle_trello_success에서 _replace_thinking_message 사용 확인"""

    @patch("seosoyoung.slackbot.soulstream.result_processor.build_trello_header", return_value="[Header]")
    def test_trello_success_calls_replace_thinking(self, mock_header):
        """트렐로 성공 처리에서 _replace_thinking_message가 호출됨"""
        executor = make_executor()
        result = make_claude_result(output="트렐로 응답")
        trello_card = MagicMock()
        trello_card.has_execute = True
        client = MagicMock()

        pctx = _make_pctx(
            client=client,
            channel="C_TEST",
            thread_ts="thread_1",
            main_msg_ts="msg_main",
            trello_card=trello_card,
            is_trello_mode=True,
            session_id="session_abc",
        )

        with patch.object(executor._result_processor, "replace_thinking_message") as mock_replace:
            executor._result_processor.handle_trello_success(pctx, result, "트렐로 응답", False)

        mock_replace.assert_called_once()
        call_kwargs = mock_replace.call_args
        assert call_kwargs[1]["thread_ts"] is None


class TestListRunTrelloSuccessNoDelete:
    """정주행 카드 실행 시 chat_delete 방지 테스트"""

    @patch("seosoyoung.slackbot.soulstream.result_processor.build_trello_header", return_value="[Header]")
    def test_list_run_card_uses_chat_update_not_delete(self, mock_header):
        """정주행 카드(list_key='list_run')는 _replace_thinking_message를 호출하지 않음"""
        executor = make_executor()
        result = make_claude_result(output="카드 작업 완료")

        trello_card = MagicMock()
        trello_card.has_execute = True
        trello_card.list_key = "list_run"

        client = MagicMock()

        pctx = _make_pctx(
            client=client,
            channel="C_TEST",
            thread_ts="thread_1",
            main_msg_ts="msg_main",
            trello_card=trello_card,
            is_trello_mode=True,
            session_id="session_abc",
        )

        with patch.object(executor._result_processor, "replace_thinking_message") as mock_replace:
            executor._result_processor.handle_trello_success(pctx, result, "카드 작업 완료", True)

        mock_replace.assert_not_called()
        # is_list_run=True이므로 update_message_fn이 호출됨
        executor._result_processor.update_message_fn.assert_called_once()

    def test_handle_success_detects_list_run_from_trello_card(self):
        """_handle_success에서 trello_card.list_key=='list_run'이면 is_list_run=True"""
        executor = make_executor()
        result = make_claude_result(output="완료", list_run=None)

        trello_card = MagicMock()
        trello_card.has_execute = True
        trello_card.list_key = "list_run"

        client = MagicMock()

        pctx = _make_pctx(
            client=client,
            channel="C_TEST",
            thread_ts="thread_1",
            last_msg_ts="msg_1",
            main_msg_ts="msg_main",
            trello_card=trello_card,
            is_trello_mode=True,
            is_thread_reply=False,
            session_id="session_abc",
        )

        with patch.object(executor._result_processor, "handle_trello_success") as mock_trello_success:
            executor._result_processor.handle_success(pctx, result)

        mock_trello_success.assert_called_once()
        call_kwargs = mock_trello_success.call_args
        assert call_kwargs[1].get("is_list_run") is True or (len(call_kwargs[0]) >= 4 and call_kwargs[0][3] is True)


class TestIntegrationInterventionFinalResponse:
    """인터벤션 후 최종 응답 위치 통합 테스트"""

    def test_interrupted_then_pending_success(self):
        """A 중단 → B 실행 → _execute_once가 2번 호출됨"""
        executor = make_executor()

        # B를 pending에 넣어둠
        pending = PendingPrompt(
            prompt="B 질문",
            msg_ts="msg_B",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=_make_pctx(),
        )
        executor._pending_prompts["thread_123"] = pending

        pctx = _make_pctx()

        with patch.object(executor, "_execute_once") as mock_execute:
            executor._run_with_lock(
                "thread_123", "A 질문", "msg_A",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id="session_abc",
                role="admin",
                user_message=None,
                on_result=None,
            )

        # A + B = 2번 호출
        assert mock_execute.call_count == 2

    def test_triple_intervention_only_last_executes(self):
        """A→B→C 연속 인터벤션: B는 C에 의해 덮어씌워지므로 A + C = 2번 실행"""
        executor = make_executor()

        # C를 pending에 (B는 C에 의해 덮어씌워진 상태)
        pending_c = PendingPrompt(
            prompt="C 질문",
            msg_ts="msg_C",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=_make_pctx(),
        )
        executor._pending_prompts["thread_123"] = pending_c

        pctx = _make_pctx()

        with patch.object(executor, "_execute_once") as mock_execute:
            executor._run_with_lock(
                "thread_123", "A 질문", "msg_A",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id="session_abc",
                role="admin",
                user_message=None,
                on_result=None,
            )

        # A + C = 2번 호출
        assert mock_execute.call_count == 2
        # pending은 비워짐
        assert "thread_123" not in executor._pending_prompts
