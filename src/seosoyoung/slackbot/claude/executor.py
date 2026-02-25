"""Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.

실행 모드 (execution_mode):
- local: 기존 방식. ClaudeRunner를 직접 사용하여 로컬에서 실행.
- remote: seosoyoung-soul 서버에 HTTP/SSE로 위임하여 실행.
         soul 서버 연결 실패 시 local 모드로 자동 폴백.
         soul 복구 시 remote 모드로 자동 복귀.
"""

import logging
import threading
import time
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

# === 폴백 상태 관리 ===

# 헬스체크 쿨다운: 연속 실패 시 매번 체크하지 않도록 제한
_HEALTH_CHECK_COOLDOWN = 30.0  # 초
# 헬스체크 타임아웃 (빠른 실패를 위해 짧게)
_HEALTH_CHECK_TIMEOUT = 3.0  # 초


class SoulHealthTracker:
    """Soul 서버 헬스 상태 추적

    - remote 모드에서 soul 연결 가능 여부를 추적
    - 실패 시 local 폴백, 복구 시 remote 복귀
    - 쿨다운 기반으로 헬스체크 빈도 제한
    """

    def __init__(self, soul_url: str, cooldown: float = _HEALTH_CHECK_COOLDOWN):
        self._soul_url = soul_url.rstrip("/")
        self._cooldown = cooldown
        self._is_healthy = True  # 낙관적 초기값
        self._last_check_time = 0.0
        self._lock = threading.Lock()
        self._consecutive_failures = 0

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def check_health(self) -> bool:
        """Soul 서버 헬스체크 (쿨다운 적용)

        Returns:
            True: healthy (remote 사용 가능)
            False: unhealthy (local 폴백 필요)
        """
        now = time.monotonic()
        with self._lock:
            # 쿨다운 기간 내에는 캐시된 결과 반환
            if now - self._last_check_time < self._cooldown:
                return self._is_healthy
            self._last_check_time = now

        # 실제 헬스체크 수행
        healthy = self._do_health_check()

        with self._lock:
            if healthy:
                if not self._is_healthy:
                    logger.info("[Fallback] Soul 서버 복구 감지 → remote 모드 복귀")
                self._is_healthy = True
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
                if self._is_healthy:
                    logger.warning(
                        "[Fallback] Soul 서버 연결 실패 → local 모드로 폴백"
                    )
                self._is_healthy = False

        return healthy

    def mark_healthy(self) -> None:
        """외부에서 healthy 상태로 강제 설정 (성공적 remote 실행 후)"""
        with self._lock:
            self._is_healthy = True
            self._consecutive_failures = 0
            self._last_check_time = time.monotonic()

    def mark_unhealthy(self) -> None:
        """외부에서 unhealthy 상태로 강제 설정 (remote 실행 중 연결 오류 시)"""
        with self._lock:
            self._is_healthy = False
            self._consecutive_failures += 1
            self._last_check_time = time.monotonic()

    def _do_health_check(self) -> bool:
        """HTTP GET /health 요청으로 soul 서버 가용성 확인"""
        import urllib.request
        import urllib.error

        url = f"{self._soul_url}/health"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=_HEALTH_CHECK_TIMEOUT) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False


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
        # Remote 모드: 실행 중인 request_id 추적 (인터벤션 폴백용)
        self._active_remote_requests: dict[str, str] = {}  # thread_ts -> request_id
        # Remote 모드: thread_ts ↔ session_id 매핑 (session_id 기반 인터벤션용)
        self._thread_session_map: dict[str, str] = {}  # thread_ts -> session_id
        self._thread_session_lock = threading.Lock()
        # Remote 모드: session_id 확보 전 도착한 인터벤션 버퍼
        self._pending_session_interventions: dict[str, list] = {}  # thread_ts -> [(prompt, ...)]
        self._pending_session_lock = threading.Lock()
        # Remote 모드: Soul 서버 헬스 상태 추적 (폴백 전략)
        self._health_tracker: Optional[SoulHealthTracker] = None
        if execution_mode == "remote" and soul_url:
            self._health_tracker = SoulHealthTracker(soul_url)

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
                self._active_remote_requests, self._get_service_adapter(),
                session_id=self._get_session_id(thread_ts),
                pending_session_interventions=self._pending_session_interventions,
                pending_session_lock=self._pending_session_lock,
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
        """단일 Claude 실행

        execution_mode 판별 + 폴백 전략:
        1. remote 모드: soul 헬스체크 → 성공 시 remote, 실패 시 local 폴백
        2. local 모드: 직접 ClaudeRunner 사용
        """
        effective_role = role or "admin"
        role_config = self._get_role_config(effective_role)

        use_remote = self._should_use_remote()

        if use_remote:
            # === Remote 모드: soul 서버에 위임 ===
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
            if self.execution_mode == "remote":
                logger.warning(f"[Fallback] local 모드로 폴백 실행: thread={thread_ts}")

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

    def _should_use_remote(self) -> bool:
        """remote 모드 사용 여부 판별 (폴백 전략 포함)

        execution_mode가 'remote'이고 soul 서버가 healthy하면 True.
        soul 서버에 연결할 수 없으면 False (local 폴백).
        health_tracker가 설정되지 않은 경우 기존 동작 유지 (항상 remote).
        """
        if self.execution_mode != "remote":
            return False

        # health_tracker 미설정 시 낙관적으로 remote 허용 (기존 동작 유지)
        if self._health_tracker is None:
            return True

        return self._health_tracker.check_health()

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
        from seosoyoung.slackbot.claude.service_client import SoulServiceClient
        from seosoyoung.slackbot.claude.service_adapter import ClaudeServiceAdapter
        client = SoulServiceClient(
            base_url=self.soul_url,
            token=self.soul_token,
        )
        return ClaudeServiceAdapter(
            client=client,
            client_id=self.soul_client_id,
            parse_markers_fn=self._parse_markers_fn,
        )

    def _register_session_id(self, thread_ts: str, session_id: str) -> None:
        """thread_ts ↔ session_id 매핑 등록 및 버퍼된 인터벤션 flush"""
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
                    _run(adapter.intervene_by_session(
                        session_id=session_id,
                        text=pending_prompt,
                        user=pending_user,
                    ))
                    logger.info(f"[Remote] 버퍼된 인터벤션 flush: thread={thread_ts}, session={session_id}")
                except Exception as e:
                    logger.warning(f"[Remote] 버퍼된 인터벤션 flush 실패: {e}")

    def _unregister_session_id(self, thread_ts: str) -> None:
        """thread_ts ↔ session_id 매핑 해제"""
        with self._thread_session_lock:
            session_id = self._thread_session_map.pop(thread_ts, None)
        with self._pending_session_lock:
            self._pending_session_interventions.pop(thread_ts, None)
        if session_id:
            logger.info(f"[Remote] session_id 매핑 해제: thread={thread_ts}, session={session_id}")

    def _get_session_id(self, thread_ts: str) -> Optional[str]:
        """thread_ts에 대응하는 session_id 조회"""
        with self._thread_session_lock:
            return self._thread_session_map.get(thread_ts)

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

        # debug 콜백: 로컬 모드의 debug_send_fn과 동등한 동작
        async def on_debug(message: str) -> None:
            try:
                presentation.client.chat_postMessage(
                    channel=presentation.channel, thread_ts=thread_ts, text=message)
            except Exception as e:
                logger.warning(f"[Remote] 디버그 메시지 전송 실패: {e}")

        # session_id 조기 통지 콜백
        async def on_session_callback(new_session_id: str) -> None:
            self._register_session_id(thread_ts, new_session_id)

        # 실행 중인 request_id 추적 (인터벤션 폴백용)
        self._active_remote_requests[thread_ts] = request_id

        try:
            result = run_in_new_loop(
                adapter.execute(
                    prompt=prompt,
                    request_id=request_id,
                    resume_session_id=session_id,
                    on_progress=on_progress,
                    on_compact=on_compact,
                    on_debug=on_debug,
                    on_session=on_session_callback,
                    allowed_tools=allowed_tools,
                    disallowed_tools=disallowed_tools,
                    use_mcp=use_mcp,
                )
            )

            # 성공적 실행 → health tracker에 healthy 마킹
            if self._health_tracker and result.success:
                self._health_tracker.mark_healthy()

            # 결과 콜백 호출 (OM 등)
            if on_result:
                on_result(result, thread_ts, user_message)

            self._process_result(presentation, result, thread_ts)

        except Exception as e:
            logger.exception(f"[Remote] Claude 실행 오류: {e}")
            # 연결 오류 시 health tracker에 unhealthy 마킹
            if self._health_tracker:
                error_str = str(e).lower()
                if any(kw in error_str for kw in ("connect", "timeout", "refused", "reset")):
                    self._health_tracker.mark_unhealthy()
            self._result_processor.handle_exception(presentation, e)
        finally:
            self._active_remote_requests.pop(thread_ts, None)
            self._unregister_session_id(thread_ts)

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
