"""Claude Code SDK 기반 실행기"""

import asyncio
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
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
    ToolResultBlock,
    ToolUseBlock,
)
from slack_sdk import WebClient

logger = logging.getLogger(__name__)

# 디버그 메시지용 슬랙 클라이언트 (lazy init)
_slack_client: Optional[WebClient] = None


def _get_slack_client() -> Optional[WebClient]:
    """슬랙 클라이언트 가져오기 (lazy init)"""
    global _slack_client
    if _slack_client is None:
        from seosoyoung.config import Config
        if Config.SLACK_BOT_TOKEN:
            _slack_client = WebClient(token=Config.SLACK_BOT_TOKEN)
    return _slack_client


def _send_debug_to_slack(channel: str, thread_ts: str, message: str) -> None:
    """슬랙에 디버그 메시지 전송 (별도 메시지로)"""
    try:
        client = _get_slack_client()
        if client and channel and thread_ts:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=message,
            )
    except Exception as e:
        logger.warning(f"디버그 메시지 슬랙 전송 실패: {e}")


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
    "mcp__seosoyoung-attach__slack_attach_file",
    "mcp__seosoyoung-attach__slack_get_context",
    "mcp__seosoyoung-attach__slack_post_message",
    "mcp__seosoyoung-attach__slack_download_thread_files",
    "mcp__seosoyoung-attach__slack_generate_image",
    "mcp__seosoyoung-attach__npc_list_characters",
    "mcp__seosoyoung-attach__npc_open_session",
    "mcp__seosoyoung-attach__npc_talk",
    "mcp__seosoyoung-attach__npc_set_situation",
    "mcp__seosoyoung-attach__npc_close_session",
    "mcp__seosoyoung-attach__npc_get_history",
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
    update_requested: bool = False
    restart_requested: bool = False
    list_run: Optional[str] = None  # <!-- LIST_RUN: 리스트명 --> 마커로 추출된 리스트 이름
    collected_messages: list[dict] = field(default_factory=list)  # OM용 대화 수집
    interrupted: bool = False  # interrupt로 중단된 경우 True
    usage: Optional[dict] = None  # ResultMessage.usage (input_tokens, output_tokens 등)
    anchor_ts: str = ""  # OM 디버그 채널 세션 스레드 앵커 ts


