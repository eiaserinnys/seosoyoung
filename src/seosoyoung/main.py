"""SeoSoyoung 슬랙 봇 메인"""

import asyncio
import os
import re
import logging
import threading
from datetime import datetime
from pathlib import Path
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.config import Config
from seosoyoung.claude.runner import ClaudeRunner
from seosoyoung.claude.session import SessionManager
from seosoyoung.claude.security import validate_attach_path

# 로깅 설정
def setup_logging():
    log_dir = Path(Config.get_log_path())
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
session_manager = SessionManager()

# 실행 중인 세션 락 (스레드별 동시 실행 방지)
_session_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def get_session_lock(thread_ts: str) -> threading.Lock:
    """스레드별 락 반환 (없으면 생성)"""
    with _locks_lock:
        if thread_ts not in _session_locks:
            _session_locks[thread_ts] = threading.Lock()
        return _session_locks[thread_ts]


def get_runner_for_role(role: str) -> ClaudeRunner:
    """역할에 맞는 ClaudeRunner 반환"""
    allowed_tools = Config.ROLE_TOOLS.get(role, Config.ROLE_TOOLS["viewer"])
    # viewer는 수정/실행 도구 명시적 차단
    if role == "viewer":
        return ClaudeRunner(
            allowed_tools=allowed_tools,
            disallowed_tools=["Write", "Edit", "Bash", "TodoWrite", "WebFetch", "WebSearch", "Task"]
        )
    return ClaudeRunner(allowed_tools=allowed_tools)


def check_permission(user_id: str, client) -> bool:
    """사용자 권한 확인 (관리자 명령어용)"""
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        allowed = username in Config.ALLOWED_USERS
        logger.debug(f"권한 체크: user_id={user_id}, username={username}, allowed={allowed}")
        return allowed
    except Exception as e:
        logger.error(f"권한 체크 실패: user_id={user_id}, error={e}")
        return False


def get_user_role(user_id: str, client) -> dict | None:
    """사용자 역할 정보 반환

    Returns:
        dict: {"user_id", "username", "role", "allowed_tools"} 또는 실패 시 None
    """
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        role = "admin" if username in Config.ADMIN_USERS else "viewer"
        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "allowed_tools": Config.ROLE_TOOLS[role]
        }
    except Exception as e:
        logger.error(f"사용자 역할 조회 실패: user_id={user_id}, error={e}")
        return None


def extract_command(text: str) -> str:
    """멘션에서 명령어 추출"""
    # <@U12345> command -> command
    match = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return match.lower()


def get_channel_history(client, channel: str, limit: int = 20) -> str:
    """채널의 최근 메시지를 가져와서 컨텍스트 문자열로 반환"""
    try:
        result = client.conversations_history(channel=channel, limit=limit)
        messages = result.get("messages", [])

        # 시간순 정렬 (오래된 것부터)
        messages = list(reversed(messages))

        context_lines = []
        for msg in messages:
            user = msg.get("user", "unknown")
            text = msg.get("text", "")
            context_lines.append(f"<{user}>: {text}")

        return "\n".join(context_lines)
    except Exception as e:
        logger.warning(f"채널 히스토리 가져오기 실패: {e}")
        return ""


