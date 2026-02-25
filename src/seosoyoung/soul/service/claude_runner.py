"""
ClaudeCodeRunner - Claude Code CLI 실행

Claude Code SDK를 사용하여 Claude Code를 실행하고 결과를 스트리밍합니다.
"""

import os
import asyncio
import logging
from typing import Optional, AsyncIterator, Callable, Awaitable, List
from dataclasses import dataclass

try:
    from claude_agent_sdk import (
        ClaudeSDKClient,
        ClaudeAgentOptions,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ResultMessage,
        ProcessError,
        CLINotFoundError,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    # 테스트용 더미 클래스
    class ClaudeSDKClient:
        pass
    class ClaudeAgentOptions:
        pass

from seosoyoung.soul.models import (
    ProgressEvent,
    MemoryEvent,
    InterventionSentEvent,
    CompleteEvent,
    ErrorEvent,
    ContextUsageEvent,
    CompactEvent,
)
from seosoyoung.soul.service.resource_manager import resource_manager
from seosoyoung.soul.service.output_sanitizer import sanitize_output
from seosoyoung.soul.service.attachment_extractor import AttachmentExtractor
from seosoyoung.soul.service.session_validator import (
    validate_session,
    SESSION_NOT_FOUND_CODE,
)


logger = logging.getLogger(__name__)


# === 설정 ===
ALLOWED_TOOLS = ["Read", "Glob", "Grep", "Task", "WebFetch", "WebSearch", "Edit", "Write", "Bash"]
DISALLOWED_TOOLS = ["NotebookEdit", "TodoWrite"]
EXECUTION_TIMEOUT = 600  # 10분
STREAM_UPDATE_INTERVAL = 2.0  # 초
MEMORY_REPORT_INTERVAL = 10.0  # 초

# 컨텍스트 관련 상수
DEFAULT_MAX_CONTEXT_TOKENS = 200000  # 기본 컨텍스트 윈도우 크기


@dataclass
class InterventionMessage:
    """개입 메시지 데이터"""
    text: str
    user: str
    attachment_paths: List[str]


class ClaudeCodeRunner:
    """
    Claude Code CLI 실행기

    역할:
    1. Claude Code SDK를 사용하여 Claude Code 실행
    2. 진행 상황을 SSE 이벤트로 변환
    3. 출력 필터링 (비밀 마스킹)
    4. 첨부 파일 추출
    """

    def __init__(self, workspace_dir: Optional[str] = None):
        """
        Args:
            workspace_dir: Claude Code 작업 디렉토리
        """
        self._workspace_dir = workspace_dir or os.getenv(
            "WORKSPACE_DIR", "D:/soyoung_root/slackbot_workspace"
        )
        # 첨부 파일 추출기 초기화
        self._attachment_extractor = AttachmentExtractor(self._workspace_dir)

    def _create_options(
        self,
        resume_session_id: Optional[str] = None,
    ) -> "ClaudeAgentOptions":
        """
        ClaudeAgentOptions 생성

        Args:
            resume_session_id: 이전 세션 ID
        """
        if not SDK_AVAILABLE:
            raise RuntimeError("Claude Code SDK not available")

        options = ClaudeAgentOptions(
            allowed_tools=ALLOWED_TOOLS,
            disallowed_tools=DISALLOWED_TOOLS,
            permission_mode='bypassPermissions',
            cwd=self._workspace_dir,
        )

        if resume_session_id:
            options.resume = resume_session_id

        return options

    def _build_intervention_prompt(self, msg: InterventionMessage) -> str:
        """개입 메시지를 Claude 프롬프트로 변환"""
        if msg.attachment_paths:
            attachment_info = "\n".join([f"- {p}" for p in msg.attachment_paths])
            return f"""[사용자 개입 메시지 from {msg.user}]
{msg.text}

첨부 파일 (Read 도구로 확인):
{attachment_info}"""
        else:
            return f"""[사용자 개입 메시지 from {msg.user}]
{msg.text}"""

    def _extract_context_usage(self, usage: Optional[dict]) -> Optional[ContextUsageEvent]:
        """
        ResultMessage.usage에서 컨텍스트 사용량 추출

        Args:
            usage: ResultMessage.usage 딕셔너리

        Returns:
            ContextUsageEvent 또는 None
        """
        if not usage:
            return None

        # 입력/출력 토큰 수 추출
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # 총 사용량 = input_tokens + output_tokens
        total_used = input_tokens + output_tokens

        if total_used <= 0:
            return None

        max_tokens = DEFAULT_MAX_CONTEXT_TOKENS

        # 사용 퍼센트 계산
        percent = (total_used / max_tokens) * 100 if max_tokens > 0 else 0

        logger.info(
            f"Context usage: input={input_tokens:,}, output={output_tokens:,}, "
            f"total={total_used:,}/{max_tokens:,} ({percent:.1f}%)"
        )

        return ContextUsageEvent(
            used_tokens=total_used,
            max_tokens=max_tokens,
            percent=round(percent, 1)
        )

    async def execute(
        self,
        prompt: str,
        resume_session_id: Optional[str] = None,
        get_intervention: Optional[Callable[[], Awaitable[Optional[dict]]]] = None,
        on_intervention_sent: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> AsyncIterator:
        """
        Claude Code 실행 (SSE 이벤트 스트림)

        Args:
            prompt: 사용자 프롬프트
            resume_session_id: 이전 세션 ID
            get_intervention: 개입 메시지 가져오기 함수
            on_intervention_sent: 개입 메시지 전송 후 콜백

        Yields:
            ProgressEvent | MemoryEvent | InterventionSentEvent | ContextUsageEvent | CompleteEvent | ErrorEvent
        """
        if not SDK_AVAILABLE:
            yield ErrorEvent(message="Claude Code SDK not available")
            return

        # 세션 ID 검증 (resume 시)
        if resume_session_id:
            validation_error = validate_session(resume_session_id)
            if validation_error:
                yield ErrorEvent(
                    message=validation_error,
                    error_code=SESSION_NOT_FOUND_CODE
                )
                return

        accumulated_text = ""
        current_text = ""
        session_id = None
        context_usage_event = None
        last_update_time = asyncio.get_event_loop().time()
        memory_reported_since_progress = False

        options = self._create_options(resume_session_id)

        try:
            async with ClaudeSDKClient(options=options) as client:
                # 쿼리 시작
                await client.query(prompt)

                # 응답 수신 및 스트리밍
                async for message in client.receive_messages():
                    # AssistantMessage에서 텍스트 추출
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                current_text = block.text
                            elif isinstance(block, ToolUseBlock):
                                logger.debug(f"Tool use: {block.name}")

                    # ResultMessage에서 세션 ID와 최종 결과 추출
                    elif isinstance(message, ResultMessage):
                        session_id = message.session_id
                        if message.result:
                            accumulated_text = message.result

                        # 컨텍스트 사용량 추출
                        context_usage_event = self._extract_context_usage(message.usage)
                        break

                    # 진행 상황 업데이트
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_update_time >= STREAM_UPDATE_INTERVAL:
                        display_text = current_text or accumulated_text
                        if display_text:
                            sanitized = sanitize_output(display_text)
                            yield ProgressEvent(text=sanitized)
                            last_update_time = current_time
                            memory_reported_since_progress = False

                    # 메모리 리포트
                    if not memory_reported_since_progress:
                        if current_time - last_update_time >= MEMORY_REPORT_INTERVAL:
                            used_gb, total_gb, percent = resource_manager.get_system_memory()
                            if total_gb > 0:
                                yield MemoryEvent(
                                    used_gb=used_gb,
                                    total_gb=total_gb,
                                    percent=percent
                                )
                            memory_reported_since_progress = True

                    # 개입 메시지 확인
                    if get_intervention:
                        intervention = await get_intervention()
                        if intervention:
                            msg = InterventionMessage(
                                text=intervention.get("text", ""),
                                user=intervention.get("user", ""),
                                attachment_paths=intervention.get("attachment_paths", [])
                            )
                            intervention_prompt = self._build_intervention_prompt(msg)
                            logger.info(f"[Intervention] Sending: {intervention_prompt[:100]}...")
                            await client.query(intervention_prompt)

                            if on_intervention_sent:
                                await on_intervention_sent(msg.user, msg.text)

                            yield InterventionSentEvent(
                                user=msg.user,
                                text=msg.text
                            )

            # 컨텍스트 사용량 이벤트 전송 (결과 전에)
            if context_usage_event:
                yield context_usage_event

            # 최종 결과
            final_text = accumulated_text or current_text
            if not final_text:
                final_text = "(결과 없음)"

            # 출력 필터링 및 첨부 파일 추출
            final_text = sanitize_output(final_text)
            final_text, attachments = self._attachment_extractor.extract_attachments(final_text)

            yield CompleteEvent(
                result=final_text,
                attachments=attachments,
                claude_session_id=session_id
            )

        except asyncio.TimeoutError:
            yield ErrorEvent(message=f"실행 시간 초과 ({EXECUTION_TIMEOUT}초)")

        except Exception as e:
            if SDK_AVAILABLE and isinstance(e, CLINotFoundError):
                yield ErrorEvent(message="Claude Code CLI가 설치되지 않았습니다")
            elif SDK_AVAILABLE and isinstance(e, ProcessError):
                yield ErrorEvent(message=f"실행 오류: {str(e)}")
            else:
                logger.exception(f"Claude Code execution error: {e}")
                yield ErrorEvent(message=f"실행 오류: {str(e)}")


# 싱글톤 인스턴스
claude_runner = ClaudeCodeRunner()
