"""rescue-bot 메인 모듈

슬랙 멘션/스레드 메시지 → Claude Code SDK 직접 호출 → 결과 응답
soul 서버를 경유하지 않는 독립 경량 봇입니다.

세션 관리:
- 스레드 ts를 키로 session_id를 in-memory dict에 저장
- 스레드 내 후속 대화(멘션 또는 일반 메시지)에서 세션을 이어감
"""

import logging
import re
import sys
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.rescue.config import RescueConfig
from seosoyoung.rescue.runner import run_claude_sync

# 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rescue-bot")

# Slack 앱 초기화
app = App(token=RescueConfig.SLACK_BOT_TOKEN, logger=logger)

# 스레드별 실행 락 (동시 실행 방지)
_thread_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

# 스레드별 세션 ID 저장 (in-memory)
_sessions: dict[str, str] = {}
_sessions_lock = threading.Lock()


def _get_thread_lock(thread_ts: str) -> threading.Lock:
    """스레드별 락을 가져오거나 생성"""
    with _locks_lock:
        if thread_ts not in _thread_locks:
            _thread_locks[thread_ts] = threading.Lock()
        return _thread_locks[thread_ts]


def _get_session_id(thread_ts: str) -> str | None:
    """스레드의 세션 ID를 조회"""
    with _sessions_lock:
        return _sessions.get(thread_ts)


def _set_session_id(thread_ts: str, session_id: str) -> None:
    """스레드의 세션 ID를 저장"""
    with _sessions_lock:
        _sessions[thread_ts] = session_id


def _strip_mention(text: str, bot_user_id: str | None) -> str:
    """멘션 태그를 제거하고 순수 텍스트만 반환"""
    if bot_user_id:
        text = re.sub(rf"<@{re.escape(bot_user_id)}>", "", text)
    # 기타 멘션도 정리
    text = re.sub(r"<@\w+>", "", text)
    return text.strip()


def _contains_bot_mention(text: str) -> bool:
    """텍스트에 봇 멘션이 포함되어 있는지 확인"""
    if not RescueConfig.BOT_USER_ID:
        return "<@" in text
    return f"<@{RescueConfig.BOT_USER_ID}>" in text


def _process_message(prompt: str, thread_ts: str, channel: str, say, client):
    """공통 메시지 처리 로직

    멘션/메시지 핸들러에서 공유합니다.
    세션이 있으면 이어서 실행하고, 결과의 session_id를 저장합니다.
    """
    lock = _get_thread_lock(thread_ts)
    if not lock.acquire(blocking=False):
        say(text="이전 요청을 처리 중입니다. 잠시 기다려 주세요.", thread_ts=thread_ts)
        return

    try:
        # 사고 과정 메시지 표시
        thinking_msg = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="> (rescue-bot) 생각 중...",
        )
        thinking_ts = thinking_msg["ts"]

        # 기존 세션 조회
        session_id = _get_session_id(thread_ts)
        logger.info(f"세션 조회: thread_ts={thread_ts}, session_id={session_id}")

        # Claude Code SDK 호출 (asyncio.run으로 매 호출마다 새 루프 생성)
        result = run_claude_sync(prompt, session_id=session_id)

        logger.info(f"SDK 결과: success={result.success}, session_id={result.session_id}, error={result.error}")

        # 세션 ID 저장
        if result.session_id:
            _set_session_id(thread_ts, result.session_id)
            logger.info(f"세션 저장: thread_ts={thread_ts} → session_id={result.session_id}")

        if result.success and result.output:
            response = result.output
            if len(response) <= 3900:
                client.chat_update(
                    channel=channel,
                    ts=thinking_ts,
                    text=response,
                )
            else:
                client.chat_update(
                    channel=channel,
                    ts=thinking_ts,
                    text=response[:3900] + "...",
                )
                remaining = response[3900:]
                while remaining:
                    chunk = remaining[:3900]
                    remaining = remaining[3900:]
                    say(text=chunk, thread_ts=thread_ts)
        elif result.error:
            client.chat_update(
                channel=channel,
                ts=thinking_ts,
                text=f"(rescue-bot) 오류: {result.error}",
            )
        else:
            client.chat_update(
                channel=channel,
                ts=thinking_ts,
                text="(rescue-bot) 응답이 비어 있습니다.",
            )
    except Exception as e:
        logger.exception(f"메시지 처리 오류: {e}")
        say(text=f"(rescue-bot) 내부 오류: {e}", thread_ts=thread_ts)
    finally:
        lock.release()


@app.event("app_mention")
def handle_mention(event, say, client):
    """멘션 이벤트 핸들러

    멘션을 받으면 Claude Code SDK를 호출하고 결과를 스레드에 응답합니다.
    기존 세션이 있으면 이어서 실행합니다.
    """
    channel = event.get("channel", "")
    user = event.get("user", "")
    text = event.get("text", "")
    ts = event.get("ts", "")
    thread_ts = event.get("thread_ts", ts)

    # 봇 자신의 메시지는 무시
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    prompt = _strip_mention(text, RescueConfig.BOT_USER_ID)
    if not prompt:
        say(text="말씀해 주세요.", thread_ts=thread_ts)
        return

    logger.info(f"멘션 수신: user={user}, channel={channel}, thread_ts={thread_ts}, prompt={prompt[:80]}")

    _process_message(prompt, thread_ts, channel, say, client)


@app.event("message")
def handle_message(event, say, client):
    """스레드 메시지 핸들러

    세션이 있는 스레드 내 일반 메시지(멘션 없이)를 처리합니다.
    """
    # 봇 자신의 메시지는 무시
    if event.get("bot_id"):
        return

    # subtype이 있는 메시지는 무시 (메시지 수정, 삭제 등)
    if event.get("subtype"):
        return

    text = event.get("text", "")

    # 봇 멘션이 포함된 경우 handle_mention에서 처리 (중복 방지)
    if _contains_bot_mention(text):
        return

    # 스레드 메시지인 경우만 처리
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return

    # 세션이 있는 스레드만 처리
    session_id = _get_session_id(thread_ts)
    if not session_id:
        logger.debug(f"세션 없음: thread_ts={thread_ts}, 현재 세션={list(_sessions.keys())}")
        return

    channel = event.get("channel", "")
    user = event.get("user", "")

    prompt = _strip_mention(text, RescueConfig.BOT_USER_ID)
    if not prompt:
        return

    logger.info(f"스레드 메시지: user={user}, channel={channel}, thread_ts={thread_ts}, prompt={prompt[:80]}")

    _process_message(prompt, thread_ts, channel, say, client)


def main():
    """rescue-bot 진입점"""
    logger.info("rescue-bot을 시작합니다...")

    RescueConfig.validate()

    # 봇 사용자 ID 초기화
    try:
        auth_result = app.client.auth_test()
        RescueConfig.BOT_USER_ID = auth_result["user_id"]
        logger.info(f"BOT_USER_ID: {RescueConfig.BOT_USER_ID}")
    except Exception as e:
        logger.error(f"봇 ID 조회 실패: {e}")

    handler = SocketModeHandler(app, RescueConfig.SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
