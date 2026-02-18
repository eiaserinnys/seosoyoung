"""Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 ClaudeAgentRunner에서 핵심 로직을 복제한 경량 버전:
- _classify_process_error: ProcessError를 사용자 친화적 메시지로 변환
- _build_options: ClaudeCodeOptions 생성 (OM, hooks, compact 제외)
- _get_or_create_client / _remove_client: 클라이언트 생명주기 관리
- _execute: 실제 실행 로직 (메인 봇과 동일한 구조)
- run / run_sync: async/sync 인터페이스
"""

import asyncio
import logging
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient
from claude_code_sdk._errors import MessageParseError, ProcessError
from claude_code_sdk.types import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
)

from seosoyoung.rescue.config import RescueConfig

logger = logging.getLogger(__name__)

# 최소한의 도구만 허용
ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "TodoWrite",
]

DISALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Task",
]


def _classify_process_error(e: ProcessError) -> str:
    """ProcessError를 사용자 친화적 메시지로 변환.

    메인 봇의 _classify_process_error와 동일한 로직입니다.
    """
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


@dataclass
class RescueResult:
    """실행 결과"""

    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None


class RescueRunner:
    """Claude Code SDK 실행기 (공유 이벤트 루프 기반)

    메인 봇의 ClaudeAgentRunner와 동일한 패턴:
    - 클래스 레벨 공유 이벤트 루프 (데몬 스레드)
    - run_coroutine_threadsafe로 동기→비동기 브릿지
    - _get_or_create_client / _remove_client로 클라이언트 생명주기 관리
    """

    # 클래스 레벨 공유 이벤트 루프 (메인 봇과 동일한 패턴)
    _shared_loop: Optional[asyncio.AbstractEventLoop] = None
    _loop_thread: Optional[threading.Thread] = None
    _loop_lock = threading.Lock()

    def __init__(self):
        self._lock = asyncio.Lock()
        self._active_clients: dict[str, ClaudeSDKClient] = {}

    @classmethod
    def _ensure_loop(cls) -> None:
        """공유 이벤트 루프가 없거나 닫혀있으면 데몬 스레드에서 새로 생성"""
        with cls._loop_lock:
            if cls._shared_loop is not None and cls._shared_loop.is_running():
                return

            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=loop.run_forever,
                daemon=True,
                name="rescue-shared-loop",
            )
            thread.start()

            cls._shared_loop = loop
            cls._loop_thread = thread
            logger.info("공유 이벤트 루프 생성됨")

    @classmethod
    def _reset_shared_loop(cls) -> None:
        """공유 루프를 리셋 (테스트용)"""
        with cls._loop_lock:
            if cls._shared_loop is not None and cls._shared_loop.is_running():
                cls._shared_loop.call_soon_threadsafe(cls._shared_loop.stop)
                if cls._loop_thread is not None:
                    cls._loop_thread.join(timeout=2)
            cls._shared_loop = None
            cls._loop_thread = None

    def run_sync(self, coro):
        """동기 컨텍스트에서 코루틴을 실행하는 브릿지

        Slack 이벤트 핸들러(동기)에서 async 함수를 호출할 때 사용.
        공유 이벤트 루프에 코루틴을 제출하고 결과를 기다립니다.
        """
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._shared_loop)
        return future.result()

    def run_claude_sync(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> RescueResult:
        """동기 컨텍스트에서 Claude Code SDK를 호출합니다.

        공유 이벤트 루프를 통해 실행하여 세션 재개가 정상 작동합니다.
        """
        return self.run_sync(self.run(prompt, session_id=session_id, thread_ts=thread_ts))

    def _build_options(
        self,
        session_id: Optional[str] = None,
    ) -> ClaudeCodeOptions:
        """ClaudeCodeOptions를 생성합니다.

        메인 봇의 _build_options에서 OM, hooks, compact, 슬랙 컨텍스트 등을
        제거한 경량 버전입니다.
        """
        working_dir = RescueConfig.get_working_dir()

        # CLI stderr를 파일에 캡처 (디버깅용)
        _runtime_dir = Path(__file__).resolve().parents[3]
        _stderr_log_path = _runtime_dir / "logs" / "rescue_cli_stderr.log"
        try:
            _stderr_file = open(_stderr_log_path, "a", encoding="utf-8")
            _stderr_file.write(f"\n--- rescue CLI stderr: {datetime.now(timezone.utc).isoformat()} resume={session_id} ---\n")
            _stderr_file.flush()
        except Exception as _e:
            logger.warning(f"stderr 캡처 파일 열기 실패: {_e}")
            _stderr_file = sys.stderr

        options = ClaudeCodeOptions(
            allowed_tools=ALLOWED_TOOLS,
            disallowed_tools=DISALLOWED_TOOLS,
            permission_mode="bypassPermissions",
            cwd=working_dir,
            extra_args={"debug-to-stderr": None},
            debug_stderr=_stderr_file,
        )

        if session_id:
            options.resume = session_id

        return options

    async def _get_or_create_client(
        self,
        client_key: str,
        options: Optional[ClaudeCodeOptions] = None,
    ) -> ClaudeSDKClient:
        """클라이언트를 가져오거나 새로 생성 (메인 봇 동일 패턴)

        Args:
            client_key: 클라이언트 키 (thread_ts)
            options: ClaudeCodeOptions (새 클라이언트 생성 시 사용)
        """
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
        self._active_clients[client_key] = client
        return client

    async def _remove_client(self, client_key: str) -> None:
        """클라이언트를 정리 (메인 봇 동일 패턴)

        disconnect 후 딕셔너리에서 제거합니다.
        """
        client = self._active_clients.pop(client_key, None)
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f"ClaudeSDKClient disconnect 오류 (무시): key={client_key}, {e}")
        logger.info(f"ClaudeSDKClient 제거: key={client_key}")

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> RescueResult:
        """Claude Code 실행 (async, lock 포함)

        메인 봇의 run()에서 OM 관련 로직을 제거한 버전입니다.
        """
        async with self._lock:
            return await self._execute(prompt, session_id=session_id, thread_ts=thread_ts)

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> RescueResult:
        """실제 실행 로직 (메인 봇 _execute와 동일한 구조)"""
        options = self._build_options(session_id=session_id)

        logger.info(f"Claude Code SDK 실행 (cwd={options.cwd}, resume={session_id})")

        # 클라이언트 키: thread_ts가 없으면 임시 키
        client_key = thread_ts or f"_ephemeral_{id(asyncio.current_task())}"

        result_session_id = None
        current_text = ""
        result_text = ""
        idle_timeout = RescueConfig.CLAUDE_TIMEOUT

        try:
            client = await self._get_or_create_client(client_key, options=options)
            await client.query(prompt)

            aiter = client.receive_response().__aiter__()
            rate_limit_count = 0
            rate_limit_delays = [1, 3, 5]
            while True:
                try:
                    message = await asyncio.wait_for(aiter.__anext__(), timeout=idle_timeout)
                    rate_limit_count = 0
                except StopAsyncIteration:
                    break
                except MessageParseError as e:
                    if e.data and e.data.get("type") == "rate_limit_event":
                        rate_limit_count += 1
                        if rate_limit_count > len(rate_limit_delays):
                            logger.error(f"rate_limit_event {rate_limit_count}회 초과, 재시도 중단")
                            raise
                        wait_seconds = rate_limit_delays[rate_limit_count - 1]
                        logger.warning(f"rate_limit_event 수신 ({rate_limit_count}/{len(rate_limit_delays)}회), {wait_seconds}초 후 재시도")
                        await asyncio.sleep(wait_seconds)
                        continue
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

                elif isinstance(message, ResultMessage):
                    if hasattr(message, "result"):
                        result_text = message.result
                    if hasattr(message, "session_id") and message.session_id:
                        result_session_id = message.session_id

            output = result_text or current_text

            return RescueResult(
                success=True,
                output=output,
                session_id=result_session_id,
            )

        except asyncio.TimeoutError:
            logger.error(f"Claude Code SDK 타임아웃 ({idle_timeout}s)")
            return RescueResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=f"타임아웃: {idle_timeout}초 초과",
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


# 모듈 레벨 싱글턴 (main.py에서 사용)
_runner = RescueRunner()


def run_claude_sync(
    prompt: str,
    session_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> RescueResult:
    """모듈 레벨 래퍼 — main.py 호환용"""
    return _runner.run_claude_sync(prompt, session_id=session_id, thread_ts=thread_ts)
