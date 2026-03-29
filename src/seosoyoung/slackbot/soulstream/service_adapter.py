"""Soulstream Service Adapter

SoulServiceClient를 통해 Soulstream 서버에 Claude Code 실행을 위임하고,
결과를 기존 ClaudeResult 포맷으로 변환합니다.

per-session 아키텍처: agent_session_id가 유일한 식별자.
"""

import logging
from typing import Awaitable, Callable, List, Optional

from seosoyoung.slackbot.soulstream.engine_types import ClaudeResult
from seosoyoung.slackbot.soulstream.service_client import (
    SoulServiceClient,
    SoulServiceError,
    SessionConflictError,
    SessionNotFoundError,
    SessionNotRunningError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class ClaudeServiceAdapter:
    """Soulstream 서버 어댑터

    executor의 _execute_once에서 사용.
    SoulServiceClient로 Soulstream에 실행을 위임하고 ClaudeResult로 변환합니다.

    per-session 아키텍처: agent_session_id가 유일한 식별자.
    client_id, request_id는 사용하지 않습니다.
    """

    def __init__(self, client: SoulServiceClient, *,
                 parse_markers_fn: Optional[Callable] = None):
        self._client = client
        self._parse_markers_fn = parse_markers_fn

    async def execute(
        self,
        prompt: str,
        agent_session_id: Optional[str] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_debug: Optional[Callable[[str], Awaitable[None]]] = None,
        on_session: Optional[Callable[[str], Awaitable[None]]] = None,
        on_credential_alert: Optional[Callable[[dict], Awaitable[None]]] = None,
        *,
        # 세분화 이벤트 콜백
        on_thinking: Optional[Callable] = None,
        on_text_start: Optional[Callable] = None,
        on_text_delta: Optional[Callable] = None,
        on_text_end: Optional[Callable] = None,
        on_tool_start: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
        on_input_request: Optional[Callable] = None,
        allowed_tools: Optional[list[str]] = None,
        disallowed_tools: Optional[list[str]] = None,
        use_mcp: bool = True,
        context: Optional[list] = None,
        model: Optional[str] = None,
        folder_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> ClaudeResult:
        """Claude Code를 Soulstream에서 실행하고 ClaudeResult로 반환

        Args:
            prompt: 실행할 프롬프트
            agent_session_id: 기존 세션 ID (없으면 새 세션, 있으면 resume)
            on_compact: 컴팩션 콜백
            on_debug: 디버그 메시지 콜백 (rate_limit 경고 등)
            on_session: 세션 ID 조기 통지 콜백 (agent_session_id: str)
            on_credential_alert: 크레덴셜 알림 콜백 (data: dict)
            allowed_tools: 허용 도구 목록 (None이면 서버 기본값 사용)
            disallowed_tools: 금지 도구 목록
            use_mcp: MCP 서버 연결 여부

        Returns:
            ClaudeResult: 기존 로컬 실행과 동일한 포맷의 결과
        """
        try:
            result = await self._client.execute(
                prompt=prompt,
                agent_session_id=agent_session_id,
                on_compact=on_compact,
                on_debug=on_debug,
                on_session=on_session,
                on_credential_alert=on_credential_alert,
                on_thinking=on_thinking,
                on_text_start=on_text_start,
                on_text_delta=on_text_delta,
                on_text_end=on_text_end,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                on_input_request=on_input_request,
                allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                use_mcp=use_mcp,
                context=context,
                model=model,
                folder_id=folder_id,
                system_prompt=system_prompt,
                profile=profile,
            )

            if result.success:
                output = result.result or ""
                markers = self._parse_markers_fn(output) if self._parse_markers_fn else None

                return ClaudeResult(
                    success=True,
                    output=output,
                    session_id=result.agent_session_id,
                    update_requested=getattr(markers, "update_requested", False),
                    restart_requested=getattr(markers, "restart_requested", False),
                    list_run=getattr(markers, "list_run", None),
                )
            else:
                return ClaudeResult(
                    success=False,
                    output="",
                    error=result.error or result.result,
                    session_id=result.agent_session_id,
                )

        except SessionConflictError:
            return ClaudeResult(
                success=False,
                output="",
                error="이미 실행 중인 세션이 있습니다.",
            )

        except RateLimitError:
            return ClaudeResult(
                success=False,
                output="",
                error="동시 실행 제한을 초과했습니다. 잠시 후 다시 시도해주세요.",
            )

        except SoulServiceError as e:
            logger.error(f"[Remote] Soul service error: {e}")
            return ClaudeResult(
                success=False,
                output="",
                error=f"Soulstream 오류: {e}",
            )

        except Exception as e:
            logger.exception(f"[Remote] Unexpected error: {e}")
            return ClaudeResult(
                success=False,
                output="",
                error=f"원격 실행 오류: {e}",
            )

    async def intervene(
        self,
        agent_session_id: str,
        text: str,
        user: str,
        *,
        attachment_paths: Optional[List[str]] = None,
    ) -> bool:
        """세션에 인터벤션 전송 (agent_session_id 기반)

        Returns:
            True: 성공, False: 실패
        """
        try:
            await self._client.intervene(
                agent_session_id=agent_session_id,
                text=text,
                user=user,
                attachment_paths=attachment_paths,
            )
            logger.info(f"[Remote] 인터벤션 전송 완료: session={agent_session_id}")
            return True
        except (SessionNotFoundError, SessionNotRunningError) as e:
            logger.warning(f"[Remote] 인터벤션 전송 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"[Remote] 인터벤션 전송 오류: {e}")
            return False

    async def close(self) -> None:
        """클라이언트 종료"""
        await self._client.close()
