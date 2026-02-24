"""Claude Soul Service Adapter

SoulServiceClient를 통해 원격 soul 서버에 Claude Code 실행을 위임하고,
결과를 기존 ClaudeResult 포맷으로 변환합니다.

ClaudeExecutor에서 local/remote 분기 시 remote 경로로 사용됩니다.
"""

import logging
import re
from typing import Awaitable, Callable, Optional

from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
from seosoyoung.slackbot.claude.service_client import (
    SoulServiceClient,
    SoulServiceError,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class ClaudeServiceAdapter:
    """원격 soul 서버 어댑터

    executor의 _execute_once에서 remote 모드일 때 사용.
    SoulServiceClient로 실행하고 ClaudeResult로 변환합니다.
    """

    def __init__(self, client: SoulServiceClient, client_id: str):
        self._client = client
        self._client_id = client_id

    async def execute(
        self,
        prompt: str,
        request_id: str,
        resume_session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> ClaudeResult:
        """Claude Code를 soul 서버에서 실행하고 ClaudeResult로 반환

        Args:
            prompt: 실행할 프롬프트
            request_id: 요청 ID (스레드 ts 등)
            resume_session_id: 이전 Claude 세션 ID
            on_progress: 진행 상황 콜백
            on_compact: 컴팩션 콜백

        Returns:
            ClaudeResult: 기존 로컬 실행과 동일한 포맷의 결과
        """
        try:
            result = await self._client.execute(
                client_id=self._client_id,
                request_id=request_id,
                prompt=prompt,
                resume_session_id=resume_session_id,
                on_progress=on_progress,
                on_compact=on_compact,
            )

            if result.success:
                # ack
                await self._client.ack(self._client_id, request_id)

                output = result.result or ""

                # 마커 추출 (로컬 실행과 동일)
                update_requested = "<!-- UPDATE -->" in output
                restart_requested = "<!-- RESTART -->" in output
                list_run_match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
                list_run = list_run_match.group(1).strip() if list_run_match else None

                return ClaudeResult(
                    success=True,
                    output=output,
                    session_id=result.claude_session_id,
                    update_requested=update_requested,
                    restart_requested=restart_requested,
                    list_run=list_run,
                )
            else:
                return ClaudeResult(
                    success=False,
                    output="",
                    error=result.error or result.result,
                )

        except TaskConflictError:
            return ClaudeResult(
                success=False,
                output="",
                error="이미 실행 중인 태스크가 있습니다.",
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
                error=f"소울 서비스 오류: {e}",
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
        request_id: str,
        text: str,
        user: str,
    ) -> bool:
        """실행 중인 태스크에 인터벤션 전송

        Returns:
            True: 성공, False: 실패
        """
        try:
            await self._client.intervene(
                client_id=self._client_id,
                request_id=request_id,
                text=text,
                user=user,
            )
            logger.info(f"[Remote] 인터벤션 전송 완료: {self._client_id}:{request_id}")
            return True
        except (TaskNotFoundError, TaskNotRunningError) as e:
            logger.warning(f"[Remote] 인터벤션 전송 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"[Remote] 인터벤션 전송 오류: {e}")
            return False

    async def close(self) -> None:
        """클라이언트 종료"""
        await self._client.close()
