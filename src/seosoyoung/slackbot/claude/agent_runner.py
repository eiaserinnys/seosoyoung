"""Claude Code SDK 기반 실행기"""

import asyncio
import json
import logging
import os
import re
import time as _time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Optional, Callable, Awaitable

import psutil
from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient, HookMatcher, HookContext
from claude_code_sdk._errors import MessageParseError, ProcessError
from claude_code_sdk.types import (
    AssistantMessage,
    HookJSONOutput,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from seosoyoung.slackbot.claude.diagnostics import (
    DebugSendFn,
    build_session_dump,
    classify_process_error,
    format_rate_limit_warning,
    send_debug_to_slack,
)
from seosoyoung.slackbot.claude.types import (
    PrepareMemoryFn,
    TriggerObservationFn,
    OnCompactOMFlagFn,
)
from seosoyoung.utils.async_bridge import run_in_new_loop

logger = logging.getLogger(__name__)

# Claude Code 기본 금지 도구
DEFAULT_DISALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Task",
]


@dataclass
class ClaudeResult:
    """Claude Code 실행 결과"""
    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    update_requested: bool = False
    restart_requested: bool = False
    list_run: Optional[str] = None  # <!-- LIST_RUN: 리스트명 --> 마커로 추출된 리스트 이름
    collected_messages: list[dict] = field(default_factory=list)  # OM용 대화 수집
    interrupted: bool = False  # interrupt로 중단된 경우 True
    is_error: bool = False  # ResultMessage.is_error가 True인 경우
    usage: Optional[dict] = None  # ResultMessage.usage (input_tokens, output_tokens 등)
    anchor_ts: str = ""  # OM 디버그 채널 세션 스레드 앵커 ts


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
        channel: Optional[str] = None,
        working_dir: Optional[Path] = None,
        allowed_tools: Optional[list[str]] = None,
        disallowed_tools: Optional[list[str]] = None,
        mcp_config_path: Optional[Path] = None,
        debug_send_fn: Optional[DebugSendFn] = None,
        prepare_memory_fn: Optional[PrepareMemoryFn] = None,
        trigger_observation_fn: Optional[TriggerObservationFn] = None,
        on_compact_om_flag: Optional[OnCompactOMFlagFn] = None,
    ):
        self.thread_ts = thread_ts
        self.channel = channel
        self.working_dir = working_dir or Path.cwd()
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools or DEFAULT_DISALLOWED_TOOLS
        self.mcp_config_path = mcp_config_path
        self.debug_send_fn = debug_send_fn
        self.prepare_memory_fn = prepare_memory_fn
        self.trigger_observation_fn = trigger_observation_fn
        self.on_compact_om_flag = on_compact_om_flag

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
        options: Optional[ClaudeCodeOptions] = None,
    ) -> ClaudeSDKClient:
        """ClaudeSDKClient를 가져오거나 새로 생성"""
        if self.client is not None:
            logger.info(f"[DEBUG-CLIENT] 기존 클라이언트 재사용: thread={self.thread_ts}")
            return self.client

        import time as _time
        logger.info(f"[DEBUG-CLIENT] 새 ClaudeSDKClient 생성 시작: thread={self.thread_ts}")
        client = ClaudeSDKClient(options=options)
        logger.info(f"[DEBUG-CLIENT] ClaudeSDKClient 인스턴스 생성 완료, connect() 호출...")
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

    def _build_compact_hook(
        self,
        compact_events: Optional[list],
    ) -> Optional[dict]:
        """PreCompact 훅을 생성합니다."""
        if compact_events is None:
            return None

        thread_ts = self.thread_ts

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

            # OM: 컴팩션 시 다음 요청에 관찰 로그 재주입하도록 플래그 설정
            if thread_ts and self.on_compact_om_flag:
                try:
                    self.on_compact_om_flag(thread_ts)
                except Exception as e:
                    logger.warning(f"OM inject 플래그 설정 실패 (PreCompact, 무시): {e}")

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
        user_id: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> tuple[ClaudeCodeOptions, Optional[str], str, Optional[IO[str]]]:
        """ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts, stderr 파일을 반환합니다.

        Returns:
            (options, memory_prompt, anchor_ts, stderr_file)
            - memory_prompt는 첫 번째 query에 프리픽스로 주입합니다.
            - anchor_ts는 디버그 채널의 세션 스레드 앵커 메시지 ts입니다.
            - stderr_file은 호출자가 닫아야 함 (sys.stderr이면 None)
        """
        thread_ts = self.thread_ts
        channel = self.channel
        hooks = self._build_compact_hook(compact_events)

        # 슬랙 컨텍스트가 있으면 env에 주입 (MCP 서버용)
        env: dict[str, str] = {}
        if self.channel and self.thread_ts:
            env["SLACK_CHANNEL"] = self.channel
            env["SLACK_THREAD_TS"] = self.thread_ts

        # CLI stderr를 세션별 파일에 캡처
        import sys as _sys
        _runtime_dir = Path(os.environ.get("SEOSOYOUNG_RUNTIME", Path(__file__).resolve().parents[4]))
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

        options = ClaudeCodeOptions(
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="bypassPermissions",
            cwd=self.working_dir,
            hooks=hooks,
            env=env,
            extra_args={"debug-to-stderr": None},
            debug_stderr=_stderr_target,
        )

        if session_id:
            options.resume = session_id

        memory_prompt: Optional[str] = None
        anchor_ts: str = ""
        if self.prepare_memory_fn:
            memory_prompt, anchor_ts = self.prepare_memory_fn(
                self.thread_ts, self.channel, session_id, prompt,
            )

        return options, memory_prompt, anchor_ts, _stderr_file

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
        channel = self.channel
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
                msg_type = e.data.get("type") if isinstance(e.data, dict) else None

                if msg_type == "rate_limit_event":
                    # Agent SDK 방식: 모든 status에서 continue (CLI가 자체 처리)
                    rate_limit_info = e.data.get("rate_limit_info", {})
                    status = rate_limit_info.get("status", "")

                    if status == "allowed":
                        continue

                    if status == "allowed_warning":
                        warning_msg = format_rate_limit_warning(rate_limit_info)
                        logger.info(f"rate_limit allowed_warning: {warning_msg}")
                        self._debug(warning_msg)
                        continue

                    # rejected, rate_limited 등 — CLI가 자체 대기/재시도하므로 skip
                    logger.warning(
                        f"rate_limit_event skip (status={status}): "
                        f"rateLimitType={rate_limit_info.get('rateLimitType')}, "
                        f"resetsAt={rate_limit_info.get('resetsAt')}"
                    )
                    self._debug(
                        f"⚠️ rate_limit `{status}` "
                        f"(CLI 자체 처리 중, type={rate_limit_info.get('rateLimitType')})"
                    )
                    continue  # 핵심 변경: return → continue

                if msg_type is not None:
                    # 미래의 unknown type → forward-compatible skip
                    logger.debug(f"Unknown message type skipped: {msg_type}")
                    continue

                # type 필드조차 없는 진짜 파싱 에러
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
                                current_time = _time.monotonic()
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
        user_id: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> ClaudeResult:
        """Claude Code 실행"""
        thread_ts = self.thread_ts
        result = await self._execute(prompt, session_id, on_progress, on_compact, user_id)

        # OM: 세션 종료 후 비동기로 관찰 파이프라인 트리거
        if self.trigger_observation_fn and result.success and user_id and thread_ts and result.collected_messages:
            observation_input = user_message if user_message is not None else prompt
            self.trigger_observation_fn(thread_ts, user_id, observation_input, result.collected_messages, anchor_ts=result.anchor_ts)

        return result

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        user_id: Optional[str] = None,
    ) -> ClaudeResult:
        """실제 실행 로직 (ClaudeSDKClient 기반)"""
        thread_ts = self.thread_ts
        channel = self.channel
        compact_state = CompactRetryState()
        options, memory_prompt, anchor_ts, stderr_file = self._build_options(session_id, compact_events=compact_state.events, user_id=user_id, prompt=prompt)
        logger.info(f"Claude Code SDK 실행 시작 (cwd={self.working_dir})")
        logger.info(f"[DEBUG-OPTIONS] permission_mode={options.permission_mode}")
        logger.info(f"[DEBUG-OPTIONS] cwd={options.cwd}")
        logger.info(f"[DEBUG-OPTIONS] env={options.env}")
        logger.info(f"[DEBUG-OPTIONS] mcp_servers={options.mcp_servers}")
        logger.info(f"[DEBUG-OPTIONS] resume={options.resume}")
        logger.info(f"[DEBUG-OPTIONS] allowed_tools count={len(options.allowed_tools) if options.allowed_tools else 0}")
        logger.info(f"[DEBUG-OPTIONS] disallowed_tools count={len(options.disallowed_tools) if options.disallowed_tools else 0}")
        logger.info(f"[DEBUG-OPTIONS] memory_prompt length={len(memory_prompt) if memory_prompt else 0}")
        logger.info(f"[DEBUG-OPTIONS] hooks={'yes' if options.hooks else 'no'}")

        # 현재 실행 루프를 인스턴스에 등록 (interrupt에서 사용)
        self.execution_loop = asyncio.get_running_loop()

        # 모듈 레지스트리에 등록 (thread_ts가 있을 때만)
        if thread_ts:
            register_runner(self)

        msg_state = MessageState(last_progress_time=_time.monotonic())
        _session_start = datetime.now(timezone.utc)

        try:
            client = await self._get_or_create_client(options=options)

            # OM 메모리를 첫 번째 메시지에 프리픽스로 주입
            effective_prompt = prompt
            if memory_prompt:
                effective_prompt = (
                    f"{memory_prompt}\n\n"
                    f"위 컨텍스트를 참고하여 질문에 답변해주세요.\n\n"
                    f"사용자의 질문: {prompt}"
                )
                logger.info(f"OM 메모리 프리픽스 주입 완료 (prompt 길이: {len(effective_prompt)})")

            await client.query(effective_prompt)

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
                if not msg_state.has_result and channel and thread_ts:
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
                    send_debug_to_slack(channel, thread_ts, dump, send_fn=self.debug_send_fn)
                break

            # 정상 완료
            output = msg_state.result_text or msg_state.current_text
            update_requested = "<!-- UPDATE -->" in output
            restart_requested = "<!-- RESTART -->" in output
            list_run_match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
            list_run = list_run_match.group(1).strip() if list_run_match else None

            if update_requested:
                logger.info("업데이트 요청 마커 감지: <!-- UPDATE -->")
            if restart_requested:
                logger.info("재시작 요청 마커 감지: <!-- RESTART -->")
            if list_run:
                logger.info(f"리스트 정주행 요청 마커 감지: {list_run}")

            return ClaudeResult(
                success=not msg_state.is_error,
                output=output,
                session_id=msg_state.session_id,
                update_requested=update_requested,
                restart_requested=restart_requested,
                list_run=list_run,
                collected_messages=msg_state.collected_messages,
                is_error=msg_state.is_error,
                usage=msg_state.usage,
                anchor_ts=anchor_ts,
            )

        except FileNotFoundError as e:
            logger.error(f"Claude Code CLI를 찾을 수 없습니다: {e}")
            return ClaudeResult(
                success=False,
                output="",
                error="Claude Code CLI를 찾을 수 없습니다. claude 명령어가 PATH에 있는지 확인하세요."
            )
        except ProcessError as e:
            friendly_msg = classify_process_error(e)
            logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}, stderr={e.stderr}, friendly={friendly_msg}")
            if channel and thread_ts:
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
                send_debug_to_slack(channel, thread_ts, dump, send_fn=self.debug_send_fn)
            return ClaudeResult(
                success=False,
                output=msg_state.current_text,
                session_id=msg_state.session_id,
                error=friendly_msg,
            )
        except MessageParseError as e:
            msg_type = e.data.get("type") if isinstance(e.data, dict) else None

            if msg_type == "rate_limit_event":
                logger.warning(f"rate_limit_event (외부 catch): {e}")
                return ClaudeResult(
                    success=False,
                    output=msg_state.current_text,
                    session_id=msg_state.session_id,
                    error="사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요.",
                )

            if msg_type is not None:
                # unknown type이 외부까지 전파된 경우
                logger.warning(f"Unknown message type escaped loop: {msg_type}")
                return ClaudeResult(
                    success=False,
                    output=msg_state.current_text,
                    session_id=msg_state.session_id,
                    error=f"알 수 없는 메시지 타입: {msg_type}",
                )

            logger.exception(f"SDK 메시지 파싱 오류: {e}")
            return ClaudeResult(
                success=False,
                output=msg_state.current_text,
                session_id=msg_state.session_id,
                error="Claude 응답 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )
        except Exception as e:
            logger.exception(f"Claude Code SDK 실행 오류: {e}")
            return ClaudeResult(
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

    async def compact_session(self, session_id: str) -> ClaudeResult:
        """세션 컴팩트 처리"""
        if not session_id:
            return ClaudeResult(
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
