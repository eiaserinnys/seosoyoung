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
from pathlib import Path
from typing import Any, Callable, Optional

from seosoyoung.slackbot.claude.agent_runner import ClaudeResult, ClaudeRunner
from seosoyoung.slackbot.claude.intervention import InterventionManager, PendingPrompt
from seosoyoung.slackbot.claude.result_processor import ResultProcessor
from seosoyoung.slackbot.claude.session import SessionManager, SessionRuntime
from seosoyoung.slackbot.claude.engine_types import ProgressCallback, CompactCallback
from seosoyoung.slackbot.claude.types import UpdateMessageFn
from seosoyoung.utils.async_bridge import run_in_new_loop

logger = logging.getLogger(__name__)


def _get_mcp_config_path() -> Optional[Path]:
    """MCP 설정 파일 경로 반환 (없으면 None)"""
    config_path = Path(__file__).resolve().parents[4] / "mcp_config.json"
    return config_path if config_path.exists() else None


def _get_role_config(role: str, role_tools: dict) -> dict:
    """역할에 맞는 runner 설정을 반환 (모듈 레벨 함수)

    Args:
        role: 실행 역할 ("admin", "viewer" 등)
        role_tools: 역할별 허용 도구 딕셔너리

    Returns:
        dict with keys: allowed_tools, disallowed_tools, mcp_config_path
    """
    allowed_tools = role_tools.get(role, role_tools.get("viewer", []))

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
        soul_url: str = "",
        soul_token: str = "",
        soul_client_id: str = "",
        restart_type_update=None,
        restart_type_restart=None,
        trello_watcher_ref: Optional[Callable] = None,
        list_runner_ref: Optional[Callable] = None,
        parse_markers_fn: Optional[Callable] = None,
    ):
        self.session_manager = session_manager
        self.session_runtime = session_runtime
        self.restart_manager = restart_manager
        self.send_long_message = send_long_message
        self.send_restart_confirmation = send_restart_confirmation
        self.update_message_fn = update_message_fn
        self.execution_mode = execution_mode
        self.role_tools = role_tools or {}
        self.soul_url = soul_url
        self.soul_token = soul_token
        self.soul_client_id = soul_client_id
        self.trello_watcher_ref = trello_watcher_ref
        self.list_runner_ref = list_runner_ref
        self._parse_markers_fn = parse_markers_fn

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
        prompt: str,
        thread_ts: str,
        msg_ts: str,
        *,
        on_progress: ProgressCallback,
        on_compact: CompactCallback,
        presentation: Any,         # PresentationContext (opaque)
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        user_message: Optional[str] = None,
        on_result: Optional[Callable] = None,  # (result, thread_ts, user_message) -> None
    ):
        """세션 내에서 Claude Code 실행 (공통 로직)

        인터벤션 지원:
        - 락 획득 실패 시 pending 저장 + interrupt
        - 실행 완료 후 pending이 있으면 이어서 실행

        Args:
            prompt: Claude에 전달할 프롬프트
            thread_ts: 세션의 스레드 타임스탬프
            msg_ts: 원본 메시지 타임스탬프
            on_progress: 진행 상태 콜백
            on_compact: 컴팩션 알림 콜백
            presentation: PresentationContext (opaque - ResultProcessor에 전달)
            session_id: Claude 세션 ID (이어서 실행용)
            role: 실행 역할
            user_message: 사용자 원본 메시지
            on_result: 결과 핸들러 콜백
        """
        # 스레드별 락으로 동시 실행 방지
        lock = self.get_session_lock(thread_ts)
        if not lock.acquire(blocking=False):
            # 인터벤션: pending에 저장 후 interrupt
            self._handle_intervention(
                thread_ts, prompt, msg_ts,
                on_progress=on_progress,
                on_compact=on_compact,
                presentation=presentation,
                role=role,
                user_message=user_message,
                on_result=on_result,
                session_id=session_id,
            )
            return

        try:
            self._run_with_lock(
                thread_ts, prompt, msg_ts,
                on_progress=on_progress,
                on_compact=on_compact,
                presentation=presentation,
                session_id=session_id,
                role=role,
                user_message=user_message,
                on_result=on_result,
            )
        finally:
            lock.release()

    def _handle_intervention(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        *,
        on_progress,
        on_compact,
        presentation,
        role,
        user_message,
        on_result,
        session_id,
    ):
        """인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우"""
        logger.info(f"인터벤션 발생: thread={thread_ts}")

        pending = PendingPrompt(
            prompt=prompt,
            msg_ts=msg_ts,
            on_progress=on_progress,
            on_compact=on_compact,
            presentation=presentation,
            role=role,
            user_message=user_message,
            on_result=on_result,
            session_id=session_id,
        )
        self._intervention.save_pending(thread_ts, pending)

        if self.execution_mode == "remote":
            self._intervention.fire_interrupt_remote(
                thread_ts, prompt,
                self._active_remote_requests, self._service_adapter,
            )
        else:
            self._intervention.fire_interrupt_local(thread_ts)

    def _run_with_lock(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        *,
        on_progress,
        on_compact,
        presentation,
        session_id,
        role,
        user_message,
        on_result,
    ):
        """락을 보유한 상태에서 실행 (while 루프로 pending 처리)"""
        # 실행 중 세션으로 표시
        self.mark_session_running(thread_ts)

        try:
            # 첫 번째 실행
            self._execute_once(
                thread_ts, prompt, msg_ts,
                on_progress=on_progress,
                on_compact=on_compact,
                presentation=presentation,
                session_id=session_id,
                role=role,
                user_message=user_message,
                on_result=on_result,
            )

            # pending 확인 → while 루프
            while True:
                pending = self._intervention.pop_pending(thread_ts)
                if not pending:
                    break

                logger.info(f"인터벤션 이어가기: thread={thread_ts}")

                self._execute_once(
                    thread_ts, pending.prompt, pending.msg_ts,
                    on_progress=pending.on_progress,
                    on_compact=pending.on_compact,
                    presentation=pending.presentation,
                    session_id=pending.session_id,
                    role=pending.role,
                    user_message=pending.user_message,
                    on_result=pending.on_result,
                )

        finally:
            self.mark_session_stopped(thread_ts)

    def _execute_once(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        *,
        on_progress,
        on_compact,
        presentation,
        session_id,
        role,
        user_message,
        on_result,
    ):
        """단일 Claude 실행"""
        if self.execution_mode == "remote":
            # === Remote 모드: soul 서버에 위임 ===
            effective_role = role or "admin"
            role_config = self._get_role_config(effective_role)
            logger.info(f"Claude 실행 (remote): thread={thread_ts}, role={effective_role}")
            self._execute_remote(
                thread_ts, prompt,
                on_progress=on_progress,
                on_compact=on_compact,
                presentation=presentation,
                session_id=session_id,
                user_message=user_message,
                on_result=on_result,
                allowed_tools=role_config["allowed_tools"],
                disallowed_tools=role_config["disallowed_tools"],
                use_mcp=role_config["mcp_config_path"] is not None,
            )
        else:
            # === Local 모드: thread_ts 단위 runner 생성 ===
            effective_role = role or "admin"
            role_config = self._get_role_config(effective_role)

            def _debug_send(msg: str) -> None:
                presentation.client.chat_postMessage(
                    channel=presentation.channel, thread_ts=thread_ts, text=msg)

            runner = ClaudeRunner(
                thread_ts,
                allowed_tools=role_config["allowed_tools"],
                disallowed_tools=role_config["disallowed_tools"],
                mcp_config_path=role_config["mcp_config_path"],
                debug_send_fn=_debug_send,
            )
            logger.info(f"Claude 실행 (local): thread={thread_ts}, role={effective_role}")

            try:
                engine_result = runner.run_sync(runner.run(
                    prompt=prompt,
                    session_id=session_id,
                    on_progress=on_progress,
                    on_compact=on_compact,
                ))

                # 응용 마커 파싱 + ClaudeResult 변환
                markers = self._parse_markers_fn(engine_result.output) if self._parse_markers_fn else None
                result = ClaudeResult.from_engine_result(engine_result, markers=markers)

                # 결과 콜백 호출 (OM 등)
                if on_result:
                    on_result(result, thread_ts, user_message)

                self._process_result(presentation, result, thread_ts)

            except Exception as e:
                logger.exception(f"Claude 실행 오류: {e}")
                self._result_processor.handle_exception(presentation, e)

    def _get_role_config(self, role: str) -> dict:
        """역할에 맞는 runner 설정을 반환 (모듈 함수에 위임)"""
        return _get_role_config(role, self.role_tools)

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
                        parse_markers_fn=self._parse_markers_fn,
                    )
        return self._service_adapter

    def _execute_remote(
        self,
        thread_ts: str,
        prompt: str,
        *,
        on_progress,
        on_compact,
        presentation,
        session_id,
        user_message,
        on_result,
        allowed_tools: Optional[list] = None,
        disallowed_tools: Optional[list] = None,
        use_mcp: bool = True,
    ):
        """Remote 모드: soul 서버에 실행을 위임"""
        adapter = self._get_service_adapter()
        request_id = thread_ts  # thread_ts를 request_id로 사용

        # 실행 중인 request_id 추적 (인터벤션용)
        self._active_remote_requests[thread_ts] = request_id

        try:
            result = run_in_new_loop(
                adapter.execute(
                    prompt=prompt,
                    request_id=request_id,
                    resume_session_id=session_id,
                    on_progress=on_progress,
                    on_compact=on_compact,
                    allowed_tools=allowed_tools,
                    disallowed_tools=disallowed_tools,
                    use_mcp=use_mcp,
                )
            )

            # 결과 콜백 호출 (OM 등)
            if on_result:
                on_result(result, thread_ts, user_message)

            self._process_result(presentation, result, thread_ts)

        except Exception as e:
            logger.exception(f"[Remote] Claude 실행 오류: {e}")
            self._result_processor.handle_exception(presentation, e)
        finally:
            self._active_remote_requests.pop(thread_ts, None)

    def _process_result(self, presentation: Any, result, thread_ts: str):
        """실행 결과 처리

        세션 업데이트 후 결과 타입에 따라 핸들러를 호출합니다.
        """
        if result.session_id:
            self.session_manager.update_session_id(thread_ts, result.session_id)
            # pctx에도 session_id 반영 (후속 콜백/핸들러에서 사용)
            presentation.session_id = result.session_id

        self.session_manager.increment_message_count(thread_ts)

        if result.interrupted:
            self._result_processor.handle_interrupted(presentation)
        elif result.is_error:
            self._result_processor.handle_error(presentation, result.output or result.error)
        elif result.success:
            self._result_processor.handle_success(presentation, result)
        else:
            self._result_processor.handle_error(presentation, result.error)
