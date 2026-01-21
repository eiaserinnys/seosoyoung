"""@seosoyoung 멘션 핸들러"""

import re
import logging
from pathlib import Path

from seosoyoung.config import Config
from seosoyoung.restart import RestartType

logger = logging.getLogger(__name__)


def extract_command(text: str) -> str:
    """멘션에서 명령어 추출"""
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


def register_mention_handlers(app, dependencies: dict):
    """멘션 핸들러 등록

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 의존성 딕셔너리
    """
    session_manager = dependencies["session_manager"]
    restart_manager = dependencies["restart_manager"]
    get_running_session_count = dependencies["get_running_session_count"]
    run_claude_in_session = dependencies["run_claude_in_session"]
    check_permission = dependencies["check_permission"]
    get_user_role = dependencies["get_user_role"]
    send_restart_confirmation = dependencies["send_restart_confirmation"]

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
        thread_ts = event.get("thread_ts")

        logger.info(f"멘션 수신: user={user_id}, channel={channel}, text={text[:50]}")

        # 스레드에서 멘션된 경우
        if thread_ts:
            if session_manager.exists(thread_ts):
                logger.debug("스레드에서 멘션됨 (세션 있음) - handle_message에서 처리")
                return
            logger.debug("스레드에서 멘션됨 (세션 없음) - 원샷 답변")

        command = extract_command(text)
        logger.info(f"명령어 처리: command={command}")

        # 재시작 대기 중이면 안내 메시지 (관리자 명령어 제외)
        if restart_manager.is_pending and command not in ["help", "status", "update", "restart"]:
            say(
                text="재시작을 대기하는 중입니다.\n재시작이 완료되면 다시 대화를 요청해주세요.",
                thread_ts=ts
            )
            return

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
            sdk_mode = "SDK" if Config.CLAUDE_USE_SDK else "CLI"
            say(
                text=(
                    f"📊 *상태*\n"
                    f"• 작업 폴더: `{Path.cwd()}`\n"
                    f"• 관리자: {', '.join(Config.ADMIN_USERS)}\n"
                    f"• 활성 세션: {session_manager.count()}개\n"
                    f"• 클로드 모드: {sdk_mode}\n"
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

            restart_type = RestartType.UPDATE if command == "update" else RestartType.RESTART

            # 실행 중인 세션이 있으면 확인 프로세스
            running_count = get_running_session_count()
            if running_count > 0:
                send_restart_confirmation(
                    client=client,
                    channel=Config.TRELLO_NOTIFY_CHANNEL,
                    restart_type=restart_type,
                    running_count=running_count,
                    user_id=user_id,
                    original_thread_ts=ts
                )
                return

            # 실행 중인 세션이 없으면 즉시 재시작
            type_name = "업데이트" if command == "update" else "재시작"
            logger.info(f"{type_name} 요청 - 프로세스 종료")
            restart_manager.force_restart(restart_type)
            return

        # 일반 질문: 세션 생성 + Claude 실행
        user_info = get_user_role(user_id, client)
        if not user_info:
            say(text="사용자 정보를 확인할 수 없습니다.", thread_ts=thread_ts or ts)
            return

        # 세션 생성 위치 결정
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
        run_claude_in_session(session, prompt, ts, channel, say, client)
