"""Claude Code SDK 기반 실행기"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, Awaitable

from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
)

logger = logging.getLogger(__name__)


# Claude Code 기본 허용 도구
DEFAULT_ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "TodoWrite",
]

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
    files: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    update_requested: bool = False
    restart_requested: bool = False
    list_run: Optional[str] = None  # <!-- LIST_RUN: 리스트명 --> 마커로 추출된 리스트 이름


class ClaudeAgentRunner:
    """Claude Code SDK 기반 실행기"""

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        timeout: int = 300,
        allowed_tools: Optional[list[str]] = None,
        disallowed_tools: Optional[list[str]] = None,
        mcp_config_path: Optional[Path] = None,
    ):
        self.working_dir = working_dir or Path.cwd()
        self.timeout = timeout
        self.allowed_tools = allowed_tools or DEFAULT_ALLOWED_TOOLS
        self.disallowed_tools = disallowed_tools or DEFAULT_DISALLOWED_TOOLS
        self.mcp_config_path = mcp_config_path
        self._lock = asyncio.Lock()

    def _build_options(
        self,
        session_id: Optional[str] = None,
    ) -> ClaudeCodeOptions:
        """ClaudeCodeOptions 생성

        참고: env 파라미터를 명시적으로 전달하지 않으면
        Claude Code CLI가 현재 프로세스의 환경변수를 상속받습니다.
        이 방식이 API 키 등을 안전하게 전달하는 가장 간단한 방법입니다.
        """
        options = ClaudeCodeOptions(
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="bypassPermissions",  # dangerously-skip-permissions 대응
            cwd=self.working_dir,
            # env는 명시적으로 전달하지 않음 (CLI가 상위 프로세스 환경 상속)
        )

        # MCP 서버 설정 (경로 지정된 경우)
        if self.mcp_config_path and self.mcp_config_path.exists():
            options.mcp_servers = self.mcp_config_path

        # 세션 재개
        if session_id:
            options.resume = session_id

        return options

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ClaudeResult:
        """Claude Code 실행

        Args:
            prompt: 실행할 프롬프트
            session_id: 이어갈 세션 ID (선택)
            on_progress: 진행 상황 콜백 (선택)
        """
        async with self._lock:
            return await self._execute(prompt, session_id, on_progress)

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> ClaudeResult:
        """실제 실행 로직"""
        options = self._build_options(session_id)
        logger.info(f"Claude Code SDK 실행 시작 (cwd={self.working_dir})")

        result_session_id = None
        current_text = ""
        result_text = ""
        last_progress_time = asyncio.get_event_loop().time()
        progress_interval = 2.0

        try:
            async for message in query(prompt=prompt, options=options):
                # SystemMessage에서 세션 ID 추출
                if isinstance(message, SystemMessage):
                    if hasattr(message, 'session_id'):
                        result_session_id = message.session_id
                        logger.info(f"세션 ID: {result_session_id}")

                # AssistantMessage에서 텍스트 추출 (진행 상황용)
                elif isinstance(message, AssistantMessage):
                    if hasattr(message, 'content'):
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

                # ResultMessage에서 최종 결과 추출
                elif isinstance(message, ResultMessage):
                    if hasattr(message, 'result'):
                        result_text = message.result
                    # ResultMessage에서도 세션 ID 추출 시도
                    if hasattr(message, 'session_id') and message.session_id:
                        result_session_id = message.session_id

            # 출력 처리
            output = result_text or current_text

            # 마커 추출
            files = re.findall(r"<!-- FILE: (.+?) -->", output)
            attachments = re.findall(r"<!-- ATTACH: (.+?) -->", output)
            update_requested = "<!-- UPDATE -->" in output
            restart_requested = "<!-- RESTART -->" in output

            # LIST_RUN 마커 추출
            list_run_match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
            list_run = list_run_match.group(1).strip() if list_run_match else None

            if attachments:
                logger.info(f"첨부 파일 요청: {attachments}")
            if update_requested:
                logger.info("업데이트 요청 마커 감지: <!-- UPDATE -->")
            if restart_requested:
                logger.info("재시작 요청 마커 감지: <!-- RESTART -->")
            if list_run:
                logger.info(f"리스트 정주행 요청 마커 감지: {list_run}")

            return ClaudeResult(
                success=True,
                output=output,
                session_id=result_session_id,
                files=files,
                attachments=attachments,
                update_requested=update_requested,
                restart_requested=restart_requested,
                list_run=list_run,
            )

        except asyncio.TimeoutError:
            logger.error(f"Claude Code SDK 타임아웃 ({self.timeout}초)")
            return ClaudeResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=f"타임아웃: {self.timeout}초 초과"
            )
        except FileNotFoundError as e:
            logger.error(f"Claude Code CLI를 찾을 수 없습니다: {e}")
            return ClaudeResult(
                success=False,
                output="",
                error="Claude Code CLI를 찾을 수 없습니다. claude 명령어가 PATH에 있는지 확인하세요."
            )
        except Exception as e:
            logger.exception(f"Claude Code SDK 실행 오류: {e}")
            return ClaudeResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=str(e)
            )

    async def compact_session(self, session_id: str) -> ClaudeResult:
        """세션 컴팩트 처리

        세션의 대화 내역을 압축하여 토큰 사용량을 줄입니다.

        Args:
            session_id: 컴팩트할 세션 ID

        Returns:
            ClaudeResult (compact 결과)
        """
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
    runner = ClaudeAgentRunner()
    result = await runner.run("안녕? 간단히 인사해줘. 3줄 이내로.")
    print(f"Success: {result.success}")
    print(f"Session ID: {result.session_id}")
    print(f"Output:\n{result.output}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
