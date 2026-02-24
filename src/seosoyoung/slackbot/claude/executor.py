"""Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.

실행 모드 (execution_mode):
- local: 기존 방식. ClaudeRunner를 직접 사용하여 로컬에서 실행.
- remote: seosoyoung-soul 서버에 HTTP/SSE로 위임하여 실행.
"""

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner
from seosoyoung.slackbot.claude.intervention import InterventionManager, PendingPrompt
from seosoyoung.slackbot.claude.result_processor import ResultProcessor
from seosoyoung.slackbot.claude.session import Session, SessionManager, SessionRuntime
from seosoyoung.slackbot.claude.message_formatter import (
    truncate_progress_text,
    format_as_blockquote,
    format_trello_progress,
    format_dm_progress,
)
from seosoyoung.slackbot.claude.types import (
    CardInfo, SlackClient, SayFunction, ProgressCallback, CompactCallback,
    UpdateMessageFn, PrepareMemoryFn, TriggerObservationFn, OnCompactOMFlagFn,
)
from seosoyoung.utils.async_bridge import run_in_new_loop

logger = logging.getLogger(__name__)


def _get_mcp_config_path() -> Optional[Path]:
    """MCP 설정 파일 경로 반환 (없으면 None)"""
    config_path = Path(__file__).resolve().parents[4] / "mcp_config.json"
    return config_path if config_path.exists() else None


@dataclass
class ExecutionContext:
    """실행 컨텍스트 - 메서드 간 전달되는 모든 실행 상태를 묶는 객체

    executor 내부 메서드들이 공유하는 상태를 하나의 객체로 캡슐화합니다.
    """
    session: Session
    channel: str
    say: SayFunction
    client: SlackClient
    msg_ts: str
    effective_role: str
    # Slack 메시지 ts 추적
    thread_ts: str = ""  # 실제 사용될 thread_ts (override 가능)
    last_msg_ts: Optional[str] = None
    main_msg_ts: Optional[str] = None  # 트렐로 모드 메인 메시지 ts
    # 트렐로 관련
    trello_card: Optional[CardInfo] = None
    is_trello_mode: bool = False
    # 스레드 관련
    is_existing_thread: bool = False
    is_thread_reply: bool = False
    initial_msg_ts: Optional[str] = None
    # DM 스레드 (트렐로 모드용)
    dm_channel_id: Optional[str] = None
    dm_thread_ts: Optional[str] = None
    dm_last_reply_ts: Optional[str] = None
    # 사용자 메시지
    user_message: Optional[str] = None
    # 콜백 (실행 중 설정)
    on_progress: Optional[ProgressCallback] = field(default=None, repr=False)
    on_compact: Optional[CompactCallback] = field(default=None, repr=False)

    @property
    def original_thread_ts(self) -> str:
        """세션의 원래 thread_ts"""
        return self.session.thread_ts


