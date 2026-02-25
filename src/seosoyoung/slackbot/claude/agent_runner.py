"""Claude Code SDK 기반 실행기"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Optional, Callable, Awaitable

import psutil

try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, HookContext
    from claude_agent_sdk._errors import MessageParseError, ProcessError
    from claude_agent_sdk.types import (
        AssistantMessage,
        HookJSONOutput,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    # 더미 클래스 (import 에러 방지)
    class ClaudeAgentOptions:
        pass
    class ClaudeSDKClient:
        pass
    class HookMatcher:
        pass
    class HookContext:
        pass
    class MessageParseError(Exception):
        pass
    class ProcessError(Exception):
        pass
    class AssistantMessage:
        pass
    class HookJSONOutput:
        pass
    class ResultMessage:
        pass
    class SystemMessage:
        pass
    class TextBlock:
        pass
    class ToolResultBlock:
        pass
    class ToolUseBlock:
        pass

from seosoyoung.slackbot.claude.diagnostics import (
    DebugSendFn,
    build_session_dump,
    classify_process_error,
    format_rate_limit_warning,
)
from seosoyoung.slackbot.claude.engine_types import EngineResult
from seosoyoung.slackbot.claude.instrumented_client import InstrumentedClaudeClient
from seosoyoung.slackbot.claude.sdk_compat import ParseAction, classify_parse_error
from seosoyoung.utils.async_bridge import run_in_new_loop

logger = logging.getLogger(__name__)

# Claude Code 기본 금지 도구
DEFAULT_DISALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Task",
]


@dataclass
class ClaudeResult(EngineResult):
    """Claude Code 실행 결과 (하위호환 레이어)

    EngineResult를 상속하며, 응용 마커 필드를 추가합니다.
    마커 필드는 executor에서 ParsedMarkers를 통해 설정됩니다.
    """

    update_requested: bool = False
    restart_requested: bool = False
    list_run: Optional[str] = None  # <!-- LIST_RUN: 리스트명 --> 마커로 추출된 리스트 이름

    @classmethod
    def from_engine_result(
        cls,
        result: EngineResult,
        markers: Any = None,
    ) -> "ClaudeResult":
        """EngineResult + markers → ClaudeResult 변환

        Args:
            result: 엔진 순수 결과
            markers: 파싱된 응용 마커 (duck-typed, None이면 기본값 사용)
        """
        return cls(
            success=result.success,
            output=result.output,
            session_id=result.session_id,
            error=result.error,
            is_error=result.is_error,
            interrupted=result.interrupted,
            usage=result.usage,
            collected_messages=result.collected_messages,
            update_requested=getattr(markers, "update_requested", False),
            restart_requested=getattr(markers, "restart_requested", False),
            list_run=getattr(markers, "list_run", None),
        )


# ---------------------------------------------------------------------------
# Module-level registry: thread_ts → ClaudeRunner
# ---------------------------------------------------------------------------
_registry: dict[str, "ClaudeRunner"] = {}
_registry_lock = threading.Lock()


def get_runner(thread_ts: str) -> Optional["ClaudeRunner"]:
    """레지스트리에서 러너 조회"""
    with _registry_lock:
        return _registry.get(thread_ts)


def register_runner(runner: "ClaudeRunner") -> None:
    """레지스트리에 러너 등록"""
    with _registry_lock:
        _registry[runner.thread_ts] = runner


def remove_runner(thread_ts: str) -> Optional["ClaudeRunner"]:
    """레지스트리에서 러너 제거"""
    with _registry_lock:
        return _registry.pop(thread_ts, None)


async def shutdown_all() -> int:
    """모든 등록된 러너의 클라이언트를 종료

    프로세스 종료 전에 호출하여 고아 프로세스를 방지합니다.

    Returns:
        종료된 클라이언트 수
    """
    with _registry_lock:
        runners = list(_registry.values())

    if not runners:
        logger.info("종료할 활성 클라이언트 없음")
        return 0

    count = 0
    for runner in runners:
        try:
            if runner.client:
                await runner.client.disconnect()
                count += 1
                logger.info(f"클라이언트 종료 성공: {runner.thread_ts}")
        except Exception as e:
            logger.warning(f"클라이언트 종료 실패: {runner.thread_ts}, {e}")
            if runner.pid:
                ClaudeRunner._force_kill_process(runner.pid, runner.thread_ts)
                count += 1

    with _registry_lock:
        _registry.clear()

    logger.info(f"총 {count}개 클라이언트 종료 완료")
    return count


def shutdown_all_sync() -> int:
    """모든 등록된 러너의 클라이언트를 종료 (동기 버전)

    시그널 핸들러 등 동기 컨텍스트에서 사용합니다.

    Returns:
        종료된 클라이언트 수
    """
    try:
        loop = asyncio.new_event_loop()
        count = loop.run_until_complete(shutdown_all())
        loop.close()
        return count
    except Exception as e:
        logger.warning(f"클라이언트 동기 종료 중 오류: {e}")
        return 0


# Compact retry 상수
COMPACT_RETRY_READ_TIMEOUT = 30  # 초: retry 시 receive_response() 읽기 타임아웃
MAX_COMPACT_RETRIES = 3  # compact 재시도 최대 횟수


@dataclass
class CompactRetryState:
    """Compact retry 외부 루프 상태"""
    events: list[dict] = field(default_factory=list)
    notified_count: int = 0
    retry_count: int = 0

    def snapshot(self) -> int:
        """현재 이벤트 수 기록 (외부 루프 시작 시 호출)"""
        return len(self.events)

    def did_compact(self, before: int) -> bool:
        """스냅샷 이후 compact가 발생했는지"""
        return len(self.events) > before

    def can_retry(self) -> bool:
        return self.retry_count < MAX_COMPACT_RETRIES

    def increment(self) -> None:
        self.retry_count += 1


@dataclass
class MessageState:
    """메시지 수신 루프 상태"""
    session_id: Optional[str] = None
    current_text: str = ""
    result_text: str = ""
    is_error: bool = False
    usage: Optional[dict] = None
    collected_messages: list[dict] = field(default_factory=list)
    msg_count: int = 0
    last_tool: str = ""
    last_progress_time: float = 0.0

    @property
    def has_result(self) -> bool:
        return bool(self.result_text or self.current_text)

    def reset_for_retry(self) -> None:
        """compact retry 시 텍스트 상태 리셋"""
        self.current_text = ""
        self.result_text = ""
        self.is_error = False


def _extract_last_assistant_text(collected_messages: list[dict]) -> str:
    """collected_messages에서 마지막 assistant 텍스트를 추출 (tool_use 제외)"""
    for msg in reversed(collected_messages):
        if msg.get("role") == "assistant" and not msg.get("content", "").startswith("[tool_use:"):
            return msg["content"]
    return ""


class ClaudeRunner:
    """Claude Code SDK 기반 실행기

    thread_ts 단위 인스턴스: 각 인스턴스가 자신의 client/pid/execution_loop를 소유합니다.
    """

    def __init__(
        self,
        thread_ts: str = "",
        *,
        working_dir: Optional[Path] = None,
        allowed_tools: Optional[list[str]] = None,
        disallowed_tools: Optional[list[str]] = None,
        mcp_config_path: Optional[Path] = None,
        debug_send_fn: Optional[DebugSendFn] = None,
    ):
        self.thread_ts = thread_ts
        self.working_dir = working_dir or Path.cwd()
        self.allowed_tools = allowed_tools  # None means no restriction
        self.disallowed_tools = disallowed_tools or DEFAULT_DISALLOWED_TOOLS
        self.mcp_config_path = mcp_config_path
        self.debug_send_fn = debug_send_fn

        # Instance-level client state
        self.client: Optional[ClaudeSDKClient] = None
        self.pid: Optional[int] = None
        self.execution_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    async def shutdown_all_clients(cls) -> int:
        """하위 호환: 모듈 레벨 shutdown_all()로 위임"""
        return await shutdown_all()

    @classmethod
    def shutdown_all_clients_sync(cls) -> int:
        """하위 호환: 모듈 레벨 shutdown_all_sync()로 위임"""
        return shutdown_all_sync()

    def run_sync(self, coro):
        """동기 컨텍스트에서 코루틴을 실행하는 브릿지"""
        return run_in_new_loop(coro)

    async def _get_or_create_client(
        self,
        options: Optional[ClaudeAgentOptions] = None,
    ) -> ClaudeSDKClient:
        """ClaudeSDKClient를 가져오거나 새로 생성"""
        if self.client is not None:
            logger.info(f"[DEBUG-CLIENT] 기존 클라이언트 재사용: thread={self.thread_ts}")
            return self.client

        import time as _time
        logger.info(f"[DEBUG-CLIENT] 새 InstrumentedClaudeClient 생성 시작: thread={self.thread_ts}")
        client = InstrumentedClaudeClient(
            options=options,
            on_rate_limit=self._observe_rate_limit,
            on_unknown_event=self._observe_unknown_event,
        )
        logger.info(f"[DEBUG-CLIENT] InstrumentedClaudeClient 인스턴스 생성 완료, connect() 호출...")
        t0 = _time.monotonic()
        try:
            await client.connect()
            elapsed = _time.monotonic() - t0
            logger.info(f"[DEBUG-CLIENT] connect() 성공: {elapsed:.2f}s")
        except Exception as e:
            elapsed = _time.monotonic() - t0
            logger.error(f"[DEBUG-CLIENT] connect() 실패: {elapsed:.2f}s, error={e}")
            try:
                await client.disconnect()
            except Exception:
                pass
            raise

        # subprocess PID 추출
        pid: Optional[int] = None
        try:
            transport = getattr(client, "_transport", None)
            if transport:
                process = getattr(transport, "_process", None)
                if process:
                    pid = getattr(process, "pid", None)
                    if pid:
                        logger.info(f"[DEBUG-CLIENT] subprocess PID 추출: {pid}")
        except Exception as e:
            logger.warning(f"[DEBUG-CLIENT] PID 추출 실패 (무시): {e}")

        self.client = client
        self.pid = pid
        logger.info(f"ClaudeSDKClient 생성: thread={self.thread_ts}, pid={pid}")
        return client

    async def _remove_client(self) -> None:
        """이 러너의 ClaudeSDKClient를 정리"""
        client = self.client
        pid = self.pid
        self.client = None
        self.pid = None

        if client is None:
            return

        try:
            await client.disconnect()
            logger.info(f"ClaudeSDKClient 정상 종료: thread={self.thread_ts}")
        except Exception as e:
            logger.warning(f"ClaudeSDKClient disconnect 실패: thread={self.thread_ts}, {e}")
            if pid:
                self._force_kill_process(pid, self.thread_ts)

    @staticmethod
    def _force_kill_process(pid: int, thread_ts: str) -> None:
        """psutil을 사용하여 프로세스를 강제 종료"""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
                logger.info(f"프로세스 강제 종료 성공 (terminate): PID {pid}, thread={thread_ts}")
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
                logger.info(f"프로세스 강제 종료 성공 (kill): PID {pid}, thread={thread_ts}")
        except psutil.NoSuchProcess:
            logger.info(f"프로세스 이미 종료됨: PID {pid}, thread={thread_ts}")
        except Exception as kill_error:
            logger.error(f"프로세스 강제 종료 실패: PID {pid}, thread={thread_ts}, {kill_error}")

    def _is_cli_alive(self) -> bool:
        """CLI 서브프로세스가 아직 살아있는지 확인"""
        if self.pid is None:
            return False
        try:
            proc = psutil.Process(self.pid)
            return proc.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def interrupt(self) -> bool:
        """이 러너에 인터럽트 전송 (동기)"""
        client = self.client
        loop = self.execution_loop
        if client is None or loop is None or not loop.is_running():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(client.interrupt(), loop)
            future.result(timeout=5)
            logger.info(f"인터럽트 전송: thread={self.thread_ts}")
            return True
        except Exception as e:
            logger.warning(f"인터럽트 실패: thread={self.thread_ts}, {e}")
            return False

    def _debug(self, message: str) -> None:
        """디버그 메시지 전송 (debug_send_fn이 있을 때만)"""
        if not self.debug_send_fn:
            return
        try:
            self.debug_send_fn(message)
        except Exception as e:
            logger.warning(f"디버그 메시지 전송 실패: {e}")

    def _observe_rate_limit(self, data: dict) -> None:
        """InstrumentedClaudeClient 콜백: rate_limit_event 관찰"""
        info = data.get("rate_limit_info", {})
        status = info.get("status", "")

        if status == "allowed":
            return

        if status == "allowed_warning":
            warning_msg = format_rate_limit_warning(info)
            logger.info(f"rate_limit allowed_warning: {warning_msg}")
            self._debug(warning_msg)
            return

        # rejected, rate_limited 등
        logger.warning(
            f"rate_limit_event (status={status}): "
            f"rateLimitType={info.get('rateLimitType')}, "
            f"resetsAt={info.get('resetsAt')}"
        )
        self._debug(
            f"⚠️ rate_limit `{status}` "
            f"(CLI 자체 처리 중, type={info.get('rateLimitType')})"
        )

    def _observe_unknown_event(self, msg_type: str, data: dict) -> None:
        """InstrumentedClaudeClient 콜백: unknown event 관찰"""
        logger.debug(f"Unknown event observed: {msg_type}")

    def _build_compact_hook(
        self,
        compact_events: Optional[list],
    ) -> Optional[dict]:
        """PreCompact 훅을 생성합니다."""
        if compact_events is None:
            return None

        async def on_pre_compact(
            hook_input: dict,
            tool_use_id: Optional[str],
            context: HookContext,
        ) -> HookJSONOutput:
            trigger = hook_input.get("trigger", "auto")
            logger.info(f"PreCompact 훅 트리거: trigger={trigger}")
            compact_events.append({
                "trigger": trigger,
                "message": f"컨텍스트 컴팩트 실행됨 (트리거: {trigger})",
            })
            return HookJSONOutput()

        return {
            "PreCompact": [
                HookMatcher(matcher=None, hooks=[on_pre_compact])
            ]
        }

    def _build_options(
        self,
        session_id: Optional[str] = None,
        compact_events: Optional[list] = None,
    ) -> tuple[ClaudeAgentOptions, Optional[IO[str]]]:
        """ClaudeAgentOptions와 stderr 파일을 반환합니다.

        Returns:
            (options, stderr_file)
            - stderr_file은 호출자가 닫아야 함 (sys.stderr이면 None)
        """
        thread_ts = self.thread_ts
        hooks = self._build_compact_hook(compact_events)

        # CLI stderr를 세션별 파일에 캡처
        import sys as _sys
        _runtime_dir = Path(__file__).resolve().parents[4]
        _stderr_suffix = thread_ts.replace(".", "_") if thread_ts else "default"
        _stderr_log_path = _runtime_dir / "logs" / f"cli_stderr_{_stderr_suffix}.log"
        logger.info(f"[DEBUG] CLI stderr 로그 경로: {_stderr_log_path}")
        _stderr_file = None
        _stderr_target = _sys.stderr
        try:
            _stderr_file = open(_stderr_log_path, "a", encoding="utf-8")
            _stderr_file.write(f"\n--- CLI stderr capture start: {datetime.now(timezone.utc).isoformat()} ---\n")
            _stderr_file.flush()
            _stderr_target = _stderr_file
        except Exception as _e:
            logger.warning(f"[DEBUG] stderr 캡처 파일 열기 실패: {_e}")
            if _stderr_file:
                _stderr_file.close()
            _stderr_file = None

        options = ClaudeAgentOptions(
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="bypassPermissions",
            cwd=self.working_dir,
            hooks=hooks,
            extra_args={"debug-to-stderr": None},
            debug_stderr=_stderr_target,
        )

        if session_id:
            options.resume = session_id

        return options, _stderr_file

    async def _notify_compact_events(
        self,
        compact_state: CompactRetryState,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]],
    ) -> None:
        """미통지 compact 이벤트를 on_compact 콜백으로 전달"""
        if not on_compact:
            return
        pending = compact_state.events[compact_state.notified_count:]
        if not pending:
            return
        for event in pending:
            try:
                await on_compact(event["trigger"], event["message"])
            except Exception as e:
                logger.warning(f"컴팩션 콜백 오류: {e}")
        compact_state.notified_count = len(compact_state.events)

    async def _receive_messages(
        self,
        client: "ClaudeSDKClient",
        compact_state: CompactRetryState,
        msg_state: MessageState,
        on_progress: Optional[Callable[[str], Awaitable[None]]],
        on_compact: Optional[Callable[[str, str], Awaitable[None]]],
    ) -> None:
        """내부 메시지 수신 루프: receive_response()에서 메시지를 읽어 상태 갱신"""
        thread_ts = self.thread_ts
        progress_interval = 2.0
        aiter = client.receive_response().__aiter__()

        while True:
            # retry 시 timeout 적용: CLI 종료 후 무한 대기 방지 [A]
            try:
                if compact_state.retry_count > 0:
                    message = await asyncio.wait_for(
                        aiter.__anext__(), timeout=COMPACT_RETRY_READ_TIMEOUT
                    )
                else:
                    message = await aiter.__anext__()
            except asyncio.TimeoutError:
                logger.warning(
                    f"Compact retry 읽기 타임아웃 ({COMPACT_RETRY_READ_TIMEOUT}s): "
                    f"thread={thread_ts}, retry={compact_state.retry_count}, "
                    f"pid={self.pid}, cli_alive={self._is_cli_alive()}"
                )
                return
            except StopAsyncIteration:
                return
            except MessageParseError as e:
                action, msg_type = classify_parse_error(e.data, log_fn=logger)
                if action is ParseAction.CONTINUE:
                    # rate_limit의 경우 추가 디버그 알림
                    if msg_type == "rate_limit_event":
                        info = e.data.get("rate_limit_info", {})
                        status = info.get("status", "")
                        if status == "allowed_warning":
                            self._debug(format_rate_limit_warning(info))
                        elif status not in ("allowed",):
                            self._debug(
                                f"⚠️ rate_limit `{status}` "
                                f"(CLI 자체 처리 중, type={info.get('rateLimitType')})"
                            )
                    continue
                raise

            msg_state.msg_count += 1

            # SystemMessage에서 세션 ID 추출
            if isinstance(message, SystemMessage):
                if hasattr(message, 'session_id'):
                    msg_state.session_id = message.session_id
                    logger.info(f"세션 ID: {msg_state.session_id}")

            # AssistantMessage에서 텍스트/도구 사용 추출
            elif isinstance(message, AssistantMessage):
                if hasattr(message, 'content'):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            msg_state.current_text = block.text

                            msg_state.collected_messages.append({
                                "role": "assistant",
                                "content": block.text,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })

                            if on_progress:
                                current_time = asyncio.get_running_loop().time()
                                if current_time - msg_state.last_progress_time >= progress_interval:
                                    try:
                                        display_text = msg_state.current_text
                                        if len(display_text) > 1000:
                                            display_text = "...\n" + display_text[-1000:]
                                        await on_progress(display_text)
                                        msg_state.last_progress_time = current_time
                                    except Exception as e:
                                        logger.warning(f"진행 상황 콜백 오류: {e}")

                        elif isinstance(block, ToolUseBlock):
                            tool_input = ""
                            if block.input:
                                tool_input = json.dumps(block.input, ensure_ascii=False)
                                if len(tool_input) > 2000:
                                    tool_input = tool_input[:2000] + "..."
                            msg_state.last_tool = block.name
                            logger.info(f"[TOOL_USE] {block.name}: {tool_input[:500]}")
                            msg_state.collected_messages.append({
                                "role": "assistant",
                                "content": f"[tool_use: {block.name}] {tool_input}",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })

                        elif isinstance(block, ToolResultBlock):
                            content = ""
                            if isinstance(block.content, str):
                                content = block.content[:2000]
                            elif block.content:
                                content = json.dumps(block.content, ensure_ascii=False)[:2000]
                            logger.info(f"[TOOL_RESULT] {content[:500]}")
                            msg_state.collected_messages.append({
                                "role": "tool",
                                "content": content,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })

            # ResultMessage에서 최종 결과 추출
            elif isinstance(message, ResultMessage):
                if hasattr(message, 'is_error'):
                    msg_state.is_error = message.is_error
                if hasattr(message, 'result'):
                    msg_state.result_text = message.result
                if hasattr(message, 'session_id') and message.session_id:
                    msg_state.session_id = message.session_id
                if hasattr(message, 'usage') and message.usage:
                    msg_state.usage = message.usage

            # 컴팩션 이벤트 알림
            await self._notify_compact_events(compact_state, on_compact)

    def _evaluate_compact_retry(
        self,
        compact_state: CompactRetryState,
        msg_state: MessageState,
        before_snapshot: int,
    ) -> bool:
        """Compact retry 판정. True이면 외부 루프 continue, False이면 break.

        Side effect: CLI 종료 시 collected_messages에서 fallback 텍스트 복원.
        """
        compact_happened = compact_state.did_compact(before_snapshot)

        if not compact_happened:
            return False

        if msg_state.has_result:
            logger.info(
                f"Compact 발생했으나 이미 유효한 결과 있음 - retry 생략 "
                f"(result_text={len(msg_state.result_text)} chars, "
                f"current_text={len(msg_state.current_text)} chars, "
                f"compact_retry_count={compact_state.retry_count}/{MAX_COMPACT_RETRIES})"
            )
            return False

        if not compact_state.can_retry():
            return False

        # CLI 프로세스 상태 확인 [B]
        cli_alive = self._is_cli_alive()
        logger.info(
            f"Compact retry 판정: pid={self.pid}, cli_alive={cli_alive}, "
            f"has_result={msg_state.has_result}, current_text={len(msg_state.current_text)} chars, "
            f"result_text={len(msg_state.result_text)} chars, "
            f"collected_msgs={len(msg_state.collected_messages)}, "
            f"retry={compact_state.retry_count}/{MAX_COMPACT_RETRIES}"
        )

        if not cli_alive:
            # CLI 종료: collected_messages에서 마지막 텍스트 복원 [C]
            logger.warning(
                f"Compact retry 생략: CLI 프로세스 이미 종료 "
                f"(pid={self.pid}, thread={self.thread_ts})"
            )
            fallback_text = _extract_last_assistant_text(msg_state.collected_messages)
            if fallback_text:
                msg_state.current_text = fallback_text
                logger.info(
                    f"Fallback: collected_messages에서 텍스트 복원 "
                    f"({len(fallback_text)} chars)"
                )
            return False

        compact_state.increment()
        logger.info(
            f"Compact 후 응답 재수신 시도 "
            f"(retry={compact_state.retry_count}/{MAX_COMPACT_RETRIES}, "
            f"session_id={msg_state.session_id})"
        )
        return True

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> EngineResult:
        """Claude Code 실행

        Returns:
            EngineResult: 엔진 순수 실행 결과.
                응용 마커(UPDATE/RESTART/LIST_RUN) 파싱과
                OM 관찰 트리거는 호출부에서 수행합니다.
        """
        return await self._execute(prompt, session_id, on_progress, on_compact)

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> EngineResult:
        """실제 실행 로직 (ClaudeSDKClient 기반)"""
        thread_ts = self.thread_ts
        compact_state = CompactRetryState()
        options, stderr_file = self._build_options(session_id, compact_events=compact_state.events)
        logger.info(f"Claude Code SDK 실행 시작 (cwd={self.working_dir})")
        logger.info(f"[DEBUG-OPTIONS] permission_mode={options.permission_mode}")
        logger.info(f"[DEBUG-OPTIONS] cwd={options.cwd}")
        logger.info(f"[DEBUG-OPTIONS] mcp_servers={options.mcp_servers}")
        logger.info(f"[DEBUG-OPTIONS] resume={options.resume}")
        logger.info(f"[DEBUG-OPTIONS] allowed_tools count={len(options.allowed_tools) if options.allowed_tools else 0}")
        logger.info(f"[DEBUG-OPTIONS] disallowed_tools count={len(options.disallowed_tools) if options.disallowed_tools else 0}")
        logger.info(f"[DEBUG-OPTIONS] hooks={'yes' if options.hooks else 'no'}")

        # 현재 실행 루프를 인스턴스에 등록 (interrupt에서 사용)
        self.execution_loop = asyncio.get_running_loop()

        # 모듈 레지스트리에 등록 (thread_ts가 있을 때만)
        if thread_ts:
            register_runner(self)

        msg_state = MessageState(last_progress_time=asyncio.get_running_loop().time())
        _session_start = datetime.now(timezone.utc)

        try:
            client = await self._get_or_create_client(options=options)

            await client.query(prompt)

            # Compact retry 외부 루프:
            # receive_response()는 ResultMessage에서 즉시 return하므로,
            # autocompact가 현재 턴의 ResultMessage를 발생시키면
            # compact 후의 응답을 수신하지 못함.
            # compact 이벤트가 감지되면 receive_response()를 재호출하여
            # post-compact 응답을 계속 수신.
            while True:
                before = compact_state.snapshot()

                await self._receive_messages(
                    client, compact_state, msg_state, on_progress, on_compact,
                )

                # PreCompact 훅 콜백 실행을 위한 이벤트 루프 양보
                await asyncio.sleep(0)

                # 미통지 compact 이벤트 알림
                await self._notify_compact_events(compact_state, on_compact)

                # Compact retry 판정
                if self._evaluate_compact_retry(compact_state, msg_state, before):
                    msg_state.reset_for_retry()
                    continue

                # 무출력 종료 디버깅
                if not msg_state.has_result:
                    _dur = (datetime.now(timezone.utc) - _session_start).total_seconds()
                    dump = build_session_dump(
                        reason="CLI exited with no output (StopAsyncIteration)",
                        pid=self.pid,
                        duration_sec=_dur,
                        message_count=msg_state.msg_count,
                        last_tool=msg_state.last_tool,
                        current_text_len=len(msg_state.current_text),
                        result_text_len=len(msg_state.result_text),
                        session_id=msg_state.session_id,
                        active_clients_count=len(_registry),
                        thread_ts=thread_ts,
                    )
                    logger.warning(f"세션 무출력 종료 덤프: thread={thread_ts}, duration={_dur:.1f}s, msgs={msg_state.msg_count}, last_tool={msg_state.last_tool}")
                    self._debug(dump)
                break

            # 정상 완료
            output = msg_state.result_text or msg_state.current_text

            return EngineResult(
                success=not msg_state.is_error,
                output=output,
                session_id=msg_state.session_id,
                collected_messages=msg_state.collected_messages,
                is_error=msg_state.is_error,
                usage=msg_state.usage,
            )

        except FileNotFoundError as e:
            logger.error(f"Claude Code CLI를 찾을 수 없습니다: {e}")
            return EngineResult(
                success=False,
                output="",
                error="Claude Code CLI를 찾을 수 없습니다. claude 명령어가 PATH에 있는지 확인하세요."
            )
        except ProcessError as e:
            friendly_msg = classify_process_error(e)
            logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}, stderr={e.stderr}, friendly={friendly_msg}")
            _dur = (datetime.now(timezone.utc) - _session_start).total_seconds()
            dump = build_session_dump(
                reason="ProcessError",
                pid=self.pid,
                duration_sec=_dur,
                message_count=msg_state.msg_count,
                last_tool=msg_state.last_tool,
                current_text_len=len(msg_state.current_text),
                result_text_len=len(msg_state.result_text),
                session_id=msg_state.session_id,
                exit_code=e.exit_code,
                error_detail=str(e.stderr or e),
                active_clients_count=len(_registry),
                thread_ts=thread_ts,
            )
            self._debug(dump)
            return EngineResult(
                success=False,
                output=msg_state.current_text,
                session_id=msg_state.session_id,
                error=friendly_msg,
            )
        except MessageParseError as e:
            action, msg_type = classify_parse_error(e.data, log_fn=logger)

            if msg_type == "rate_limit_event":
                logger.warning(f"rate_limit_event (외부 catch): {e}")
                return EngineResult(
                    success=False,
                    output=msg_state.current_text,
                    session_id=msg_state.session_id,
                    error="사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요.",
                )

            if action is ParseAction.CONTINUE:
                # unknown type이 외부까지 전파된 경우
                logger.warning(f"Unknown message type escaped loop: {msg_type}")
                return EngineResult(
                    success=False,
                    output=msg_state.current_text,
                    session_id=msg_state.session_id,
                    error=f"알 수 없는 메시지 타입: {msg_type}",
                )

            logger.exception(f"SDK 메시지 파싱 오류: {e}")
            return EngineResult(
                success=False,
                output=msg_state.current_text,
                session_id=msg_state.session_id,
                error="Claude 응답 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )
        except Exception as e:
            logger.exception(f"Claude Code SDK 실행 오류: {e}")
            return EngineResult(
                success=False,
                output=msg_state.current_text,
                session_id=msg_state.session_id,
                error=str(e)
            )
        finally:
            await self._remove_client()
            self.execution_loop = None
            if thread_ts:
                remove_runner(thread_ts)
            if stderr_file is not None:
                try:
                    stderr_file.close()
                except Exception:
                    pass

    async def compact_session(self, session_id: str) -> EngineResult:
        """세션 컴팩트 처리"""
        if not session_id:
            return EngineResult(
                success=False,
                output="",
                error="세션 ID가 없습니다."
            )

        logger.info(f"세션 컴팩트 시작: {session_id}")
        result = await self._execute("/compact", session_id)

        if result.success:
            logger.info(f"세션 컴팩트 완료: {session_id}")
        else:
            logger.error(f"세션 컴팩트 실패: {session_id}, {result.error}")

        return result



# 테스트용
async def main():
    runner = ClaudeRunner()
    result = await runner.run("안녕? 간단히 인사해줘. 3줄 이내로.")
    print(f"Success: {result.success}")
    print(f"Session ID: {result.session_id}")
    print(f"Output:\n{result.output}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
