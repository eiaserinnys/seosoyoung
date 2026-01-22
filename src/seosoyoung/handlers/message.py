"""스레드 메시지 핸들러"""

import asyncio
import re
import logging

from seosoyoung.config import Config
from seosoyoung.handlers.translate import process_translate_message
from seosoyoung.slack import download_files_from_event, build_file_context

logger = logging.getLogger(__name__)


def register_message_handlers(app, dependencies: dict):
    """메시지 핸들러 등록

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 의존성 딕셔너리
    """
    session_manager = dependencies["session_manager"]
    restart_manager = dependencies["restart_manager"]
    run_claude_in_session = dependencies["run_claude_in_session"]
    get_user_role = dependencies["get_user_role"]

    @app.event("message")
    def handle_message(event, say, client):
        """스레드 메시지 처리

        세션이 있는 스레드 내 일반 메시지를 처리합니다.
        (멘션 없이 스레드에 작성된 메시지)
        """
        # 봇 자신의 메시지는 무시
        if event.get("bot_id"):
            return

        channel = event.get("channel")
        text = event.get("text", "")

        # 번역 채널인 경우: 멘션이 없으면 번역, 멘션이 있으면 기존 로직 (handle_mention에서 처리)
        if channel in Config.TRANSLATE_CHANNELS:
            if "<@" not in text:
                process_translate_message(event, client)
            return

        # 스레드 메시지인 경우만 처리
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        # 멘션이 포함된 경우 handle_mention에서 처리 (중복 방지)
        if "<@" in text:
            return

        user_id = event["user"]
        channel = event["channel"]
        ts = event["ts"]

        # 세션 확인
        session = session_manager.get(thread_ts)
        if not session:
            return

        # 재시작 대기 중이면 안내 메시지
        if restart_manager.is_pending:
            say(
                text="재시작을 대기하는 중입니다.\n재시작이 완료되면 다시 대화를 요청해주세요.",
                thread_ts=thread_ts
            )
            return

        # 멘션 제거 (혹시 모를 경우 대비)
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        # 첨부 파일 처리
        file_context = ""
        if event.get("files"):
            try:
                downloaded_files = asyncio.get_event_loop().run_until_complete(
                    download_files_from_event(event, thread_ts)
                )
                if downloaded_files:
                    file_context = build_file_context(downloaded_files)
                    logger.info(f"파일 {len(downloaded_files)}개 다운로드 완료")
            except Exception as e:
                logger.error(f"파일 다운로드 실패: {e}")

        if not clean_text and not file_context:
            return

        # 메시지 작성자의 역할 조회 (세션 생성자와 다를 수 있음)
        user_info = get_user_role(user_id, client)
        if not user_info:
            say(text="사용자 정보를 확인할 수 없습니다.", thread_ts=thread_ts)
            return

        # 프롬프트 구성
        prompt_parts = []
        if clean_text:
            prompt_parts.append(clean_text)
        if file_context:
            prompt_parts.append(file_context)
        prompt = "\n".join(prompt_parts)

        logger.info(
            f"메시지 처리: thread_ts={thread_ts}, "
            f"user={user_info['username']}, role={user_info['role']}, "
            f"text={clean_text[:50] if clean_text else '(파일 첨부)'}"
        )

        # 메시지 작성자 권한으로 실행
        run_claude_in_session(session, prompt, ts, channel, say, client, role=user_info["role"])

    @app.event("reaction_added")
    def handle_reaction(event, client):
        """이모지 리액션 처리"""
        # TODO: 리액션 기반 동작 구현
        pass
