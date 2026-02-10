"""Claude Code SDK 기반 실행기"""

import asyncio
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

from claude_code_sdk import query, ClaudeCodeOptions, HookMatcher, HookContext
from claude_code_sdk._errors import ProcessError
from claude_code_sdk.types import (
    AssistantMessage,
    HookJSONOutput,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

logger = logging.getLogger(__name__)


def _classify_process_error(e: ProcessError) -> str:
    """ProcessError를 사용자 친화적 메시지로 변환.

    Claude Code CLI는 다양한 이유로 exit code 1을 반환하지만,
    SDK가 stderr를 캡처하지 않아 원인 구분이 어렵습니다.
    exit_code와 stderr 패턴을 기반으로 최대한 분류합니다.
    """
    error_str = str(e).lower()
    stderr = (e.stderr or "").lower()
    combined = f"{error_str} {stderr}"

    # 사용량 제한 관련 패턴
    if any(kw in combined for kw in ["usage limit", "rate limit", "quota", "too many requests", "429"]):
        return "사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요."

    # 인증 관련 패턴
    if any(kw in combined for kw in ["unauthorized", "401", "auth", "token", "credentials", "forbidden", "403"]):
        return "인증에 실패했습니다. 관리자에게 문의해주세요."

    # 네트워크 관련 패턴
    if any(kw in combined for kw in ["network", "connection", "timeout", "econnrefused", "dns"]):
        return "네트워크 연결에 문제가 있습니다. 잠시 후 다시 시도해주세요."

    # exit code 1인데 구체적인 원인을 알 수 없는 경우
    if e.exit_code == 1:
        return (
            "Claude Code가 비정상 종료했습니다. "
            "사용량 제한이나 일시적 오류일 수 있으니 잠시 후 다시 시도해주세요."
        )

    # 기타
    return f"Claude Code 실행 중 오류가 발생했습니다 (exit code: {e.exit_code})"


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
    image_gen_prompts: list[str] = field(default_factory=list)
    update_requested: bool = False
    restart_requested: bool = False
    list_run: Optional[str] = None  # <!-- LIST_RUN: 리스트명 --> 마커로 추출된 리스트 이름
    collected_messages: list[dict] = field(default_factory=list)  # OM용 대화 수집


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
        compact_events: Optional[list] = None,
        user_id: Optional[str] = None,
    ) -> ClaudeCodeOptions:
        """ClaudeCodeOptions 생성

        참고: env 파라미터를 명시적으로 전달하지 않으면
        Claude Code CLI가 현재 프로세스의 환경변수를 상속받습니다.
        이 방식이 API 키 등을 안전하게 전달하는 가장 간단한 방법입니다.
        """
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
                return HookJSONOutput()  # 빈 응답 = 컴팩션 진행 허용

            hooks = {
                "PreCompact": [
                    HookMatcher(matcher=None, hooks=[on_pre_compact])
                ]
            }

        options = ClaudeCodeOptions(
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="bypassPermissions",  # dangerously-skip-permissions 대응
            cwd=self.working_dir,
            hooks=hooks,
            # env는 명시적으로 전달하지 않음 (CLI가 상위 프로세스 환경 상속)
        )

        # MCP 서버 설정 (경로 지정된 경우)
        if self.mcp_config_path and self.mcp_config_path.exists():
            options.mcp_servers = self.mcp_config_path

        # 세션 재개
        if session_id:
            options.resume = session_id

        # Observational Memory: 관찰 로그 주입
        if user_id:
            try:
                from seosoyoung.config import Config
                if Config.OM_ENABLED:
                    from seosoyoung.memory.context_builder import ContextBuilder
                    from seosoyoung.memory.store import MemoryStore

                    store = MemoryStore(Config.get_memory_path())
                    builder = ContextBuilder(store)
                    memory_prompt = builder.build_memory_prompt(
                        user_id, Config.OM_MAX_OBSERVATION_TOKENS
                    )
                    if memory_prompt:
                        options.append_system_prompt = memory_prompt
                        logger.info(f"OM 관찰 로그 주입 완료 (user={user_id})")
            except Exception as e:
                logger.warning(f"OM 관찰 로그 주입 실패 (무시): {e}")

        return options

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        user_id: Optional[str] = None,
    ) -> ClaudeResult:
        """Claude Code 실행

        Args:
            prompt: 실행할 프롬프트
            session_id: 이어갈 세션 ID (선택)
            on_progress: 진행 상황 콜백 (선택)
            on_compact: 컴팩션 발생 콜백 (선택) - (trigger, message) 전달
            user_id: 사용자 ID (OM 관찰 로그 주입용, 선택)
        """
        async with self._lock:
            result = await self._execute(prompt, session_id, on_progress, on_compact, user_id)

        # OM: 세션 종료 후 비동기로 관찰 파이프라인 트리거
        if result.success and user_id and result.collected_messages:
            self._trigger_observation(user_id, prompt, result.collected_messages)

        return result

    def _trigger_observation(
        self,
        user_id: str,
        prompt: str,
        collected_messages: list[dict],
    ) -> None:
        """관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)

        executor.py가 asyncio.run()으로 호출하므로, 코루틴 완료 후 이벤트 루프가 닫힙니다.
        따라서 create_task 대신 별도 스레드에서 새 이벤트 루프를 생성하여 실행합니다.
        """
        try:
            from seosoyoung.config import Config
            if not Config.OM_ENABLED:
                return

            # 사용자 메시지를 collected_messages 앞에 추가
            messages = [{"role": "user", "content": prompt}] + collected_messages

            def _run_in_thread():
                try:
                    from seosoyoung.memory.observation_pipeline import (
                        observe_conversation,
                    )
                    from seosoyoung.memory.observer import Observer
                    from seosoyoung.memory.reflector import Reflector
                    from seosoyoung.memory.store import MemoryStore

                    debug_channel = Config.OM_DEBUG_CHANNEL

                    store = MemoryStore(Config.get_memory_path())
                    observer = Observer(
                        api_key=Config.OPENAI_API_KEY,
                        model=Config.OM_MODEL,
                    )
                    reflector = Reflector(
                        api_key=Config.OPENAI_API_KEY,
                        model=Config.OM_MODEL,
                    )
                    asyncio.run(observe_conversation(
                        store=store,
                        observer=observer,
                        user_id=user_id,
                        messages=messages,
                        observation_threshold=Config.OM_OBSERVATION_THRESHOLD,
                        reflector=reflector,
                        reflection_threshold=Config.OM_REFLECTION_THRESHOLD,
                        debug_channel=debug_channel,
                    ))
                except Exception as e:
                    logger.error(f"OM 관찰 파이프라인 비동기 실행 오류 (무시): {e}")
                    # 별도 스레드에서 logger가 동작하지 않을 수 있으므로 디버그 채널로도 발송
                    try:
                        from seosoyoung.memory.observation_pipeline import _send_debug_log
                        if Config.OM_DEBUG_CHANNEL:
                            _send_debug_log(
                                Config.OM_DEBUG_CHANNEL,
                                f"❌ *OM 스레드 오류*\n• user: `{user_id}`\n• error: `{e}`",
                            )
                    except Exception:
                        pass

            thread = threading.Thread(target=_run_in_thread, daemon=True)
            thread.start()
            logger.info(f"OM 관찰 파이프라인 트리거됨 (user={user_id})")
        except Exception as e:
            logger.warning(f"OM 관찰 트리거 실패 (무시): {e}")

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        user_id: Optional[str] = None,
    ) -> ClaudeResult:
        """실제 실행 로직"""
        compact_events: list[dict] = []
        compact_notified_count = 0
        options = self._build_options(session_id, compact_events=compact_events, user_id=user_id)
        logger.info(f"Claude Code SDK 실행 시작 (cwd={self.working_dir})")

        result_session_id = None
        current_text = ""
        result_text = ""
        collected_messages: list[dict] = []  # OM용 대화 수집
        last_progress_time = asyncio.get_event_loop().time()
        progress_interval = 2.0

        try:
            async for message in query(prompt=prompt, options=options):
                # SystemMessage에서 세션 ID 추출
                if isinstance(message, SystemMessage):
                    if hasattr(message, 'session_id'):
                        result_session_id = message.session_id
                        logger.info(f"세션 ID: {result_session_id}")

                # AssistantMessage에서 텍스트/도구 사용 추출
                elif isinstance(message, AssistantMessage):
                    if hasattr(message, 'content'):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                current_text = block.text

                                # OM용 대화 수집
                                collected_messages.append({
                                    "role": "assistant",
                                    "content": block.text,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })

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

                            elif isinstance(block, ToolUseBlock):
                                # OM용: 도구 호출 수집
                                collected_messages.append({
                                    "role": "assistant",
                                    "content": f"[tool_use: {block.name}]",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })

                            elif isinstance(block, ToolResultBlock):
                                # OM용: 도구 결과 수집 (내용이 긴 경우 truncate)
                                content = ""
                                if isinstance(block.content, str):
                                    content = block.content[:2000]
                                elif block.content:
                                    content = json.dumps(block.content, ensure_ascii=False)[:2000]
                                collected_messages.append({
                                    "role": "tool",
                                    "content": content,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })

                # ResultMessage에서 최종 결과 추출
                elif isinstance(message, ResultMessage):
                    if hasattr(message, 'result'):
                        result_text = message.result
                        # OM용 대화 수집
                        collected_messages.append({
                            "role": "assistant",
                            "content": message.result,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    # ResultMessage에서도 세션 ID 추출 시도
                    if hasattr(message, 'session_id') and message.session_id:
                        result_session_id = message.session_id

                # 컴팩션 이벤트 확인 (PreCompact 훅에서 추가된 이벤트)
                if on_compact and len(compact_events) > compact_notified_count:
                    for event in compact_events[compact_notified_count:]:
                        try:
                            await on_compact(event["trigger"], event["message"])
                        except Exception as e:
                            logger.warning(f"컴팩션 콜백 오류: {e}")
                    compact_notified_count = len(compact_events)

            # 출력 처리
            output = result_text or current_text

            # 마커 추출
            files = re.findall(r"<!-- FILE: (.+?) -->", output)
            attachments = re.findall(r"<!-- ATTACH: (.+?) -->", output)
            image_gen_prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
            update_requested = "<!-- UPDATE -->" in output
            restart_requested = "<!-- RESTART -->" in output

            # LIST_RUN 마커 추출
            list_run_match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
            list_run = list_run_match.group(1).strip() if list_run_match else None

            if attachments:
                logger.info(f"첨부 파일 요청: {attachments}")
            if image_gen_prompts:
                logger.info(f"이미지 생성 요청: {image_gen_prompts}")
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
                image_gen_prompts=image_gen_prompts,
                update_requested=update_requested,
                restart_requested=restart_requested,
                list_run=list_run,
                collected_messages=collected_messages,
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
        except ProcessError as e:
            friendly_msg = _classify_process_error(e)
            logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}, stderr={e.stderr}, friendly={friendly_msg}")
            return ClaudeResult(
                success=False,
                output=current_text,
                session_id=result_session_id,
                error=friendly_msg,
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
