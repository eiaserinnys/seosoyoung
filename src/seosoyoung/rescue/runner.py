"""Claude Code SDK 실행기 (메인 봇 기본 대화 기능 완전 복제)

메인 봇의 ClaudeAgentRunner에서 핵심 로직을 복제한 버전:
- _classify_process_error: ProcessError를 사용자 친화적 메시지로 변환
- _build_options: ClaudeCodeOptions 생성 (env 주입, PreCompact 훅, stderr 캡처)
- _get_or_create_client / _remove_client: 클라이언트 생명주기 관리
- _execute: on_progress 콜백, on_compact, rate_limit 처리
- interrupt / compact_session: 세션 제어
- run / run_sync: async/sync 인터페이스

제외: OM, Recall, 트렐로 연동, 번역, 채널 관찰, 프로필, 정주행, NPC, Remote 모드
"""

import asyncio
import logging
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient, HookMatcher, HookContext
from claude_code_sdk._errors import MessageParseError, ProcessError
from claude_code_sdk.types import (
    AssistantMessage,
    HookJSONOutput,
    ResultMessage,
    SystemMessage,
    TextBlock,
)

from seosoyoung.rescue.config import RescueConfig

logger = logging.getLogger(__name__)

# 허용 도구: 기본 도구 + 슬랙 MCP 도구 (NPC 제외)
ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "TodoWrite",
    "mcp__seosoyoung-attach__slack_attach_file",
    "mcp__seosoyoung-attach__slack_get_context",
    "mcp__seosoyoung-attach__slack_post_message",
    "mcp__seosoyoung-attach__slack_download_thread_files",
    "mcp__seosoyoung-attach__slack_generate_image",
]

DISALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Task",
]


def _classify_process_error(e: ProcessError) -> str:
    """ProcessError를 사용자 친화적 메시지로 변환."""
    error_str = str(e).lower()
    stderr = (e.stderr or "").lower()
    combined = f"{error_str} {stderr}"

    if any(kw in combined for kw in ["usage limit", "rate limit", "quota", "too many requests", "429"]):
        return "사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요."

    if any(kw in combined for kw in ["unauthorized", "401", "auth", "token", "credentials", "forbidden", "403"]):
        return "인증에 실패했습니다. 관리자에게 문의해주세요."

    if any(kw in combined for kw in ["network", "connection", "timeout", "econnrefused", "dns"]):
        return "네트워크 연결에 문제가 있습니다. 잠시 후 다시 시도해주세요."

    if e.exit_code == 1:
        return (
            "Claude Code가 비정상 종료했습니다. "
            "사용량 제한이나 일시적 오류일 수 있으니 잠시 후 다시 시도해주세요."
        )

    return f"Claude Code 실행 중 오류가 발생했습니다 (exit code: {e.exit_code})"


from seosoyoung.claude.agent_runner import run_in_new_loop as _run_in_new_loop


@dataclass
class RescueResult:
    """실행 결과"""

    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    interrupted: bool = False
    usage: Optional[dict] = None


