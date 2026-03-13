"""Claude Code 실행 로직

Soulstream 서버에 HTTP/SSE로 위임하여 Claude Code를 실행합니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
Soulstream에 interrupt를 전송하여 현재 실행을 중단시킵니다.

per-session 아키텍처: agent_session_id가 유일한 식별자.
"""

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from seosoyoung.slackbot.reflect import reflect
from seosoyoung.slackbot.soulstream.engine_types import ClaudeResult, CompactCallback
from seosoyoung.slackbot.soulstream.intervention import InterventionManager
from seosoyoung.slackbot.soulstream.result_processor import ResultProcessor
from seosoyoung.slackbot.soulstream.session import SessionManager, SessionRuntime
from seosoyoung.slackbot.soulstream.types import UpdateMessageFn
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

    per-session 아키텍처: agent_session_id가 유일한 식별자.
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
        role_tools: Optional[dict] = None,
        soul_url: str = "",
        soul_token: str = "",
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
        self.role_tools = role_tools or {}
        self.soul_url = soul_url
        self.soul_token = soul_token
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
        # thread_ts ↔ agent_session_id 매핑 (per-session 인터벤션용)
        self._thread_session_map: dict[str, str] = {}  # thread_ts -> agent_session_id
        self._thread_session_lock = threading.Lock()
        # agent_session_id 확보 전 도착한 인터벤션 버퍼
        self._pending_session_interventions: dict[str, list] = {}  # thread_ts -> [(prompt, ...)]
        self._pending_session_lock = threading.Lock()

    @reflect.capability(
        name="soulstream_integration",
        description=(
            "soulstream soul-server에 Claude Code 세션을 위임하고 "
            "SSE 스트리밍으로 실시간 응답을 수신"
        ),
    )
    def run(
        self,
        prompt: str,
        thread_ts: str,
        msg_ts: str,
        *,
        on_compact: CompactCallback,
        presentation: Any,         # PresentationContext (opaque)
        session_id: Optional[str] = None,
        role: Optional[str] = None,
        user_message: Optional[str] = None,
        on_result: Optional[Callable] = None,  # (result, thread_ts, user_message) -> None
        # 세분화 이벤트 콜백
        on_thinking=None,
        on_text_start=None,
        on_text_delta=None,
        on_text_end=None,
        on_tool_start=None,
        on_tool_result=None,
        on_input_request=None,
    ):
        """세션 내에서 Claude Code 실행 (공통 로직)

        인터벤션 지원:
        - 락 획득 실패 시 Soulstream에 interrupt 전송

        Args:
            prompt: Claude에 전달할 프롬프트
            thread_ts: 세션의 스레드 타임스탬프
            msg_ts: 원본 메시지 타임스탬프
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
                on_compact=on_compact,
                presentation=presentation,
                role=role,
                user_message=user_message,
                on_result=on_result,
                session_id=session_id,
                on_thinking=on_thinking,
                on_text_start=on_text_start,
                on_text_delta=on_text_delta,
                on_text_end=on_text_end,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                on_input_request=on_input_request,
            )
            return

        try:
            self._run_with_lock(
                thread_ts, prompt, msg_ts,
                on_compact=on_compact,
                presentation=presentation,
                session_id=session_id,
                role=role,
                user_message=user_message,
                on_result=on_result,
                on_thinking=on_thinking,
                on_text_start=on_text_start,
                on_text_delta=on_text_delta,
                on_text_end=on_text_end,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                on_input_request=on_input_request,
            )
        finally:
            lock.release()

    def _handle_intervention(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        *,
        on_compact,
        presentation,
        role,
        user_message,
        on_result,
        session_id,
        # 세분화 이벤트 콜백
        on_thinking=None,
        on_text_start=None,
        on_text_delta=None,
        on_text_end=None,
        on_tool_start=None,
        on_tool_result=None,
        on_input_request=None,
    ):
        """인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우

        Soulstream에 interrupt를 전송하여 현재 실행을 중단시킵니다.
        Soulstream 측에서 interrupt를 받으면 새 프롬프트로 이어서 실행합니다.
        """
        logger.info(f"인터벤션 발생: thread={thread_ts}")

        self._intervention.fire_interrupt_remote(
            thread_ts, prompt,
            self._get_service_adapter(),
            session_id=self.get_session_id(thread_ts),
            pending_session_interventions=self._pending_session_interventions,
            pending_session_lock=self._pending_session_lock,
        )

    def _run_with_lock(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        *,
        on_compact,
        presentation,
        session_id,
        role,
        user_message,
        on_result,
        # 세분화 이벤트 콜백
        on_thinking=None,
        on_text_start=None,
        on_text_delta=None,
        on_text_end=None,
        on_tool_start=None,
        on_tool_result=None,
        on_input_request=None,
    ):
        """락을 보유한 상태에서 실행"""
        # 실행 중 세션으로 표시
        self.mark_session_running(thread_ts)

        try:
            self._execute_once(
                thread_ts, prompt, msg_ts,
                on_compact=on_compact,
                presentation=presentation,
                session_id=session_id,
                role=role,
                user_message=user_message,
                on_result=on_result,
                on_thinking=on_thinking,
                on_text_start=on_text_start,
                on_text_delta=on_text_delta,
                on_text_end=on_text_end,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                on_input_request=on_input_request,
            )
        finally:
            self.mark_session_stopped(thread_ts)

    def _execute_once(
        self,
        thread_ts: str,
        prompt: str,
        msg_ts: str,
        *,
        on_compact,
        presentation,
        session_id,
        role,
        user_message,
        on_result,
        # 세분화 이벤트 콜백
        on_thinking=None,
        on_text_start=None,
        on_text_delta=None,
        on_text_end=None,
        on_tool_start=None,
        on_tool_result=None,
        on_input_request=None,
    ):
        """단일 Claude 실행 -- Soulstream 서버에 위임"""
        effective_role = role or "admin"
        role_config = self._get_role_config(effective_role)

        logger.info(f"Claude 실행: thread={thread_ts}, role={effective_role}")
        self._execute_remote(
            thread_ts, prompt,
            on_compact=on_compact,
            presentation=presentation,
            session_id=session_id,
            user_message=user_message,
            on_result=on_result,
            allowed_tools=role_config["allowed_tools"],
            disallowed_tools=role_config["disallowed_tools"],
            use_mcp=role_config["mcp_config_path"] is not None,
            on_thinking=on_thinking,
            on_text_start=on_text_start,
            on_text_delta=on_text_delta,
            on_text_end=on_text_end,
            on_tool_start=on_tool_start,
            on_tool_result=on_tool_result,
            on_input_request=on_input_request,
        )

    def _get_role_config(self, role: str) -> dict:
        """역할에 맞는 runner 설정을 반환 (모듈 함수에 위임)"""
        return _get_role_config(role, self.role_tools)

    def _get_service_adapter(self):
        """Remote 모드용 ClaudeServiceAdapter를 생성하여 반환 (호출마다 새 인스턴스)

        aiohttp.ClientSession은 생성된 이벤트 루프에 바인딩됩니다.
        run_in_new_loop로 실행할 때마다 새 루프가 생성되므로,
        이전 루프에서 만든 ClientSession을 재사용하면 "Event loop is closed" 오류가 발생합니다.
        따라서 매 요청마다 새 SoulServiceClient를 생성합니다.
        """
        from seosoyoung.slackbot.soulstream.service_client import SoulServiceClient
        from seosoyoung.slackbot.soulstream.service_adapter import ClaudeServiceAdapter
        client = SoulServiceClient(
            base_url=self.soul_url,
            token=self.soul_token,
        )
        return ClaudeServiceAdapter(
            client=client,
            parse_markers_fn=self._parse_markers_fn,
        )

    def _register_session_id(self, thread_ts: str, session_id: str) -> None:
        """thread_ts <-> agent_session_id 매핑 등록 및 버퍼된 인터벤션 flush"""
        with self._thread_session_lock:
            self._thread_session_map[thread_ts] = session_id
        logger.info(f"[Remote] session_id 매핑 등록: thread={thread_ts} -> session={session_id}")

        # 버퍼된 인터벤션이 있으면 flush
        with self._pending_session_lock:
            pending = self._pending_session_interventions.pop(thread_ts, [])

        if pending:
            adapter = self._get_service_adapter()
            for (pending_prompt, pending_user) in pending:
                try:
                    from seosoyoung.utils.async_bridge import run_in_new_loop as _run
                    _run(adapter.intervene(
                        agent_session_id=session_id,
                        text=pending_prompt,
                        user=pending_user,
                    ))
                    logger.info(f"[Remote] 버퍼된 인터벤션 flush: thread={thread_ts}, session={session_id}")
                except Exception as e:
                    logger.warning(f"[Remote] 버퍼된 인터벤션 flush 실패: {e}")

    def _unregister_session_id(self, thread_ts: str) -> None:
        """thread_ts <-> agent_session_id 매핑 해제"""
        with self._thread_session_lock:
            session_id = self._thread_session_map.pop(thread_ts, None)
        with self._pending_session_lock:
            self._pending_session_interventions.pop(thread_ts, None)
        if session_id:
            logger.info(f"[Remote] session_id 매핑 해제: thread={thread_ts}, session={session_id}")

    def get_session_id(self, thread_ts: str) -> Optional[str]:
        """thread_ts에 대응하는 agent_session_id 조회"""
        with self._thread_session_lock:
            return self._thread_session_map.get(thread_ts)

    def _execute_remote(
        self,
        thread_ts: str,
        prompt: str,
        *,
        on_compact,
        presentation,
        session_id,
        user_message,
        on_result,
        allowed_tools: Optional[list] = None,
        disallowed_tools: Optional[list] = None,
        use_mcp: bool = True,
        # 세분화 이벤트 콜백
        on_thinking=None,
        on_text_start=None,
        on_text_delta=None,
        on_text_end=None,
        on_tool_start=None,
        on_tool_result=None,
        on_input_request=None,
    ):
        """Remote 모드: Soulstream 서버에 실행을 위임 (per-session)"""
        adapter = self._get_service_adapter()

        # debug 콜백: rate_limit 경고 등을 슬랙 스레드에 전송
        async def on_debug(message: str) -> None:
            if presentation is None:
                return
            try:
                presentation.client.chat_postMessage(
                    channel=presentation.channel, thread_ts=thread_ts, text=message)
            except Exception as e:
                logger.warning(f"[Remote] 디버그 메시지 전송 실패: {e}")

        # credential_alert 콜백: 크레덴셜 알림 UI를 슬랙 채널에 전송
        async def on_credential_alert_callback(data: dict) -> None:
            if presentation is None:
                return
            from seosoyoung.slackbot.handlers.credential_ui import send_credential_alert
            from seosoyoung.slackbot.config import Config
            channel = Config.claude.credential_alert_channel
            if channel:
                send_credential_alert(presentation.client, channel, data)

        # agent_session_id 조기 통지 콜백
        async def on_session_callback(new_session_id: str) -> None:
            self._register_session_id(thread_ts, new_session_id)

        try:
            result = run_in_new_loop(
                adapter.execute(
                    prompt=prompt,
                    agent_session_id=session_id,
                    on_compact=on_compact,
                    on_debug=on_debug,
                    on_session=on_session_callback,
                    on_credential_alert=on_credential_alert_callback,
                    on_thinking=on_thinking,
                    on_text_start=on_text_start,
                    on_text_delta=on_text_delta,
                    on_text_end=on_text_end,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                    on_input_request=on_input_request,
                    allowed_tools=allowed_tools,
                    disallowed_tools=disallowed_tools,
                    use_mcp=use_mcp,
                )
            )

            # 결과 콜백 호출 (OM 등)
            if on_result:
                try:
                    on_result(result, thread_ts, user_message)
                except Exception as cb_err:
                    logger.warning(f"[Remote] on_result 콜백 오류 (무시): {cb_err}")

            self._process_result(presentation, result, thread_ts)

        except Exception as e:
            logger.exception(f"[Remote] Claude 실행 오류: {e}")
            if presentation is not None:
                self._result_processor.handle_exception(presentation, e)
        finally:
            self._unregister_session_id(thread_ts)

    def _process_result(self, presentation: Any, result, thread_ts: str):
        """실행 결과 처리

        세션 업데이트 후 결과 타입에 따라 핸들러를 호출합니다.
        presentation이 None이면 세션만 갱신하고 슬랙 게시를 건너뜁니다 (text_only 모드).
        """
        if result.session_id:
            self.session_manager.update_session_id(thread_ts, result.session_id)
            if presentation is not None:
                # pctx에도 session_id 반영 (후속 콜백/핸들러에서 사용)
                presentation.session_id = result.session_id

        self.session_manager.increment_message_count(thread_ts)

        if presentation is None:
            # text_only 모드: 출력은 on_result 콜백으로 이미 캡처됨
            return

        if result.interrupted:
            self._result_processor.handle_interrupted(presentation)
        elif result.is_error:
            self._result_processor.handle_error(presentation, result.output or result.error)
        elif result.success:
            self._result_processor.handle_success(presentation, result)
        else:
            self._result_processor.handle_error(presentation, result.error)