class ClaudeExecutor:
    """Claude Code 실행기

    세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
    인터벤션 기능을 지원합니다.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        session_runtime: SessionRuntime,
        restart_manager,
        send_long_message: Callable,
        send_restart_confirmation: Callable,
        update_message_fn: UpdateMessageFn,
        *,
        execution_mode: str = "local",
        role_tools: Optional[dict] = None,
        show_context_usage: bool = False,
        soul_url: str = "",
        soul_token: str = "",
        soul_client_id: str = "",
        restart_type_update=None,
        restart_type_restart=None,
        trello_watcher_ref: Optional[Callable] = None,
        list_runner_ref: Optional[Callable] = None,
        prepare_memory_fn: Optional[PrepareMemoryFn] = None,
        trigger_observation_fn: Optional[TriggerObservationFn] = None,
        on_compact_om_flag: Optional[OnCompactOMFlagFn] = None,
    ):
        self.session_manager = session_manager
        self.session_runtime = session_runtime
        self.restart_manager = restart_manager
        self.send_long_message = send_long_message
        self.send_restart_confirmation = send_restart_confirmation
        self.update_message_fn = update_message_fn
        self.execution_mode = execution_mode
        self.role_tools = role_tools or {}
        self.show_context_usage = show_context_usage
        self.soul_url = soul_url
        self.soul_token = soul_token
        self.soul_client_id = soul_client_id
        self.trello_watcher_ref = trello_watcher_ref
        self.list_runner_ref = list_runner_ref
        self.prepare_memory_fn = prepare_memory_fn
        self.trigger_observation_fn = trigger_observation_fn
        self.on_compact_om_flag = on_compact_om_flag

        # 하위 호환 프로퍼티 (기존 코드에서 직접 접근하는 경우 대비)
        self.get_session_lock = session_runtime.get_session_lock
        self.mark_session_running = session_runtime.mark_session_running
        self.mark_session_stopped = session_runtime.mark_session_stopped
        self.get_running_session_count = session_runtime.get_running_session_count

        # 인터벤션 관리자
        self._intervention = InterventionManager()
        # 하위 호환 프로퍼티 (테스트에서 직접 접근)
        self._pending_prompts = self._intervention.pending_prompts
        # 결과 처리자
        self._result_processor = ResultProcessor(
            send_long_message=send_long_message,
            restart_manager=restart_manager,
            get_running_session_count=session_runtime.get_running_session_count,
            send_restart_confirmation=send_restart_confirmation,
            update_message_fn=update_message_fn,
            trello_watcher_ref=trello_watcher_ref,
            show_context_usage=show_context_usage,
            restart_type_update=restart_type_update,
            restart_type_restart=restart_type_restart,
        )
        # Remote 모드: ClaudeServiceAdapter (lazy 초기화)
        self._service_adapter: Optional[object] = None
        self._adapter_lock = threading.Lock()
        # Remote 모드: 실행 중인 request_id 추적 (인터벤션용)
        self._active_remote_requests: dict[str, str] = {}  # thread_ts -> request_id

    def run(
        self,
        session: Session,
        prompt: str,
        msg_ts: str,
        channel: str,
        say,
        client,
        role: str = None,
        trello_card: CardInfo = None,
        is_existing_thread: bool = False,
        initial_msg_ts: str = None,
        dm_channel_id: str = None,
        dm_thread_ts: str = None,
        user_message: str = None,
    ):
        """세션 내에서 Claude Code 실행 (공통 로직)

        인터벤션 지원:
        - 락 획득 실패 시 ⚡ 리액션 + pending 저장 + interrupt
        - 실행 완료 후 pending이 있으면 이어서 실행

        Args:
            session: Session 객체
            prompt: Claude에 전달할 프롬프트
            msg_ts: 원본 메시지 타임스탬프 (이모지 추가용)
            channel: Slack 채널 ID
            say: Slack say 함수
            client: Slack client
            role: 실행할 역할 (None이면 session.role 사용)
            trello_card: 트렐로 워처에서 호출된 경우 TrackedCard 정보
            is_existing_thread: 기존 스레드에서 호출된 경우 True (세션 없이 스레드에서 처음 호출)
            initial_msg_ts: 이미 생성된 초기 메시지 ts (있으면 새로 생성하지 않음)
            dm_channel_id: 트렐로 모드에서 사고 과정을 출력할 DM 채널 ID
            dm_thread_ts: DM 스레드의 앵커 메시지 ts
            user_message: 사용자 원본 메시지 (OM Observer용, 선택)
        """
        thread_ts = session.thread_ts
        effective_role = role or session.role
        is_trello_mode = trello_card is not None

        ctx = ExecutionContext(
            session=session,
            channel=channel,
            say=say,
            client=client,
            msg_ts=msg_ts,
            effective_role=effective_role,
            thread_ts=thread_ts,
            trello_card=trello_card,
            is_trello_mode=is_trello_mode,
            is_existing_thread=is_existing_thread,
            initial_msg_ts=initial_msg_ts,
            dm_channel_id=dm_channel_id,
            dm_thread_ts=dm_thread_ts,
            user_message=user_message,
        )

        # 스레드별 락으로 동시 실행 방지
        lock = self.get_session_lock(thread_ts)
        if not lock.acquire(blocking=False):
            # 인터벤션: 리액션만 추가하고 pending에 저장 후 interrupt
            self._handle_intervention(ctx, prompt)
            return

        try:
            self._run_with_lock(ctx, prompt)
        finally:
            lock.release()

    def _handle_intervention(self, ctx: ExecutionContext, prompt: str):
        """인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우

        pending 저장 → interrupt fire → 즉시 return
        """
        thread_ts = ctx.thread_ts
        logger.info(f"인터벤션 발생: thread={thread_ts}")

        pending = PendingPrompt(
            prompt=prompt,
            msg_ts=ctx.msg_ts,
            channel=ctx.channel,
            say=ctx.say,
            client=ctx.client,
            role=ctx.effective_role,
            trello_card=ctx.trello_card,
            is_existing_thread=ctx.is_existing_thread,
            initial_msg_ts=ctx.initial_msg_ts,
            dm_channel_id=ctx.dm_channel_id,
            dm_thread_ts=ctx.dm_thread_ts,
            user_message=ctx.user_message,
        )
        self._intervention.save_pending(thread_ts, pending)

        if self.execution_mode == "remote":
            self._intervention.fire_interrupt_remote(
                thread_ts, prompt,
                self._active_remote_requests, self._service_adapter,
            )
        else:
            self._intervention.fire_interrupt_local(thread_ts)

    def _run_with_lock(self, ctx: ExecutionContext, prompt: str):
        """락을 보유한 상태에서 실행 (while 루프로 pending 처리)"""
        original_thread_ts = ctx.original_thread_ts

        # 실행 중 세션으로 표시
        self.mark_session_running(original_thread_ts)

        try:
            # 첫 번째 실행
            self._execute_once(ctx, prompt)

            # pending 확인 → while 루프
            while True:
                pending = self._intervention.pop_pending(original_thread_ts)
                if not pending:
                    break

                logger.info(f"인터벤션 이어가기: thread={original_thread_ts}")

                # pending의 정보로 컨텍스트 갱신
                ctx.msg_ts = pending.msg_ts
                ctx.channel = pending.channel
                ctx.say = pending.say
                ctx.client = pending.client
                ctx.effective_role = pending.role or ctx.session.role
                ctx.trello_card = pending.trello_card
                ctx.is_trello_mode = pending.trello_card is not None
                ctx.is_existing_thread = pending.is_existing_thread
                ctx.initial_msg_ts = pending.initial_msg_ts
                ctx.dm_channel_id = pending.dm_channel_id or ctx.dm_channel_id
                ctx.dm_thread_ts = pending.dm_thread_ts or ctx.dm_thread_ts
                ctx.user_message = pending.user_message
                # thread_ts는 이전 실행에서 업데이트된 것을 유지

                self._execute_once(ctx, pending.prompt)

        finally:
            self.mark_session_stopped(original_thread_ts)

    def _execute_once(self, ctx: ExecutionContext, prompt: str):
        """단일 Claude 실행

        ctx의 last_msg_ts, thread_ts, dm_last_reply_ts 등을 in-place로 갱신합니다.
        """
        thread_ts = ctx.thread_ts
        session = ctx.session

        # 마지막 메시지 ts 추적 (최종 답변으로 교체할 대상)
        ctx.last_msg_ts = None
        ctx.main_msg_ts = ctx.msg_ts if ctx.is_trello_mode else None

        ctx.dm_last_reply_ts = None
        ctx.is_thread_reply = session.message_count > 0 or ctx.is_existing_thread

        if ctx.is_trello_mode:
            ctx.last_msg_ts = ctx.msg_ts
        elif ctx.initial_msg_ts:
            ctx.last_msg_ts = ctx.initial_msg_ts
        else:
            initial_text = ("소영이 생각합니다..." if ctx.effective_role == "admin"
                            else "소영이 조회 전용 모드로 생각합니다...")
            quote_text = f"> {initial_text}"
            initial_msg = ctx.client.chat_postMessage(
                channel=ctx.channel,
                thread_ts=thread_ts,
                text=quote_text,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": quote_text}}]
            )
            ctx.last_msg_ts = initial_msg["ts"]

        async def on_progress(current_text: str):
            try:
                display_text = truncate_progress_text(current_text)
                if not display_text:
                    return

                if ctx.is_trello_mode:
                    if ctx.dm_channel_id and ctx.dm_thread_ts:
                        quote_text = format_dm_progress(display_text)
                        reply = ctx.client.chat_postMessage(
                            channel=ctx.dm_channel_id,
                            thread_ts=ctx.dm_thread_ts,
                            text=quote_text,
                            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": quote_text}}]
                        )
                        ctx.dm_last_reply_ts = reply["ts"]
                    else:
                        update_text = format_trello_progress(
                            display_text, ctx.trello_card, session.session_id or "")
                        self.update_message_fn(ctx.client, ctx.channel, ctx.main_msg_ts, update_text)
                else:
                    quote_text = format_as_blockquote(display_text)
                    self.update_message_fn(ctx.client, ctx.channel, ctx.last_msg_ts, quote_text)
            except Exception as e:
                logger.warning(f"사고 과정 메시지 전송 실패: {e}")

        async def on_compact(trigger: str, message: str):
            try:
                text = ("🔄 컨텍스트가 자동 압축됩니다..." if trigger == "auto"
                        else "📦 컨텍스트를 압축하는 중입니다...")
                ctx.say(text=text, thread_ts=ctx.thread_ts)
            except Exception as e:
                logger.warning(f"컴팩션 알림 전송 실패: {e}")

        ctx.on_progress = on_progress
        ctx.on_compact = on_compact
        original_thread_ts = ctx.original_thread_ts

        if self.execution_mode == "remote":
            # === Remote 모드: soul 서버에 위임 ===
            logger.info(f"Claude 실행 (remote): thread={thread_ts}, role={ctx.effective_role}")
            self._execute_remote(ctx, prompt)
        else:
            # === Local 모드: thread_ts 단위 runner 생성 ===
            role_config = self._get_role_config(ctx.effective_role)

            def _debug_send(ch: str, ts: str, msg: str) -> None:
                ctx.client.chat_postMessage(channel=ch, thread_ts=ts, text=msg)

            runner = ClaudeRunner(
                thread_ts,
                channel=ctx.channel,
                allowed_tools=role_config["allowed_tools"],
                disallowed_tools=role_config["disallowed_tools"],
                mcp_config_path=role_config["mcp_config_path"],
                debug_send_fn=_debug_send,
                prepare_memory_fn=self.prepare_memory_fn,
                trigger_observation_fn=self.trigger_observation_fn,
                on_compact_om_flag=self.on_compact_om_flag,
            )
            logger.info(f"Claude 실행 (local): thread={thread_ts}, role={ctx.effective_role}")

            try:
                result = runner.run_sync(runner.run(
                    prompt=prompt,
                    session_id=session.session_id,
                    on_progress=on_progress,
                    on_compact=on_compact,
                    user_id=session.user_id,
                    user_message=ctx.user_message,
                ))

                self._process_result(ctx, result)

            except Exception as e:
                logger.exception(f"Claude 실행 오류: {e}")
                self._result_processor.handle_exception(ctx, e)

    def _get_role_config(self, role: str) -> dict:
        """역할에 맞는 runner 설정을 반환

        Returns:
            dict with keys: allowed_tools, disallowed_tools, mcp_config_path
        """
        allowed_tools = self.role_tools.get(role, self.role_tools.get("viewer", []))

        if role == "viewer":
            return {
                "allowed_tools": allowed_tools,
                "disallowed_tools": ["Write", "Edit", "Bash", "TodoWrite", "WebFetch", "WebSearch", "Task"],
                "mcp_config_path": None,
            }
        return {
            "allowed_tools": allowed_tools,
            "disallowed_tools": None,
            "mcp_config_path": _get_mcp_config_path(),
        }

    def _get_service_adapter(self):
        """Remote 모드용 ClaudeServiceAdapter를 lazy 초기화하여 반환"""
        if self._service_adapter is None:
            with self._adapter_lock:
                if self._service_adapter is None:
                    from seosoyoung.slackbot.claude.service_client import SoulServiceClient
                    from seosoyoung.slackbot.claude.service_adapter import ClaudeServiceAdapter
                    client = SoulServiceClient(
                        base_url=self.soul_url,
                        token=self.soul_token,
                    )
                    self._service_adapter = ClaudeServiceAdapter(
                        client=client,
                        client_id=self.soul_client_id,
                    )
        return self._service_adapter

    def _execute_remote(self, ctx: ExecutionContext, prompt: str):
        """Remote 모드: soul 서버에 실행을 위임"""
        adapter = self._get_service_adapter()
        original_thread_ts = ctx.original_thread_ts
        request_id = original_thread_ts  # thread_ts를 request_id로 사용

        # 실행 중인 request_id 추적 (인터벤션용)
        self._active_remote_requests[original_thread_ts] = request_id

        try:
            result = run_in_new_loop(
                adapter.execute(
                    prompt=prompt,
                    request_id=request_id,
                    resume_session_id=ctx.session.session_id,
                    on_progress=ctx.on_progress,
                    on_compact=ctx.on_compact,
                )
            )

            self._process_result(ctx, result)

        except Exception as e:
            logger.exception(f"[Remote] Claude 실행 오류: {e}")
            self._result_processor.handle_exception(ctx, e)
        finally:
            self._active_remote_requests.pop(original_thread_ts, None)

    def _process_result(self, ctx: ExecutionContext, result):
        """실행 결과 처리

        세션 업데이트 후 결과 타입에 따라 핸들러를 호출합니다.
        핸들러 메서드를 거쳐 ResultProcessor에 위임합니다.
        """
        thread_ts = ctx.thread_ts

        if result.session_id and result.session_id != ctx.session.session_id:
            self.session_manager.update_session_id(thread_ts, result.session_id)

        self.session_manager.increment_message_count(thread_ts)

        if result.interrupted:
            self._result_processor.handle_interrupted(ctx)
        elif result.is_error:
            self._result_processor.handle_error(ctx, result.output or result.error)
        elif result.success:
            self._result_processor.handle_success(ctx, result)
        else:
            self._result_processor.handle_error(ctx, result.error)