@app.event("app_mention")
def handle_mention(event, say, client):
    """@seosoyoung 멘션 처리

    - 채널에서 멘션: 세션 생성 + Claude 실행
    - 스레드에서 멘션 (세션 있음): handle_message에서 처리
    - 스레드에서 멘션 (세션 없음): 원샷 답변
    - help/status/update/restart: 관리자 명령어
    """
    user_id = event["user"]
    text = event.get("text", "")
    channel = event["channel"]
    ts = event["ts"]
    thread_ts = event.get("thread_ts")  # 스레드에서 호출되었으면 값 있음

    logger.info(f"멘션 수신: user={user_id}, channel={channel}, text={text[:50]}")

    # 스레드에서 멘션된 경우
    if thread_ts:
        # 기존 세션이 있으면 handle_message에서 처리
        if session_manager.exists(thread_ts):
            logger.debug("스레드에서 멘션됨 (세션 있음) - handle_message에서 처리")
            return
        # 세션이 없으면 원샷 답변 (아래에서 처리)
        logger.debug("스레드에서 멘션됨 (세션 없음) - 원샷 답변")

    command = extract_command(text)
    logger.info(f"명령어 처리: command={command}")

    # 관리자 명령어 처리
    if command == "help":
        say(
            text=(
                "📖 *사용법*\n"
                "• `@seosoyoung <질문>` - 질문하기 (세션 생성 + 응답)\n"
                "• `@seosoyoung help` - 도움말\n"
                "• `@seosoyoung status` - 상태 확인\n"
                "• `@seosoyoung update` - 봇 업데이트 (관리자)\n"
                "• `@seosoyoung restart` - 봇 재시작 (관리자)"
            ),
            thread_ts=ts
        )
        return

    if command == "status":
        say(
            text=(
                f"📊 *상태*\n"
                f"• 작업 폴더: `{Path.cwd()}`\n"
                f"• 관리자: {', '.join(Config.ADMIN_USERS)}\n"
                f"• 활성 세션: {session_manager.count()}개\n"
                f"• 디버그 모드: {Config.DEBUG}"
            ),
            thread_ts=ts
        )
        return

    if command in ["update", "restart"]:
        if not check_permission(user_id, client):
            logger.warning(f"권한 없음: user={user_id}")
            say(text="관리자 권한이 필요합니다.", thread_ts=ts)
            return

        if command == "update":
            say(text="업데이트합니다. 잠시만요...", thread_ts=ts)
            logger.info("업데이트 요청 - 프로세스 종료")
            os._exit(42)
        else:
            say(text="재시작합니다. 잠시만요...", thread_ts=ts)
            logger.info("재시작 요청 - 프로세스 종료")
            os._exit(43)
        return

    # 일반 질문: 세션 생성 + Claude 실행
    # 사용자 역할 조회
    user_info = get_user_role(user_id, client)
    if not user_info:
        say(text="사용자 정보를 확인할 수 없습니다.", thread_ts=thread_ts or ts)
        return

    # 세션 생성 위치 결정
    # - 채널에서 호출: ts가 스레드 시작점
    # - 스레드에서 호출 (세션 없음): thread_ts가 스레드 시작점
    session_thread_ts = thread_ts or ts
    is_oneshot = thread_ts is not None  # 스레드 내 원샷 호출

    # 세션 생성 (역할 정보 포함)
    session = session_manager.create(
        thread_ts=session_thread_ts,
        channel_id=channel,
        user_id=user_id,
        username=user_info["username"],
        role=user_info["role"]
    )

    # 멘션 텍스트에서 질문 추출 (멘션 제거)
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    if not clean_text:
        logger.info(f"빈 질문 - 세션만 생성됨: thread_ts={session_thread_ts}")
        return

    # 채널 컨텍스트 가져오기
    context = get_channel_history(client, channel, limit=20)

    # 프롬프트 구성
    prompt = f"""아래는 Slack 채널의 최근 대화입니다:

{context}

사용자의 질문: {clean_text}

위 컨텍스트를 참고하여 질문에 답변해주세요."""

    # Claude 실행 (스레드 락으로 동시 실행 방지)
    _run_claude_in_session(session, prompt, ts, channel, say, client)


