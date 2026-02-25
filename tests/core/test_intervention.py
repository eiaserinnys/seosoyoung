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

from seosoyoung.slackbot.claude.executor import ClaudeExecutor
from seosoyoung.slackbot.claude.intervention import PendingPrompt
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.claude.agent_runner import ClaudeResult


def make_executor(**overrides) -> ClaudeExecutor:
    """테스트용 ClaudeExecutor 생성"""
    from seosoyoung.slackbot.claude.session import SessionRuntime
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

    def test_intervention_fires_interrupt_with_active_runner(self):
        """인터벤션 시 get_runner가 runner를 반환하면 interrupt 호출 (동기, 인자 없음)"""
        executor = make_executor()

        mock_runner = MagicMock()
        mock_runner.interrupt.return_value = True

        pctx = _make_pctx()

        with patch("seosoyoung.slackbot.claude.agent_runner.get_runner", return_value=mock_runner):
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

        # interrupt()는 인자 없이 호출됨 (per-instance 모델)
        mock_runner.interrupt.assert_called_once()

    def test_intervention_no_runner_no_interrupt(self):
        """get_runner가 None을 반환하면 interrupt 호출 안 함"""
        executor = make_executor()
        pctx = _make_pctx()

        with patch("seosoyoung.slackbot.claude.agent_runner.get_runner", return_value=None):
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

        with patch("seosoyoung.slackbot.claude.result_processor.build_trello_header", return_value="[Trello Header]"):
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
    """_execute_once에서 interrupted 결과 처리"""

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_interrupted_result_calls_handle_interrupted(self, MockRunnerClass):
        """result.interrupted=True일 때 _handle_interrupted 호출"""
        interrupted_result = make_claude_result(interrupted=True, success=True)
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = interrupted_result
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(client=client)

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

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_normal_result_calls_handle_success(self, MockRunnerClass):
        """result.interrupted=False, success=True일 때 _handle_success 호출"""
        normal_result = make_claude_result(interrupted=False, success=True)
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = normal_result
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(client=client)

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

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_execute_once_creates_runner(self, MockRunnerClass):
        """_execute_once에서 ClaudeRunner가 생성됨"""
        result = make_claude_result()
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(client=client)

        with patch.object(executor._result_processor, "handle_success"):
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

        # ClaudeRunner가 생성되었는지 확인
        MockRunnerClass.assert_called_once()


class TestRunWithLockPendingLoop:
    """_run_with_lock의 while 루프로 pending 처리"""

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_no_pending_single_execution(self, MockRunnerClass):
        """pending 없으면 한 번만 실행"""
        result = make_claude_result()
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(client=client)

        with patch.object(executor._result_processor, "handle_success"):
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

        # run_sync이 한 번만 호출됨
        assert mock_runner.run_sync.call_count == 1

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_pending_triggers_second_execution(self, MockRunnerClass):
        """pending이 있으면 두 번 실행"""
        result = make_claude_result()
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()
        pctx = _make_pctx(client=client)

        # 첫 실행 후 pending이 있도록 설정
        pending = PendingPrompt(
            prompt="second prompt",
            msg_ts="msg_2",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=_make_pctx(client=client),
        )
        executor._pending_prompts["thread_123"] = pending

        with patch.object(executor._result_processor, "handle_success"):
            with patch.object(executor._result_processor, "handle_interrupted"):
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

        # run_sync이 두 번 호출됨 (첫 번째 + pending)
        assert mock_runner.run_sync.call_count == 2
        # pending이 비워짐
        assert "thread_123" not in executor._pending_prompts

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_session_running_stopped_called(self, MockRunnerClass):
        """mark_session_running/stopped이 호출됨"""
        result = make_claude_result()
        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = result
        MockRunnerClass.return_value = mock_runner

        mark_running = MagicMock()
        mark_stopped = MagicMock()
        executor = make_executor(
            mark_session_running=mark_running,
            mark_session_stopped=mark_stopped,
        )
        client = MagicMock()
        pctx = _make_pctx(client=client)

        with patch.object(executor._result_processor, "handle_success"):
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

        mock_runner = MagicMock()
        mock_runner.interrupt.return_value = True

        # get_runner가 mock_runner를 반환하도록 패치
        with patch("seosoyoung.slackbot.claude.agent_runner.get_runner", return_value=mock_runner):
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

        # interrupt도 3번 호출됨
        assert mock_runner.interrupt.call_count == 3