class RescueRunner:
    """Claude Code SDK 실행기 (메인 봇 기본 대화 기능 복제)

    메인 봇의 ClaudeAgentRunner와 동일한 패턴:
    - run_in_new_loop로 각 실행마다 격리된 이벤트 루프 사용
    - _get_or_create_client / _remove_client로 클라이언트 생명주기 관리
    - on_progress / on_compact 콜백
    - interrupt / compact_session
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active_clients: dict[str, ClaudeSDKClient] = {}
        self._execution_loops: dict[str, asyncio.AbstractEventLoop] = {}
        self._clients_lock = threading.Lock()

    def run_sync(self, coro):
        """동기 컨텍스트에서 코루틴을 실행하는 브릿지

        별도 스레드에서 새 이벤트 루프를 생성하여 코루틴을 실행합니다.
        """
        return _run_in_new_loop(coro)

    def _build_options(
        self,
        session_id: Optional[str] = None,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
        compact_events: Optional[list] = None,
    ) -> tuple[ClaudeCodeOptions, Optional[object]]:
        """ClaudeCodeOptions를 생성합니다.

        Args:
            session_id: 세션 재개용 ID
            channel: 슬랙 채널 ID (MCP 서버 env 주입용)
            thread_ts: 스레드 타임스탬프 (MCP 서버 env 주입용)
            compact_events: PreCompact 훅 이벤트 수집 리스트

        Returns:
            (options, stderr_file): stderr_file은 호출자가 닫아야 함 (sys.stderr이면 None)
        """
        working_dir = RescueConfig.get_working_dir()

        # PreCompact 훅 설정
        hooks = None
        if compact_events is not None:
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

            hooks = {
                "PreCompact": [
                    HookMatcher(matcher=None, hooks=[on_pre_compact])
                ]
            }

        # env: 슬랙 컨텍스트 주입 (MCP 서버용)
        env: dict[str, str] = {}
        if channel and thread_ts:
            env["SLACK_CHANNEL"] = channel
            env["SLACK_THREAD_TS"] = thread_ts

        # CLI stderr를 파일에 캡처 (디버깅용)
        _runtime_dir = Path(__file__).resolve().parents[3]
        _stderr_log_path = _runtime_dir / "logs" / "rescue_cli_stderr.log"
        _stderr_file = None
        _stderr_target = sys.stderr
        try:
            _stderr_file = open(_stderr_log_path, "a", encoding="utf-8")
            _stderr_file.write(f"\n--- rescue CLI stderr: {datetime.now(timezone.utc).isoformat()} resume={session_id} ---\n")
            _stderr_file.flush()
            _stderr_target = _stderr_file
        except Exception as _e:
            logger.warning(f"stderr 캡처 파일 열기 실패: {_e}")
            if _stderr_file:
                _stderr_file.close()
            _stderr_file = None

        options = ClaudeCodeOptions(
            allowed_tools=ALLOWED_TOOLS,
            disallowed_tools=DISALLOWED_TOOLS,
            permission_mode="bypassPermissions",
            cwd=working_dir,
            hooks=hooks,
            env=env,
            extra_args={"debug-to-stderr": None},
            debug_stderr=_stderr_target,
        )

        if session_id:
            options.resume = session_id

        return options, _stderr_file

    async def _get_or_create_client(
        self,
        client_key: str,
        options: Optional[ClaudeCodeOptions] = None,
    ) -> ClaudeSDKClient:
        """클라이언트를 가져오거나 새로 생성"""
        with self._clients_lock:
            if client_key in self._active_clients:
                logger.info(f"기존 클라이언트 재사용: key={client_key}")
                return self._active_clients[client_key]

        logger.info(f"새 ClaudeSDKClient 생성: key={client_key}")
        client = ClaudeSDKClient(options=options)
        try:
            await client.connect()
            logger.info(f"ClaudeSDKClient connect 성공: key={client_key}")
        except Exception as e:
            logger.error(f"ClaudeSDKClient connect 실패: key={client_key}, error={e}")
            try:
                await client.disconnect()
            except Exception:
                pass
            raise
        with self._clients_lock:
            self._active_clients[client_key] = client
        return client

    async def _remove_client(self, client_key: str) -> None:
        """클라이언트를 정리 (disconnect 후 딕셔너리에서 제거)"""
        with self._clients_lock:
            client = self._active_clients.pop(client_key, None)
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f"ClaudeSDKClient disconnect 오류 (무시): key={client_key}, {e}")
        logger.info(f"ClaudeSDKClient 제거: key={client_key}")

    def interrupt(self, thread_ts: str) -> bool:
        """실행 중인 스레드에 인터럽트 전송 (동기)

        Args:
            thread_ts: 스레드 타임스탬프

        Returns:
            True: 인터럽트 성공, False: 해당 스레드에 클라이언트 없음 또는 실패
        """
        with self._clients_lock:
            client = self._active_clients.get(thread_ts)
            loop = self._execution_loops.get(thread_ts)
        if client is None or loop is None or not loop.is_running():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(client.interrupt(), loop)
            future.result(timeout=5)
            logger.info(f"인터럽트 전송: thread={thread_ts}")
            return True
        except Exception as e:
            logger.warning(f"인터럽트 실패: thread={thread_ts}, {e}")
            return False

    async def compact_session(self, session_id: str) -> RescueResult:
        """세션 컴팩트 처리

        Args:
            session_id: 컴팩트할 세션 ID

        Returns:
            RescueResult (compact 결과)
        """
        if not session_id:
            return RescueResult(
                success=False,
                output="",
                error="세션 ID가 없습니다.",
            )

        logger.info(f"세션 컴팩트 시작: {session_id}")
        result = await self._execute("/compact", session_id=session_id)

        if result.success:
            logger.info(f"세션 컴팩트 완료: {session_id}")
        else:
            logger.error(f"세션 컴팩트 실패: {session_id}, {result.error}")

        return result

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        channel: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> RescueResult:
        """Claude Code 실행 (async, lock 포함)"""
        with self._lock:
            return await self._execute(
                prompt,
                session_id=session_id,
                thread_ts=thread_ts,
                channel=channel,
                on_progress=on_progress,
                on_compact=on_compact,
            )

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        channel: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> RescueResult:
        """실제 실행 로직 (메인 봇 _execute와 동일한 구조)"""
        compact_events: list[dict] = []
        compact_notified_count = 0
        options, stderr_file = self._build_options(
            session_id=session_id,
            channel=channel,
            thread_ts=thread_ts,
            compact_events=compact_events,
        )

        logger.info(f"Claude Code SDK 실행 (cwd={options.cwd}, resume={session_id})")

        # 클라이언트 키: thread_ts가 없으면 임시 키
        client_key = thread_ts or f"_ephemeral_{id(asyncio.current_task())}"

        # 현재 실행 루프를 등록 (interrupt에서 사용)
        with self._clients_lock:
            self._execution_loops[client_key] = asyncio.get_running_loop()

        result_session_id = None
        current_text = ""
        result_text = ""
        result_is_error = False
        result_usage: Optional[dict] = None
        last_progress_time = asyncio.get_event_loop().time()
        progress_interval = 2.0
        try:
            client = await self._get_or_create_client(client_key, options=options)
            await client.query(prompt)

            aiter = client.receive_response().__aiter__()
            while True:
                try:
                    message = await aiter.__anext__()
                except StopAsyncIteration:
                    break
                except MessageParseError as e:
                    if e.data and e.data.get("type") == "rate_limit_event":
                        logger.warning(f"rate_limit_event 수신, graceful 종료")
                        break
                    raise

                if isinstance(message, SystemMessage):
                    if hasattr(message, "session_id"):
                        result_session_id = message.session_id
                        logger.info(f"세션 ID: {result_session_id}")

                elif isinstance(message, AssistantMessage):
                    if hasattr(message, "content"):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                current_text = block.text

                                # 진행 상황 콜백 (2초 간격)
                                if on_progress:
                                    current_time = asyncio.get_event_loop().time()
                                    if current_time - last_progress_time >= progress_interval:
                                        try:
                                            display_text = current_text
                                            if len(display_text) > 1000:
                                                display_text = "...\n" + display_text[-1000:]
                                            await on_progress(display_text)
                                            last_progress_time = current_time
                                        except Exception as e:
                                            logger.warning(f"진행 상황 콜백 오류: {e}")

                elif isinstance(message, ResultMessage):
                    if hasattr(message, "is_error"):
                        result_is_error = message.is_error
                    if hasattr(message, "result"):
                        result_text = message.result
                    if hasattr(message, "session_id") and message.session_id:
                        result_session_id = message.session_id
                    if hasattr(message, "usage") and message.usage:
                        result_usage = message.usage

                # 컴팩션 이벤트 확인
                if on_compact and len(compact_events) > compact_notified_count:
                    for event in compact_events[compact_notified_count:]:
                        try:
                            await on_compact(event["trigger"], event["message"])
                        except Exception as e:
                            logger.warning(f"컴팩션 콜백 오류: {e}")
                    compact_notified_count = len(compact_events)

            output = result_text or current_text

            return RescueResult(
                success=True,
                output=output,
                session_id=result_session_id,
                interrupted=result_is_error,
                usage=result_usage,
            )

        except FileNotFoundError as e:
            logger.error(f"Claude Code CLI를 찾을 수 없습니다: {e}")
            return RescueResult(
                success=False,
                output="",
                error="Claude Code CLI를 찾을 수 없습니다. claude 명령어가 PATH에 있는지 확인하세요.",
            )
        except ProcessError as e:
            friendly_msg = _classify_process_error(e)
            logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}, stderr={e.stderr}, friendly={friendly_msg}")
            return RescueResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=friendly_msg,
            )
        except MessageParseError as e:
            if e.data and e.data.get("type") == "rate_limit_event":
                logger.warning(f"rate_limit_event로 실행 실패: {e}")
                return RescueResult(
                    success=False,
                    output=current_text,
                    session_id=result_session_id,
                    error="사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요.",
                )
            logger.exception(f"SDK 메시지 파싱 오류: {e}")
            return RescueResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error="Claude 응답 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )
        except Exception as e:
            logger.exception(f"Claude Code SDK 실행 오류: {e}")
            return RescueResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=str(e),
            )
        finally:
            await self._remove_client(client_key)
            with self._clients_lock:
                self._execution_loops.pop(client_key, None)
            if stderr_file is not None:
                try:
                    stderr_file.close()
                except Exception:
                    pass


# 모듈 레벨 싱글턴
_runner = RescueRunner()


def get_runner() -> RescueRunner:
    """모듈 레벨 RescueRunner 인스턴스를 반환"""
    return _runner