def _run_claude_in_session(session, prompt: str, msg_ts: str, channel: str, say, client, role: str = None):
    """세션 내에서 Claude Code 실행 (공통 로직)

    Args:
        session: Session 객체
        prompt: Claude에 전달할 프롬프트
        msg_ts: 원본 메시지 타임스탬프 (이모지 추가용)
        channel: Slack 채널 ID
        say: Slack say 함수
        client: Slack client
        role: 실행할 역할 (None이면 session.role 사용)
    """
    thread_ts = session.thread_ts
    effective_role = role or session.role

    # 스레드별 락으로 동시 실행 방지
    lock = get_session_lock(thread_ts)
    if not lock.acquire(blocking=False):
        say(text="이전 요청을 처리 중이에요. 잠시 후 다시 시도해주세요.", thread_ts=thread_ts)
        return

    # 마지막 메시지 ts 추적 (최종 답변으로 교체할 대상)
    last_msg_ts = None

    try:
        # 작업 중 이모지
        try:
            client.reactions_add(channel=channel, timestamp=msg_ts, name="eyes")
        except Exception:
            pass

        # 초기 "생각합니다..." 메시지
        if effective_role == "admin":
            initial_text = "소영이 생각합니다..."
        else:
            initial_text = "소영이 조회 전용 모드로 생각합니다..."

        initial_msg = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=initial_text
        )
        last_msg_ts = initial_msg["ts"]

        # 스트리밍 콜백 - 새 메시지로 사고 과정 추가
        async def on_progress(current_text: str):
            nonlocal last_msg_ts
            try:
                display_text = current_text
                if len(display_text) > 3800:
                    display_text = "...\n" + display_text[-3800:]
                # 새 메시지로 사고 과정 추가
                new_msg = client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"```\n{display_text}\n```"
                )
                last_msg_ts = new_msg["ts"]
            except Exception as e:
                logger.warning(f"사고 과정 메시지 전송 실패: {e}")

        # 역할에 맞는 runner 생성
        runner = get_runner_for_role(effective_role)
        logger.info(f"Claude 실행: thread={thread_ts}, role={effective_role}")

        # Claude Code 실행
        try:
            result = asyncio.run(runner.run(
                prompt=prompt,
                session_id=session.session_id,
                on_progress=on_progress
            ))

            # 세션 ID 업데이트
            if result.session_id and result.session_id != session.session_id:
                session_manager.update_session_id(thread_ts, result.session_id)

            # 메시지 카운트 증가
            session_manager.increment_message_count(thread_ts)

            if result.success:
                response = result.output or "(응답 없음)"
                # 마지막 메시지를 최종 답변으로 교체 (일반 텍스트)
                try:
                    if len(response) <= 3900:
                        client.chat_update(channel=channel, ts=last_msg_ts, text=response)
                    else:
                        client.chat_update(channel=channel, ts=last_msg_ts, text=f"(1/?) {response[:3900]}")
                        remaining = response[3900:]
                        send_long_message(say, remaining, thread_ts)
                except Exception:
                    send_long_message(say, response, thread_ts)

                # 첨부 파일 처리
                if result.attachments:
                    for file_path in result.attachments:
                        success, msg = upload_file_to_slack(client, channel, thread_ts, file_path)
                        if not success:
                            say(text=f"⚠️ {msg}", thread_ts=thread_ts)

                # 완료 이모지
                try:
                    client.reactions_add(channel=channel, timestamp=msg_ts, name="white_check_mark")
                except Exception:
                    pass

                # 재기동 마커 감지 (admin 역할만 허용)
                if effective_role == "admin":
                    if result.update_requested:
                        logger.info("업데이트 요청 마커 감지 - 프로세스 종료 (exit 42)")
                        say(text="코드가 업데이트되었습니다. 재시작합니다...", thread_ts=thread_ts)
                        os._exit(42)
                    elif result.restart_requested:
                        logger.info("재시작 요청 마커 감지 - 프로세스 종료 (exit 43)")
                        say(text="재시작합니다...", thread_ts=thread_ts)
                        os._exit(43)
            else:
                client.chat_update(
                    channel=channel,
                    ts=last_msg_ts,
                    text=f"오류가 발생했습니다: {result.error}"
                )
                try:
                    client.reactions_add(channel=channel, timestamp=msg_ts, name="x")
                except Exception:
                    pass

        except Exception as e:
            logger.exception(f"Claude 실행 오류: {e}")
            try:
                client.chat_update(
                    channel=channel,
                    ts=last_msg_ts,
                    text=f"오류가 발생했습니다: {str(e)}"
                )
            except Exception:
                say(text=f"오류가 발생했습니다: {str(e)}", thread_ts=thread_ts)

        # 작업 중 이모지 제거
        try:
            client.reactions_remove(channel=channel, timestamp=msg_ts, name="eyes")
        except Exception:
            pass
    finally:
        lock.release()