class TestAgentRunnerInterruptedFlag:
    """ClaudeResult.interrupted 플래그"""

    def test_interrupted_default_false(self):
        result = ClaudeResult(success=True, output="test")
        assert result.interrupted is False

    def test_interrupted_set_true(self):
        result = ClaudeResult(success=True, output="test", interrupted=True)
        assert result.interrupted is True


class TestModuleLevelRunnerLookup:
    """모듈 레벨 get_runner를 통한 인터벤션 테스트"""

    def test_intervention_uses_get_runner_for_interrupt(self):
        """인터벤션 시 get_runner로 runner를 찾아 interrupt 전송"""
        executor = make_executor()

        mock_runner = MagicMock()
        mock_runner.interrupt.return_value = True

        pctx = _make_pctx(thread_ts="thread_abc")

        with patch("seosoyoung.slackbot.claude.agent_runner.get_runner", return_value=mock_runner):
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

        mock_runner.interrupt.assert_called_once()

    def test_intervention_no_runner_found(self):
        """get_runner가 None이면 interrupt 호출 안 함"""
        executor = make_executor()
        pctx = _make_pctx()

        with patch("seosoyoung.slackbot.claude.agent_runner.get_runner", return_value=None):
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

    @patch("seosoyoung.slackbot.claude.result_processor.build_trello_header", return_value="[Header]")
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

    @patch("seosoyoung.slackbot.claude.result_processor.build_trello_header", return_value="[Header]")
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

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_interrupted_then_pending_success(self, MockRunnerClass):
        """A 중단 → B 실행 → 최종 응답이 올바른 위치에 표시"""
        # 첫 번째 실행은 interrupted, 두 번째는 성공
        interrupted_result = make_claude_result(interrupted=True, success=True)
        success_result = make_claude_result(interrupted=False, success=True, output="B 응답")

        mock_runner = MagicMock()
        mock_runner.run_sync.side_effect = [interrupted_result, success_result]
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()

        # B를 pending에 넣어둠
        pending = PendingPrompt(
            prompt="B 질문",
            msg_ts="msg_B",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=_make_pctx(client=client),
        )
        executor._pending_prompts["thread_123"] = pending

        pctx = _make_pctx(client=client)

        with patch.object(executor._result_processor, "handle_interrupted") as mock_interrupted:
            with patch.object(executor._result_processor, "handle_success") as mock_success:
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

        # A는 interrupted로 처리
        mock_interrupted.assert_called_once()
        # B는 success로 처리
        mock_success.assert_called_once()

    @patch("seosoyoung.slackbot.claude.executor.ClaudeRunner")
    def test_triple_intervention_only_last_executes(self, MockRunnerClass):
        """A→B→C 연속 인터벤션: A 중단, B는 덮어씌워지고, C만 실행"""
        interrupted_result = make_claude_result(interrupted=True, success=True)
        success_result = make_claude_result(interrupted=False, success=True, output="C 응답")

        mock_runner = MagicMock()
        mock_runner.run_sync.side_effect = [interrupted_result, success_result]
        MockRunnerClass.return_value = mock_runner

        executor = make_executor()
        client = MagicMock()

        # C를 pending에 (B는 C에 의해 덮어씌워진 상태)
        pending_c = PendingPrompt(
            prompt="C 질문",
            msg_ts="msg_C",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=_make_pctx(client=client),
        )
        executor._pending_prompts["thread_123"] = pending_c

        pctx = _make_pctx(client=client)

        with patch.object(executor._result_processor, "handle_interrupted"):
            with patch.object(executor._result_processor, "handle_success") as mock_success:
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

        # success는 C에 대해서만 한 번 호출됨
        mock_success.assert_called_once()
        # pending은 비워짐
        assert "thread_123" not in executor._pending_prompts
