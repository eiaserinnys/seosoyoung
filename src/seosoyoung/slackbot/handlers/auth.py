"""Claude 인증 명령어 핸들러

setup-token, clear-token 명령어와 스레드 내 인증 코드 감지를 처리합니다.
"""

import asyncio
import logging
from typing import Callable

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.soulstream.service_client import SoulServiceClient, SoulServiceError

logger = logging.getLogger(__name__)


# 인증 세션 추적 (Claude 대화 세션과 별도)
# thread_ts -> session_id
_active_auth_sessions: dict[str, str] = {}


def _run_soul_api(async_fn: Callable):
    """SoulServiceClient API를 동기적으로 호출

    Args:
        async_fn: SoulServiceClient 인스턴스를 받아 코루틴을 반환하는 함수

    Returns:
        API 응답
    """
    async def _wrapper():
        soul = SoulServiceClient(
            base_url=Config.claude.soul_url,
            token=Config.claude.soul_token,
        )
        try:
            return await async_fn(soul)
        finally:
            await soul.close()

    return asyncio.run(_wrapper())


def handle_setup_token(
    *,
    say,
    ts,
    thread_ts,
    channel,
    client,
    user_id,
    check_permission,
    **_,
):
    """setup-token 명령어 핸들러

    1. 스레드 생성 + soulstream POST /auth/claude/start 호출
    2. 스레드에 URL + 안내 메시지 전송
    """
    if not check_permission(user_id, client):
        logger.warning(f"setup-token 권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=ts)
        return

    try:
        # 1. 인증 세션 시작
        auth_data = _run_soul_api(lambda soul: soul.start_claude_auth())
        session_id = auth_data.get("session_id", "")
        auth_url = auth_data.get("auth_url", "")

        if not session_id or not auth_url:
            say(text="❌ 인증 세션 시작에 실패했습니다: 응답 데이터가 유효하지 않습니다.", thread_ts=ts)
            return

        # 2. 스레드 생성 + URL 안내
        message = (
            "🔐 *Claude Code 인증을 시작합니다.*\n\n"
            f"아래 URL을 브라우저에서 열어 인증해주세요:\n{auth_url}\n\n"
            "인증 후 화면에 표시되는 코드를 이 스레드에 붙여넣어 주세요.\n\n"
            "⏱️ 5분 내에 완료해주세요."
        )

        # 스레드 메시지로 전송 (새 스레드 생성)
        result = say(text=message, thread_ts=ts)
        new_thread_ts = result.get("ts", ts)

        # 3. 인증 세션 추적 등록
        _active_auth_sessions[new_thread_ts] = session_id
        logger.info(f"인증 세션 등록: thread_ts={new_thread_ts}, session_id={session_id}")

    except SoulServiceError as e:
        logger.exception(f"setup-token 실패: {e}")
        say(text=f"❌ 인증 세션 시작 실패: {e}", thread_ts=ts)
    except Exception as e:
        logger.exception(f"setup-token 예기치 않은 오류: {e}")
        say(text=f"❌ 오류가 발생했습니다: {e}", thread_ts=ts)


def handle_clear_token(
    *,
    say,
    ts,
    client,
    user_id,
    check_permission,
    **_,
):
    """clear-token 명령어 핸들러

    soulstream DELETE /auth/claude/token 호출
    """
    if not check_permission(user_id, client):
        logger.warning(f"clear-token 권한 없음: user={user_id}")
        say(text="관리자 권한이 필요합니다.", thread_ts=ts)
        return

    try:
        _run_soul_api(lambda soul: soul.clear_claude_token())
        say(text="✅ Claude 토큰이 삭제되었습니다.", thread_ts=ts)
        logger.info(f"Claude 토큰 삭제 완료: user={user_id}")

    except SoulServiceError as e:
        logger.exception(f"clear-token 실패: {e}")
        say(text=f"❌ 토큰 삭제 실패: {e}", thread_ts=ts)
    except Exception as e:
        logger.exception(f"clear-token 예기치 않은 오류: {e}")
        say(text=f"❌ 오류가 발생했습니다: {e}", thread_ts=ts)


def check_auth_session(
    thread_ts: str,
    text: str,
    say,
    client,
    dependencies: dict,
) -> bool:
    """인증 세션에서 코드 입력 감지. 처리했으면 True 반환.

    Args:
        thread_ts: 스레드 타임스탬프
        text: 메시지 텍스트
        say: 응답 함수
        client: Slack 클라이언트
        dependencies: 의존성 딕셔너리

    Returns:
        True if handled, False otherwise
    """
    if thread_ts not in _active_auth_sessions:
        return False

    session_id = _active_auth_sessions[thread_ts]
    code = text.strip()

    # 빈 코드는 무시
    if not code:
        return False

    # 코드 형식 검증 (Claude 인증 코드는 일반적으로 영숫자)
    # 너무 긴 코드나 공백이 포함된 경우 무시
    if len(code) > 200 or " " in code:
        return False

    logger.info(f"인증 코드 감지: thread_ts={thread_ts}, code_length={len(code)}")

    try:
        # soulstream API 호출
        result = _run_soul_api(lambda soul: soul.submit_auth_code(session_id, code))

        if result.get("success"):
            expires_at = result.get("expires_at", "1년")
            say(text=f"✅ 인증이 완료되었습니다! ({expires_at} 유효)", thread_ts=thread_ts)
            logger.info(f"인증 성공: thread_ts={thread_ts}")
        else:
            error_msg = result.get("error", "알 수 없는 오류")
            say(text=f"❌ 인증 실패: {error_msg}", thread_ts=thread_ts)
            logger.warning(f"인증 실패: thread_ts={thread_ts}, error={error_msg}")

    except SoulServiceError as e:
        logger.exception(f"인증 코드 제출 실패: {e}")
        say(text=f"❌ 인증 실패: {e}", thread_ts=thread_ts)
    except Exception as e:
        logger.exception(f"인증 코드 제출 예기치 않은 오류: {e}")
        say(text=f"❌ 오류가 발생했습니다: {e}", thread_ts=thread_ts)
    finally:
        # 세션 정리 (성공/실패 무관)
        _active_auth_sessions.pop(thread_ts, None)
        logger.info(f"인증 세션 정리: thread_ts={thread_ts}")

    return True


def get_active_auth_sessions() -> dict[str, str]:
    """활성 인증 세션 조회 (테스트용)"""
    return _active_auth_sessions.copy()


def clear_auth_sessions() -> None:
    """모든 인증 세션 초기화 (테스트용)"""
    _active_auth_sessions.clear()