@app.event("message")
def handle_message(event, say, client):
    """스레드 메시지 처리

    세션이 있는 스레드 내 일반 메시지를 처리합니다.
    (멘션 없이 스레드에 작성된 메시지)
    """
    # 봇 자신의 메시지는 무시
    if event.get("bot_id"):
        return

    # 스레드 메시지인 경우만 처리
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return

    # 멘션이 포함된 경우 handle_mention에서 처리 (중복 방지)
    text = event.get("text", "")
    if "<@" in text:
        return

    user_id = event["user"]
    channel = event["channel"]
    ts = event["ts"]

    # 세션 확인
    session = session_manager.get(thread_ts)
    if not session:
        # 세션이 없으면 무시
        return

    # 멘션 제거 (혹시 모를 경우 대비)
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    if not clean_text:
        return

    # 메시지 작성자의 역할 조회 (세션 생성자와 다를 수 있음)
    user_info = get_user_role(user_id, client)
    if not user_info:
        say(text="사용자 정보를 확인할 수 없습니다.", thread_ts=thread_ts)
        return

    logger.info(f"메시지 처리: thread_ts={thread_ts}, user={user_info['username']}, role={user_info['role']}, text={clean_text[:50]}")

    # 메시지 작성자 권한으로 실행
    _run_claude_in_session(session, clean_text, ts, channel, say, client, role=user_info["role"])


# 워크스페이스 루트 (첨부 파일 허용 범위)
WORKSPACE_ROOT = Path.cwd()


def upload_file_to_slack(client, channel: str, thread_ts: str, file_path: str) -> tuple[bool, str]:
    """파일을 슬랙에 첨부

    Args:
        client: Slack client
        channel: 채널 ID
        thread_ts: 스레드 타임스탬프
        file_path: 첨부할 파일 경로

    Returns:
        (success, message): 성공 여부와 메시지
    """
    # 경로 검증
    is_valid, error = validate_attach_path(file_path, WORKSPACE_ROOT)
    if not is_valid:
        logger.warning(f"파일 첨부 거부: {file_path} - {error}")
        return False, f"파일 첨부 거부: {error}"

    try:
        file_path_obj = Path(file_path).resolve()
        result = client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            file=str(file_path_obj),
            filename=file_path_obj.name,
            initial_comment=f"📎 `{file_path_obj.name}`"
        )
        logger.info(f"파일 첨부 성공: {file_path}")
        return True, "첨부 완료"
    except Exception as e:
        logger.error(f"파일 첨부 실패: {file_path} - {e}")
        return False, f"첨부 실패: {str(e)}"


def send_long_message(say, text: str, thread_ts: str | None, max_length: int = 3900):
    """긴 메시지를 분할해서 전송 (thread_ts가 None이면 채널에 응답)"""
    if len(text) <= max_length:
        say(text=f"{text}", thread_ts=thread_ts)
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
        prefix = f"({i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
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
                text="소영이가 시작되었습니다."
            )
            logger.info(f"시작 알림 전송: {Config.NOTIFY_CHANNEL}")
        except Exception as e:
            logger.error(f"시작 알림 실패: {e}")


if __name__ == "__main__":
    logger.info("SeoSoyoung 봇을 시작합니다...")
    logger.info(f"LOG_PATH: {Config.get_log_path()}")
    logger.info(f"ADMIN_USERS: {Config.ADMIN_USERS}")
    logger.info(f"ALLOWED_USERS: {Config.ALLOWED_USERS}")
    logger.info(f"DEBUG: {Config.DEBUG}")
    notify_startup()
    handler = SocketModeHandler(app, Config.SLACK_APP_TOKEN)
    handler.start()
