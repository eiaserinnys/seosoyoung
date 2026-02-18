"""Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 ClaudeAgentRunner와 동일한 공유 이벤트 루프 패턴을 사용합니다.
ClaudeSDKClient 기반으로 세션 재개를 지원합니다.
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
    - 매 실행마다 ClaudeSDKClient connect → query → receive → disconnect
    """

    # 클래스 레벨 공유 이벤트 루프 (메인 봇과 동일한 패턴)
    _shared_loop: Optional[asyncio.AbstractEventLoop] = None
    _loop_thread: Optional[threading.Thread] = None
    _loop_lock = threading.Lock()

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
    ) -> RescueResult:
        """동기 컨텍스트에서 Claude Code SDK를 호출합니다.

        공유 이벤트 루프를 통해 실행하여 세션 재개가 정상 작동합니다.
        """
        return self.run_sync(self._run_claude(prompt, session_id=session_id))

    async def _run_claude(
        self,
        prompt: str,
        session_id: Optional[str] = None,
    ) -> RescueResult:
        """Claude Code SDK를 호출하고 결과를 반환합니다.

        ClaudeSDKClient 기반으로 세션 재개를 지원합니다:
        - session_id가 None이면 새 세션을 시작합니다.
        - session_id가 있으면 해당 세션을 이어서 실행합니다.
        """
        working_dir = RescueConfig.get_working_dir()

        # CLI stderr를 파일에 캡처 (디버깅용)
        _runtime_dir = Path(__file__).resolve().parents[3]  # rescue/runner.py -> seosoyoung_runtime
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

        logger.info(f"Claude Code SDK 실행 (cwd={working_dir}, resume={session_id})")

        result_session_id = None
        current_text = ""
        result_text = ""
        idle_timeout = RescueConfig.CLAUDE_TIMEOUT

        client: Optional[ClaudeSDKClient] = None
        try:
            client = ClaudeSDKClient(options=options)
            await client.connect()
            await client.query(prompt)

            aiter = client.receive_response().__aiter__()
            rate_limit_count = 0
            while True:
                try:
                    message = await asyncio.wait_for(aiter.__anext__(), timeout=idle_timeout)
                    rate_limit_count = 0  # 정상 메시지 수신 시 카운터 리셋
                except StopAsyncIteration:
                    break
                except MessageParseError as e:
                    # rate_limit_event: SDK가 아직 지원하지 않는 메시지 타입
                    if e.data and e.data.get("type") == "rate_limit_event":
                        rate_limit_count += 1
                        wait_seconds = min(2 ** rate_limit_count, 30)
                        logger.warning(f"rate_limit_event 수신 ({rate_limit_count}회), {wait_seconds}초 대기")
                        await asyncio.sleep(wait_seconds)
                        continue
                    raise  # 다른 파싱 에러는 그대로 전파

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
        except ProcessError as e:
            logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}")
            return RescueResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=f"Claude Code 프로세스 오류 (exit code: {e.exit_code})",
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
            if client is not None:
                # CLI가 세션 데이터를 디스크에 저장할 시간을 허용
                # ResultMessage 수신 후 즉시 disconnect하면 terminate()로 인해
                # 세션 파일이 불완전하게 저장되어 resume가 실패합니다.
                try:
                    transport = getattr(client, "_transport", None)
                    if transport is not None:
                        process = getattr(transport, "_process", None)
                        if process is not None and process.returncode is None:
                            # CLI 프로세스가 자연 종료되기를 최대 5초 대기
                            try:
                                await asyncio.wait_for(process.wait(), timeout=5.0)
                                logger.info(f"CLI 프로세스 자연 종료 (returncode={process.returncode})")
                            except asyncio.TimeoutError:
                                logger.warning("CLI 프로세스 5초 내 자연 종료 실패, terminate 진행")
                except Exception as e:
                    logger.warning(f"CLI 프로세스 대기 오류 (무시): {e}")
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"ClaudeSDKClient disconnect 오류 (무시): {e}")
            # stderr 파일 닫기
            if _stderr_file is not sys.stderr:
                try:
                    _stderr_file.close()
                except Exception:
                    pass


# 모듈 레벨 싱글턴 (main.py에서 사용)
_runner = RescueRunner()


def run_claude_sync(
    prompt: str,
    session_id: Optional[str] = None,
) -> RescueResult:
    """모듈 레벨 래퍼 — main.py 호환용"""
    return _runner.run_claude_sync(prompt, session_id=session_id)
