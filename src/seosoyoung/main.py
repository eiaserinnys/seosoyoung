"""SeoSoyoung 슬랙 봇 메인"""

import sys
import re
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.config import Config

app = App(token=Config.SLACK_BOT_TOKEN)


def check_permission(user_id: str, client) -> bool:
    """사용자 권한 확인"""
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        print(f"[DEBUG] user_id={user_id}, username={username}, ALLOWED_USERS={Config.ALLOWED_USERS}")
        return username in Config.ALLOWED_USERS
    except Exception as e:
        print(f"[DEBUG] check_permission error: {e}")
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

    # 권한 확인
    if not check_permission(user_id, client):
        say(text="👩 권한이 없습니다.", thread_ts=ts)
        return

    command = extract_command(text)

    if command == "cc":
        # Claude Code 세션 시작
        say(
            text="👩 소영이 작업을 시작합니다. 스레드 안에서 대화해주세요.",
            thread_ts=ts
        )
        # TODO: Claude Code 세션 생성

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
                f"• 디버그 모드: {Config.DEBUG}"
            ),
            thread_ts=ts
        )

    elif command == "update":
        say(text="👩 업데이트합니다. 잠시만요...", thread_ts=ts)
        sys.exit(42)

    elif command == "restart":
        say(text="👩 재시작합니다. 잠시만요...", thread_ts=ts)
        sys.exit(43)

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

    # 권한 확인
    if not check_permission(user_id, client):
        return

    # TODO: Claude Code로 메시지 전달
    # 지금은 에코만
    say(
        text=f"👩 (에코) {text}\n\n_Claude Code 연동은 아직 구현 중입니다._",
        thread_ts=thread_ts
    )


@app.event("reaction_added")
def handle_reaction(event, client):
    """이모지 리액션 처리"""
    # TODO: 리액션 기반 동작 구현
    pass


if __name__ == "__main__":
    print("⚡ SeoSoyoung 봇을 시작합니다...")
    handler = SocketModeHandler(app, Config.SLACK_APP_TOKEN)
    handler.start()