class ClaudeAgentRunner:
    """Claude Code SDK 기반 실행기"""

    # 클래스 레벨 공유 이벤트 루프 (모든 인스턴스가 공유)
    _shared_loop: Optional[asyncio.AbstractEventLoop] = None
    _loop_thread: Optional[threading.Thread] = None
    _loop_lock = threading.Lock()

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
                name="claude-shared-loop",
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

    async def _get_or_create_client(
        self,
        thread_ts: str,
        options: Optional[ClaudeCodeOptions] = None,
    ) -> ClaudeSDKClient:
        """스레드에 대한 ClaudeSDKClient를 가져오거나 새로 생성

        Args:
            thread_ts: 스레드 타임스탬프 (클라이언트 키)
            options: ClaudeCodeOptions (새 클라이언트 생성 시 사용)
        """
        if thread_ts in self._active_clients:
            logger.info(f"[DEBUG-CLIENT] 기존 클라이언트 재사용: thread={thread_ts}")
            return self._active_clients[thread_ts]

        import time as _time
        logger.info(f"[DEBUG-CLIENT] 새 ClaudeSDKClient 생성 시작: thread={thread_ts}")
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
            # connect 실패 시 서브프로세스 정리 — 좀비 방지
            try:
                await client.disconnect()
            except Exception:
                pass
            raise
        self._active_clients[thread_ts] = client
        logger.info(f"ClaudeSDKClient 생성: thread={thread_ts}")
        return client

    async def _remove_client(self, thread_ts: str) -> None:
        """스레드의 ClaudeSDKClient를 정리

        disconnect 후 딕셔너리에서 제거합니다.
        disconnect 실패 시에도 딕셔너리에서 제거합니다.
        """
        client = self._active_clients.pop(thread_ts, None)
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f"ClaudeSDKClient disconnect 오류 (무시): thread={thread_ts}, {e}")
        logger.info(f"ClaudeSDKClient 제거: thread={thread_ts}")

    async def interrupt(self, thread_ts: str) -> bool:
        """실행 중인 스레드에 인터럽트 전송

        Args:
            thread_ts: 스레드 타임스탬프

        Returns:
            True: 인터럽트 성공, False: 해당 스레드에 클라이언트 없음 또는 실패
        """
        client = self._active_clients.get(thread_ts)
        if client is None:
            return False
        try:
            await client.interrupt()
            logger.info(f"인터럽트 전송: thread={thread_ts}")
            return True
        except Exception as e:
            logger.warning(f"인터럽트 실패: thread={thread_ts}, {e}")
            return False

    def _build_options(
        self,
        session_id: Optional[str] = None,
        compact_events: Optional[list] = None,
        user_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        channel: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> tuple[ClaudeCodeOptions, Optional[str], str]:
        """ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts를 함께 반환합니다.

        Returns:
            (options, memory_prompt, anchor_ts)
            - memory_prompt는 첫 번째 query에 프리픽스로 주입합니다.
            - anchor_ts는 디버그 채널의 세션 스레드 앵커 메시지 ts입니다.
            append_system_prompt는 CLI 인자 크기 제한이 있어 장기 기억이 커지면 실패하므로,
            메모리는 첫 번째 사용자 메시지에 주입하는 방식을 사용합니다.

        참고: env 파라미터를 명시적으로 전달하지 않으면
        Claude Code CLI가 현재 프로세스의 환경변수를 상속받습니다.
        이 방식이 API 키 등을 안전하게 전달하는 가장 간단한 방법입니다.

        channel과 thread_ts가 모두 제공되면 env에 SLACK_CHANNEL, SLACK_THREAD_TS를
        명시적으로 설정합니다. MCP 서버(seosoyoung-attach)가 이 값을 사용하여
        파일을 올바른 스레드에 첨부합니다.
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

                # OM: 컴팩션 시 다음 요청에 관찰 로그 재주입하도록 플래그 설정
                if thread_ts:
                    try:
                        from seosoyoung.config import Config
                        if Config.OM_ENABLED:
                            from seosoyoung.memory.store import MemoryStore
                            store = MemoryStore(Config.get_memory_path())
                            record = store.get_record(thread_ts)
                            if record and record.observations.strip():
                                store.set_inject_flag(thread_ts)
                                logger.info(f"OM inject 플래그 설정 (PreCompact, thread={thread_ts})")
                    except Exception as e:
                        logger.warning(f"OM inject 플래그 설정 실패 (PreCompact, 무시): {e}")

                return HookJSONOutput()  # 빈 응답 = 컴팩션 진행 허용

            hooks = {
                "PreCompact": [
                    HookMatcher(matcher=None, hooks=[on_pre_compact])
                ]
            }

        # 슬랙 컨텍스트가 있으면 env에 주입 (MCP 서버용)
        # SDK는 env가 항상 dict이길 기대하므로 빈 dict를 기본값으로 사용
        env: dict[str, str] = {}
        if channel and thread_ts:
            env["SLACK_CHANNEL"] = channel
            env["SLACK_THREAD_TS"] = thread_ts

        # DEBUG: CLI stderr를 파일에 캡처
        import sys as _sys
        # logs 디렉토리: seosoyoung 패키지 기준으로 계산
        _runtime_dir = Path(__file__).resolve().parents[3]  # src/seosoyoung/claude/agent_runner.py -> seosoyoung_runtime
        _stderr_log_path = _runtime_dir / "logs" / "cli_stderr.log"
        logger.info(f"[DEBUG] CLI stderr 로그 경로: {_stderr_log_path}")
        try:
            _stderr_file = open(_stderr_log_path, "a", encoding="utf-8")
            _stderr_file.write(f"\n--- CLI stderr capture start: {datetime.now(timezone.utc).isoformat()} ---\n")
            _stderr_file.flush()
        except Exception as _e:
            logger.warning(f"[DEBUG] stderr 캡처 파일 열기 실패: {_e}")
            _stderr_file = _sys.stderr

        options = ClaudeCodeOptions(
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="bypassPermissions",  # dangerously-skip-permissions 대응
            cwd=self.working_dir,
            hooks=hooks,
            env=env,
            extra_args={"debug-to-stderr": None},  # DEBUG: stderr 출력 활성화
            debug_stderr=_stderr_file,  # DEBUG: stderr를 파일에 기록
        )

        # 세션 재개
        if session_id:
            options.resume = session_id

        # OM 디버그 채널 앵커 ts — 세션별 스레드 통합용
        anchor_ts: str = ""

        # Observational Memory: 장기 기억은 새 세션 시작 시만, 세션 관찰은 컴팩션 후만 주입
        # CLI 인자 크기 제한을 회피하기 위해 append_system_prompt가 아닌
        # 첫 번째 query 메시지에 프리픽스로 주입합니다.
        memory_prompt: Optional[str] = None
        if thread_ts:
            try:
                from seosoyoung.config import Config
                if Config.OM_ENABLED:
                    from seosoyoung.memory.context_builder import ContextBuilder, InjectionResult
                    from seosoyoung.memory.store import MemoryStore

                    store = MemoryStore(Config.get_memory_path())
                    is_new_session = session_id is None  # 새 세션일 때만 장기 기억 주입
                    should_inject_session = store.check_and_clear_inject_flag(thread_ts)

                    # 채널 관찰: 관찰 대상 채널에서 멘션될 때만 주입
                    channel_store = None
                    include_channel_obs = False
                    if (
                        is_new_session
                        and Config.CHANNEL_OBSERVER_ENABLED
                        and channel
                        and channel in Config.CHANNEL_OBSERVER_CHANNELS
                    ):
                        from seosoyoung.memory.channel_store import ChannelStore
                        channel_store = ChannelStore(Config.get_memory_path())
                        include_channel_obs = True

                    builder = ContextBuilder(store, channel_store=channel_store)
                    result: InjectionResult = builder.build_memory_prompt(
                        thread_ts,
                        max_tokens=Config.OM_MAX_OBSERVATION_TOKENS,
                        include_persistent=is_new_session,          # 장기 기억: 새 세션만
                        include_session=should_inject_session,  # 세션 관찰: 컴팩션 후만 (inject 플래그)
                        include_channel_observation=include_channel_obs,
                        channel_id=channel,
                        include_new_observations=True,               # 새 관찰: 매 턴 (현재 세션 diff)
                    )

                    if result.prompt:
                        memory_prompt = result.prompt
                        logger.info(
                            f"OM 주입 준비 완료 (thread={thread_ts}, "
                            f"LTM={result.persistent_tokens} tok, "
                            f"새관찰={result.new_observation_tokens} tok, "
                            f"세션={result.session_tokens} tok, "
                            f"채널={result.channel_digest_tokens}+{result.channel_buffer_tokens} tok)"
                        )

                    # 앵커 ts: 새 세션이면 생성, 기존 세션이면 MemoryRecord에서 로드
                    if is_new_session and Config.OM_DEBUG_CHANNEL:
                        try:
                            from seosoyoung.memory.observation_pipeline import _send_debug_log
                            preview = (prompt or "")[:80]
                            if len(prompt or "") > 80:
                                preview += "…"
                            anchor_ts = _send_debug_log(
                                Config.OM_DEBUG_CHANNEL,
                                f"{Config.EMOJI_TEXT_SESSION_START} *OM | 세션 시작 감지* `{thread_ts}`\n>{preview}",
                            )
                            # 새 세션 앵커 ts를 MemoryRecord에 저장 (후속 턴에서 재사용)
                            if anchor_ts:
                                record = store.get_record(thread_ts)
                                if record is None:
                                    from seosoyoung.memory.store import MemoryRecord
                                    record = MemoryRecord(thread_ts=thread_ts)
                                record.anchor_ts = anchor_ts
                                store.save_record(record)
                        except Exception as e:
                            logger.warning(f"OM 앵커 메시지 생성 실패 (무시): {e}")
                    elif not is_new_session and Config.OM_DEBUG_CHANNEL:
                        # 기존 세션: MemoryRecord에서 저장된 anchor_ts 로드
                        record = store.get_record(thread_ts)
                        if record and record.anchor_ts:
                            anchor_ts = record.anchor_ts

                    # 디버그 로그 이벤트 #7, #8: 주입 정보
                    self._send_injection_debug_log(
                        thread_ts, result, Config.OM_DEBUG_CHANNEL, anchor_ts=anchor_ts,
                    )
            except Exception as e:
                logger.warning(f"OM 주입 실패 (무시): {e}")

        return options, memory_prompt, anchor_ts

    @staticmethod
    def _send_injection_debug_log(
        thread_ts: str,
        result: "InjectionResult",
        debug_channel: str,
        anchor_ts: str = "",
    ) -> None:
        """디버그 이벤트 #7, #8: 주입 정보를 슬랙에 발송

        LTM/세션 각각 별도 메시지로 발송하며, 주입 내용을 blockquote로 표시.
        anchor_ts가 있으면 해당 스레드에 답글로 발송.
        anchor_ts가 비었으면 채널 본문 오염 방지를 위해 스킵.
        """
        if not debug_channel:
            return
        if not anchor_ts:
            return
        has_any = (
            result.persistent_tokens
            or result.session_tokens
            or result.channel_digest_tokens
            or result.channel_buffer_tokens
            or result.new_observation_tokens
        )
        if not has_any:
            return

        try:
            from seosoyoung.config import Config
            from seosoyoung.memory.observation_pipeline import (
                _blockquote,
                _format_tokens,
                _send_debug_log,
            )

            sid = thread_ts

            # LTM 주입
            if result.persistent_tokens:
                ltm_quote = _blockquote(result.persistent_content)
                _send_debug_log(
                    debug_channel,
                    f"{Config.EMOJI_TEXT_LTM_INJECT} *OM 장기 기억 주입* `{sid}`\n"
                    f">`LTM {_format_tokens(result.persistent_tokens)} tok`\n"
                    f"{ltm_quote}",
                    thread_ts=anchor_ts,
                )

            # 새 관찰 주입
            if result.new_observation_tokens:
                new_obs_quote = _blockquote(result.new_observation_content)
                _send_debug_log(
                    debug_channel,
                    f"{Config.EMOJI_TEXT_NEW_OBS_INJECT} *OM 새 관찰 주입* `{sid}`\n"
                    f">`새관찰 {_format_tokens(result.new_observation_tokens)} tok`\n"
                    f"{new_obs_quote}",
                    thread_ts=anchor_ts,
                )

            # 세션 관찰 주입
            if result.session_tokens:
                session_quote = _blockquote(result.session_content)
                _send_debug_log(
                    debug_channel,
                    f"{Config.EMOJI_TEXT_SESSION_OBS_INJECT} *OM 세션 관찰 주입* `{sid}`\n"
                    f">`세션 {_format_tokens(result.session_tokens)} tok`\n"
                    f"{session_quote}",
                    thread_ts=anchor_ts,
                )

            # 채널 관찰 주입
            if result.channel_digest_tokens or result.channel_buffer_tokens:
                ch_total = result.channel_digest_tokens + result.channel_buffer_tokens
                _send_debug_log(
                    debug_channel,
                    f"{Config.EMOJI_TEXT_CHANNEL_OBS_INJECT} *채널 관찰 주입* `{sid}`\n"
                    f">`digest {_format_tokens(result.channel_digest_tokens)} tok + "
                    f"buffer {_format_tokens(result.channel_buffer_tokens)} tok = "
                    f"총 {_format_tokens(ch_total)} tok`",
                    thread_ts=anchor_ts,
                )
        except Exception as e:
            logger.warning(f"OM 주입 디버그 로그 실패 (무시): {e}")

    async def run(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        user_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        channel: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> ClaudeResult:
        """Claude Code 실행

        Args:
            prompt: 실행할 프롬프트
            session_id: 이어갈 세션 ID (선택)
            on_progress: 진행 상황 콜백 (선택)
            on_compact: 컴팩션 발생 콜백 (선택) - (trigger, message) 전달
            user_id: 사용자 ID (OM 관찰 로그 주입용, 선택)
            thread_ts: 스레드 타임스탬프 (OM 세션 단위 저장용, 선택)
            channel: 슬랙 채널 ID (MCP 서버 컨텍스트용, 선택)
            user_message: 사용자 원본 메시지 (OM Observer용, 선택). 미지정 시 prompt 사용.
        """
        async with self._lock:
            result = await self._execute(prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel=channel)

        # OM: 세션 종료 후 비동기로 관찰 파이프라인 트리거
        # user_message가 지정되면 사용자 원본 질문만 전달 (채널 히스토리 제외)
        if result.success and user_id and thread_ts and result.collected_messages:
            observation_input = user_message if user_message is not None else prompt
            self._trigger_observation(thread_ts, user_id, observation_input, result.collected_messages, anchor_ts=result.anchor_ts)

        return result

    def _trigger_observation(
        self,
        thread_ts: str,
        user_id: str,
        prompt: str,
        collected_messages: list[dict],
        anchor_ts: str = "",
    ) -> None:
        """관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)

        공유 이벤트 루프에서 ClaudeSDKClient가 실행되므로,
        별도 스레드에서 새 이벤트 루프를 생성하여 OM 파이프라인을 실행합니다.
        """
        try:
            from seosoyoung.config import Config
            if not Config.OM_ENABLED:
                return

            # tool_use/tool_result 메시지를 필터링하여 순수 user/assistant 텍스트만 전달
            # tool 메시지가 포함되면 턴 토큰이 항상 min_turn_tokens를 초과하여
            # Observer 스킵 로직이 작동하지 않는 문제를 방지
            text_messages = [
                m for m in collected_messages
                if m.get("role") != "tool"
                and not (m.get("content", "").startswith("[tool_use:"))
            ]
            messages = [{"role": "user", "content": prompt}] + text_messages

            def _run_in_thread():
                try:
                    from seosoyoung.memory.observation_pipeline import (
                        observe_conversation,
                    )
                    from seosoyoung.memory.observer import Observer
                    from seosoyoung.memory.promoter import Compactor, Promoter
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
                    promoter = Promoter(
                        api_key=Config.OPENAI_API_KEY,
                        model=Config.OM_PROMOTER_MODEL,
                    )
                    compactor = Compactor(
                        api_key=Config.OPENAI_API_KEY,
                        model=Config.OM_PROMOTER_MODEL,
                    )
                    asyncio.run(observe_conversation(
                        store=store,
                        observer=observer,
                        thread_ts=thread_ts,
                        user_id=user_id,
                        messages=messages,
                        min_turn_tokens=Config.OM_MIN_TURN_TOKENS,
                        reflector=reflector,
                        reflection_threshold=Config.OM_REFLECTION_THRESHOLD,
                        promoter=promoter,
                        promotion_threshold=Config.OM_PROMOTION_THRESHOLD,
                        compactor=compactor,
                        compaction_threshold=Config.OM_PERSISTENT_COMPACTION_THRESHOLD,
                        compaction_target=Config.OM_PERSISTENT_COMPACTION_TARGET,
                        debug_channel=debug_channel,
                        anchor_ts=anchor_ts,
                    ))
                except Exception as e:
                    logger.error(f"OM 관찰 파이프라인 비동기 실행 오류 (무시): {e}")
                    try:
                        from seosoyoung.memory.observation_pipeline import _send_debug_log
                        if Config.OM_DEBUG_CHANNEL:
                            _send_debug_log(
                                Config.OM_DEBUG_CHANNEL,
                                f"❌ *OM 스레드 오류*\n• user: `{user_id}`\n• thread: `{thread_ts}`\n• error: `{e}`",
                                thread_ts=anchor_ts,
                            )
                    except Exception:
                        pass

            thread = threading.Thread(target=_run_in_thread, daemon=True)
            thread.start()
            logger.info(f"OM 관찰 파이프라인 트리거됨 (user={user_id}, thread={thread_ts})")
        except Exception as e:
            logger.warning(f"OM 관찰 트리거 실패 (무시): {e}")

    async def _execute(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        user_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> ClaudeResult:
        """실제 실행 로직 (ClaudeSDKClient 기반)"""
        compact_events: list[dict] = []
        compact_notified_count = 0
        options, memory_prompt, anchor_ts = self._build_options(session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel, prompt=prompt)
        # DEBUG: SDK에 전달되는 options 상세 로그
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

        # 스레드 키: thread_ts가 없으면 임시 키 생성
        client_key = thread_ts or f"_ephemeral_{id(asyncio.current_task())}"

        result_session_id = None
        current_text = ""
        result_text = ""
        result_is_error = False  # ResultMessage.is_error 추적
        result_usage: Optional[dict] = None  # ResultMessage.usage 추적
        collected_messages: list[dict] = []  # OM용 대화 수집
        last_progress_time = asyncio.get_event_loop().time()
        progress_interval = 2.0
        # idle 타임아웃: 마지막 메시지 수신 후 이 시간이 지나면 강제 종료
        idle_timeout = self.timeout

        # 외부 retry loop: rate_limit_event 발생 시 client를 정리하고 새로 생성하여 재시도
        # SDK 내부에서 rate_limit_event 수신 후 연결이 끊기므로 같은 iterator를 재사용할 수 없음
        rate_limit_delays = [1, 3, 5]  # 재시도 대기 시간 (초)
        max_attempts = len(rate_limit_delays) + 1  # 최초 1회 + 재시도 3회

        for attempt in range(max_attempts):
            try:
                client = await self._get_or_create_client(client_key, options=options)

                # OM 메모리를 첫 번째 메시지에 프리픽스로 주입
                # CLI 인자 크기 제한을 회피하기 위해 append_system_prompt 대신 이 방식 사용
                effective_prompt = prompt
                if memory_prompt:
                    effective_prompt = (
                        f"{memory_prompt}\n\n"
                        f"위 컨텍스트를 참고하여 질문에 답변해주세요.\n\n"
                        f"사용자의 질문: {prompt}"
                    )
                    logger.info(f"OM 메모리 프리픽스 주입 완료 (prompt 길이: {len(effective_prompt)})")

                await client.query(effective_prompt)

                aiter = client.receive_response().__aiter__()
                rate_limited = False
                rate_limit_event_received = False  # rate_limit_event 수신 여부 추적
                while True:
                    try:
                        message = await asyncio.wait_for(aiter.__anext__(), timeout=idle_timeout)
                    except StopAsyncIteration:
                        # rate_limit_event 후 연결이 끊긴 경우, result_text 없으면 재시도 필요
                        if rate_limit_event_received and not result_text:
                            logger.warning("rate_limit_event 후 연결 종료, result_text 없음 - 재시도 필요")
                            rate_limited = True
                        break
                    except MessageParseError as e:
                        if e.data and e.data.get("type") == "rate_limit_event":
                            # rate_limit_info.status 확인: "allowed"면 정상 진행
                            rate_limit_info = e.data.get("rate_limit_info", {})
                            status = rate_limit_info.get("status", "")

                            # 디버그: 슬랙에 rate_limit_event 정보 전송
                            if channel and thread_ts:
                                debug_msg = (
                                    f"🔍 rate_limit_event:\n"
                                    f"• status: `{status}`\n"
                                    f"• data: `{json.dumps(e.data, ensure_ascii=False)[:500]}`\n"
                                    f"• current_text: {len(current_text)} chars\n"
                                    f"• attempt: {attempt + 1}/{max_attempts}"
                                )
                                _send_debug_to_slack(channel, thread_ts, debug_msg)

                            if status == "allowed":
                                # 정상 요청이지만 SDK가 연결을 끊을 수 있으므로 추적
                                logger.debug(f"rate_limit_event (status=allowed) 수신, 계속 시도")
                                rate_limit_event_received = True
                                continue

                            # status가 allowed가 아닌 경우에만 rate limit 처리
                            logger.warning(
                                f"rate_limit_event 발생 (status={status}): "
                                f"rateLimitType={rate_limit_info.get('rateLimitType')}, "
                                f"resetsAt={rate_limit_info.get('resetsAt')}"
                            )
                            rate_limited = True
                            break
                        raise
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
                                    # 도구 호출 로깅
                                    tool_input = ""
                                    if block.input:
                                        tool_input = json.dumps(block.input, ensure_ascii=False)
                                        if len(tool_input) > 2000:
                                            tool_input = tool_input[:2000] + "..."
                                    logger.info(f"[TOOL_USE] {block.name}: {tool_input[:500]}")
                                    # OM용: 도구 호출 수집
                                    collected_messages.append({
                                        "role": "assistant",
                                        "content": f"[tool_use: {block.name}] {tool_input}",
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    })

                                elif isinstance(block, ToolResultBlock):
                                    # 도구 결과 수집 (내용이 긴 경우 truncate)
                                    content = ""
                                    if isinstance(block.content, str):
                                        content = block.content[:2000]
                                    elif block.content:
                                        content = json.dumps(block.content, ensure_ascii=False)[:2000]
                                    logger.info(f"[TOOL_RESULT] {content[:500]}")
                                    collected_messages.append({
                                        "role": "tool",
                                        "content": content,
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    })

                    # ResultMessage에서 최종 결과 추출
                    elif isinstance(message, ResultMessage):
                        if hasattr(message, 'is_error'):
                            result_is_error = message.is_error
                        if hasattr(message, 'result'):
                            result_text = message.result
                        # ResultMessage에서도 세션 ID 추출 시도
                        if hasattr(message, 'session_id') and message.session_id:
                            result_session_id = message.session_id
                        # usage 정보 추출
                        if hasattr(message, 'usage') and message.usage:
                            result_usage = message.usage

                    # 컴팩션 이벤트 확인 (PreCompact 훅에서 추가된 이벤트)
                    if on_compact and len(compact_events) > compact_notified_count:
                        for event in compact_events[compact_notified_count:]:
                            try:
                                await on_compact(event["trigger"], event["message"])
                            except Exception as e:
                                logger.warning(f"컴팩션 콜백 오류: {e}")
                        compact_notified_count = len(compact_events)

                if rate_limited:
                    # 현재 client를 정리하고 재시도
                    await self._remove_client(client_key)

                    if attempt < len(rate_limit_delays):
                        wait_seconds = rate_limit_delays[attempt]
                        logger.warning(f"rate_limit_event 수신 ({attempt + 1}/{len(rate_limit_delays)}회), {wait_seconds}초 후 새 연결로 재시도")
                        if on_progress:
                            try:
                                await on_progress(f"사용량 제한 감지, {wait_seconds}초 후 재시도합니다 ({attempt + 1}/{len(rate_limit_delays)})")
                            except Exception:
                                pass
                        await asyncio.sleep(wait_seconds)
                        # 상태 초기화 후 다음 attempt로
                        current_text = ""
                        result_text = ""
                        result_is_error = False
                        result_usage = None
                        collected_messages = []
                        last_progress_time = asyncio.get_event_loop().time()
                        compact_notified_count = 0
                        continue
                    else:
                        logger.error(f"rate_limit_event {max_attempts}회 초과, 재시도 중단")
                        return ClaudeResult(
                            success=False,
                            output=current_text,
                            session_id=result_session_id,
                            error="사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요.",
                        )

                # 정상 완료
                output = result_text or current_text

                # 마커 추출
                update_requested = "<!-- UPDATE -->" in output
                restart_requested = "<!-- RESTART -->" in output

                # LIST_RUN 마커 추출
                list_run_match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
                list_run = list_run_match.group(1).strip() if list_run_match else None

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
                    update_requested=update_requested,
                    restart_requested=restart_requested,
                    list_run=list_run,
                    collected_messages=collected_messages,
                    interrupted=result_is_error,
                    usage=result_usage,
                    anchor_ts=anchor_ts,
                )

            except asyncio.TimeoutError:
                logger.error(f"Claude Code SDK idle 타임아웃 ({idle_timeout}초간 메시지 수신 없음)")
                return ClaudeResult(
                    success=False,
                    output=current_text,
                    session_id=result_session_id,
                    error=f"타임아웃: {idle_timeout}초간 SDK 응답 없음",
                    collected_messages=collected_messages,
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
            except MessageParseError as e:
                if e.data and e.data.get("type") == "rate_limit_event":
                    logger.warning(f"rate_limit_event로 실행 실패: {e}")
                    return ClaudeResult(
                        success=False,
                        output=current_text,
                        session_id=result_session_id,
                        error="사용량 제한에 도달했습니다. 잠시 후 다시 시도해주세요.",
                    )
                logger.exception(f"SDK 메시지 파싱 오류: {e}")
                return ClaudeResult(
                    success=False,
                    output=current_text,
                    session_id=result_session_id,
                    error="Claude 응답 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                )
            except Exception as e:
                logger.exception(f"Claude Code SDK 실행 오류: {e}")
                return ClaudeResult(
                    success=False,
                    output=current_text,
                    session_id=result_session_id,
                    error=str(e)
                )
            finally:
                # 응답 완료 또는 에러 시 클라이언트 정리
                await self._remove_client(client_key)

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
