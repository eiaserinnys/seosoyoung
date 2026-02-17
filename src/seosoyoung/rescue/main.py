"""rescue-bot 메인 모듈

슬랙 멘션 → Claude Code SDK 직접 호출 → 결과 응답
soul 서버를 경유하지 않는 독립 경량 봇입니다.
"""

import asyncio
import logging
import re
import sys
import threading

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.rescue.config import RescueConfig
from seosoyoung.rescue.runner import run_claude

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rescue-bot")

# Slack 앱 초기화
app = App(token=RescueConfig.SLACK_BOT_TOKEN, logger=logger)

# 스레드별 실행 락 (동시 실행 방지)
_thread_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_thread_lock(thread_ts: str) -> threading.Lock:
    """스레드별 락을 가져오거나 생성"""
    with _locks_lock:
        if thread_ts not in _thread_locks:
            _thread_locks[thread_ts] = threading.Lock()
        return _thread_locks[thread_ts]


def _strip_mention(text: str, bot_user_id: str | None) -> str:
    """멘션 태그를 제거하고 순수 텍스트만 반환"""
    if bot_user_id:
        text = re.sub(rf"<@{re.escape(bot_user_id)}>", "", text)
    # 기타 멘션도 정리
    text = re.sub(r"<@\w+>", "", text)
    return text.strip()


@app.event("app_mention")
def handle_mention(event, say, client):
    """멘션 이벤트 핸들러

    멘션을 받으면 Claude Code SDK를 호출하고 결과를 스레드에 응답합니다.
    """
    channel = event.get("channel", "")
    user = event.get("user", "")
    text = event.get("text", "")
    ts = event.get("ts", "")
    thread_ts = event.get("thread_ts", ts)

    prompt = _strip_mention(text, RescueConfig.BOT_USER_ID)
    if not prompt:
        say(text="말씀해 주세요.", thread_ts=thread_ts)
        return

    logger.info(f"멘션 수신: user={user}, channel={channel}, prompt={prompt[:80]}")

    # 스레드별 동시 실행 방지
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

        # Claude Code SDK 호출 (동기 래퍼)
        result = asyncio.run(run_claude(prompt))

        if result.success and result.output:
            response = result.output
            # 사고 과정 메시지를 결과로 교체
            if len(response) <= 3900:
                client.chat_update(
                    channel=channel,
                    ts=thinking_ts,
                    text=response,
                )
            else:
                # 긴 응답: 사고 과정을 첫 부분으로 교체, 나머지는 추가 메시지
                client.chat_update(
                    channel=channel,
                    ts=thinking_ts,
                    text=response[:3900] + "...",
                )
                # 나머지를 청크로 분할하여 전송
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
        logger.exception(f"멘션 처리 오류: {e}")
        say(text=f"(rescue-bot) 내부 오류: {e}", thread_ts=thread_ts)
    finally:
        lock.release()


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
