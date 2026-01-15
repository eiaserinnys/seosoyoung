"""SeoSoyoung 슬랙 봇 메인"""

import asyncio
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.config import Config
from seosoyoung.claude.runner import ClaudeRunner
from seosoyoung.claude.session import SessionManager

# 로깅 설정
def setup_logging():
    log_dir = Path(Config.LOG_PATH)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.DEBUG if Config.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

app = App(token=Config.SLACK_BOT_TOKEN, logger=logger)

# Claude Code 연동
claude_runner = ClaudeRunner()
session_manager = SessionManager()


def check_permission(user_id: str, client) -> bool:
    """사용자 권한 확인"""
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        allowed = username in Config.ALLOWED_USERS
        logger.debug(f"권한 체크: user_id={user_id}, username={username}, allowed={allowed}")
        return allowed
    except Exception as e:
        logger.error(f"권한 체크 실패: user_id={user_id}, error={e}")
        return False


def extract_command(text: str) -> str:
    """멘션에서 명령어 추출"""
    # <@U12345> command -> command
    match = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return match.lower()


@app.event("app_mention")
def handle_mention(event, say, client):
    """@seosoyoung 멘션 처리"""
    user_id = event["user"]
    text = event.get("text", "")
    channel = event["channel"]
    ts = event["ts"]

    logger.info(f"멘션 수신: user={user_id}, channel={channel}, text={text[:50]}")

    # 권한 확인
    if not check_permission(user_id, client):
        logger.warning(f"권한 없음: user={user_id}")
        say(text="👩 권한이 없습니다.", thread_ts=ts)
        return

    command = extract_command(text)
    logger.info(f"명령어 처리: command={command}")

    if command == "cc":
        # Claude Code 세션 시작
        say(
            text="👩 소영이 작업을 시작합니다. 스레드 안에서 대화해주세요.",
            thread_ts=ts
        )
        # 세션 생성
        session_manager.create(thread_ts=ts, channel_id=channel)
        logger.info(f"세션 생성: thread_ts={ts}, channel={channel}")

    elif command == "help":
        say(
            text=(
                "📖 *사용법*\n"
                "• `@seosoyoung cc` - 작업 세션 시작\n"
                "• `@seosoyoung help` - 도움말\n"
                "• `@seosoyoung status` - 상태 확인\n"
                "• `@seosoyoung update` - 봇 업데이트\n"
                "• `@seosoyoung restart` - 봇 재시작"
            ),
            thread_ts=ts
        )

    elif command == "status":
        say(
            text=(
                f"📊 *상태*\n"
                f"• eb_renpy 경로: `{Config.EB_RENPY_PATH}`\n"
                f"• 허용 사용자: {', '.join(Config.ALLOWED_USERS)}\n"
                f"• 활성 세션: {session_manager.count()}개\n"
                f"• 디버그 모드: {Config.DEBUG}"
            ),
            thread_ts=ts
        )

    elif command == "update":
        say(text="👩 업데이트합니다. 잠시만요...", thread_ts=ts)
        logger.info("업데이트 요청 - 프로세스 종료")
        os._exit(42)

    elif command == "restart":
        say(text="👩 재시작합니다. 잠시만요...", thread_ts=ts)
        logger.info("재시작 요청 - 프로세스 종료")
        os._exit(43)

    else:
        say(
            text=f"👩 알 수 없는 명령입니다: `{command}`\n`@seosoyoung help`를 입력해보세요.",
            thread_ts=ts
        )


@app.event("message")
def handle_message(event, say, client):
    """스레드 메시지 처리"""
    # 봇 자신의 메시지는 무시
    if event.get("bot_id"):
        return

    # 스레드 메시지인 경우만 처리
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return

    user_id = event["user"]
    text = event.get("text", "")
    channel = event["channel"]

    # 권한 확인
    if not check_permission(user_id, client):
        return

    # 세션 확인
    session = session_manager.get(thread_ts)
    if not session:
        # 세션이 없으면 무시 (cc 명령으로 시작한 스레드만 처리)
        return

    # 멘션 제거 (스레드 내에서도 멘션할 수 있으므로)
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    if not clean_text:
        return

    logger.info(f"메시지 처리: thread_ts={thread_ts}, text={clean_text[:50]}")

    # 작업 중 이모지 추가
    try:
        client.reactions_add(channel=channel, timestamp=event["ts"], name="eyes")
    except Exception:
        pass

    # Claude Code 실행
    try:
        result = asyncio.run(claude_runner.run(
            prompt=clean_text,
            session_id=session.session_id
        ))

        # 세션 ID 업데이트 (첫 응답에서 받음)
        if result.session_id and result.session_id != session.session_id:
            session_manager.update_session_id(thread_ts, result.session_id)

        # 메시지 카운트 증가
        session_manager.increment_message_count(thread_ts)

        if result.success:
            # 응답 전송 (길면 분할)
            response = result.output or "(응답 없음)"
            send_long_message(say, response, thread_ts)

            # 완료 이모지
            try:
                client.reactions_add(channel=channel, timestamp=event["ts"], name="white_check_mark")
            except Exception:
                pass
        else:
            say(text=f"👩 오류가 발생했습니다: {result.error}", thread_ts=thread_ts)
            try:
                client.reactions_add(channel=channel, timestamp=event["ts"], name="x")
            except Exception:
                pass

    except Exception as e:
        logger.exception(f"Claude Code 실행 오류: {e}")
        say(text=f"👩 오류가 발생했습니다: {str(e)}", thread_ts=thread_ts)

    # 작업 중 이모지 제거
    try:
        client.reactions_remove(channel=channel, timestamp=event["ts"], name="eyes")
    except Exception:
        pass


def send_long_message(say, text: str, thread_ts: str, max_length: int = 3900):
    """긴 메시지를 분할해서 전송"""
    if len(text) <= max_length:
        say(text=f"👩 {text}", thread_ts=thread_ts)
        return

    # 줄 단위로 분할
    lines = text.split("\n")
    chunks = []
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk = current_chunk + "\n" + line if current_chunk else line

    if current_chunk:
        chunks.append(current_chunk)

    # 분할된 메시지 전송
    for i, chunk in enumerate(chunks):
        prefix = f"👩 ({i+1}/{len(chunks)})\n" if len(chunks) > 1 else "👩 "
        say(text=prefix + chunk, thread_ts=thread_ts)


@app.event("reaction_added")
def handle_reaction(event, client):
    """이모지 리액션 처리"""
    # TODO: 리액션 기반 동작 구현
    pass


def notify_startup():
    """봇 시작 알림"""
    if Config.NOTIFY_CHANNEL:
        try:
            app.client.chat_postMessage(
                channel=Config.NOTIFY_CHANNEL,
                text="👩 소영이가 시작되었습니다."
            )
            logger.info(f"시작 알림 전송: {Config.NOTIFY_CHANNEL}")
        except Exception as e:
            logger.error(f"시작 알림 실패: {e}")


if __name__ == "__main__":
    logger.info("SeoSoyoung 봇을 시작합니다...")
    logger.info(f"LOG_PATH: {Config.LOG_PATH}")
    logger.info(f"ALLOWED_USERS: {Config.ALLOWED_USERS}")
    logger.info(f"DEBUG: {Config.DEBUG}")
    notify_startup()
    handler = SocketModeHandler(app, Config.SLACK_APP_TOKEN)
    handler.start()
