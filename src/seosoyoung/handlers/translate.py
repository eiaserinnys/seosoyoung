"""번역 핸들러

특정 채널의 메시지를 감지하여 자동 번역합니다.
"""

import logging
from slack_bolt import App

from seosoyoung.config import Config
from seosoyoung.translator import detect_language, translate, Language

logger = logging.getLogger(__name__)


def _get_user_display_name(client, user_id: str) -> str:
    """사용자의 표시 이름을 가져옵니다."""
    try:
        result = client.users_info(user=user_id)
        user = result.get("user", {})
        profile = user.get("profile", {})
        return (
            profile.get("display_name") or
            profile.get("real_name") or
            user.get("name", user_id)
        )
    except Exception as e:
        logger.warning(f"사용자 정보 조회 실패: {user_id}, {e}")
        return user_id


def _get_context_messages(client, channel: str, thread_ts: str | None, limit: int) -> list[dict]:
    """이전 메시지들을 컨텍스트로 가져옵니다.

    Args:
        client: Slack 클라이언트
        channel: 채널 ID
        thread_ts: 스레드 타임스탬프 (없으면 채널 메시지)
        limit: 가져올 메시지 수

    Returns:
        [{"user": "이름", "text": "내용"}, ...] 형태의 리스트 (시간순)
    """
    try:
        if thread_ts:
            result = client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                limit=limit + 1  # 현재 메시지 포함 가능성
            )
        else:
            result = client.conversations_history(
                channel=channel,
                limit=limit + 1
            )

        messages = result.get("messages", [])

        # 최신순 -> 시간순 정렬 (conversations_history는 최신순)
        if not thread_ts:
            messages = list(reversed(messages))

        context = []
        for msg in messages[-limit:]:
            user_id = msg.get("user", "unknown")
            text = msg.get("text", "")
            if text:
                user_name = _get_user_display_name(client, user_id)
                context.append({"user": user_name, "text": text})

        return context

    except Exception as e:
        logger.warning(f"컨텍스트 메시지 조회 실패: {e}")
        return []


def _format_response(user_name: str, translated: str, source_lang: Language) -> str:
    """응답 메시지를 포맷팅합니다.

    Args:
        user_name: 원본 메시지 작성자 이름
        translated: 번역된 텍스트
        source_lang: 원본 언어

    Returns:
        포맷팅된 응답 문자열
    """
    if source_lang == Language.KOREAN:
        # 한국어 -> 영어: "(이름) told that\n> 번역"
        return f"{user_name} told that\n> {translated}"
    else:
        # 영어 -> 한국어: "(이름)님이\n> 번역\n...라고 말씀하셨습니다."
        return f"{user_name}님이\n> {translated}\n...라고 말씀하셨습니다."


def register_translate_handler(app: App, dependencies: dict):
    """번역 핸들러를 앱에 등록합니다.

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 핸들러 의존성 (현재 미사용)
    """
    translate_channel = Config.TRANSLATE_CHANNEL
    if not translate_channel:
        logger.info("TRANSLATE_CHANNEL이 설정되지 않아 번역 핸들러를 등록하지 않습니다.")
        return

    logger.info(f"번역 핸들러 등록: 채널 {translate_channel}")

    @app.event("message")
    def handle_translate_message(event, client, context, say):
        """메시지 이벤트 핸들러"""
        # 채널 확인
        channel = event.get("channel")
        if channel != translate_channel:
            return

        # 봇 메시지 무시
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        # 메시지 수정/삭제 이벤트 무시
        subtype = event.get("subtype")
        if subtype in ("message_changed", "message_deleted"):
            return

        text = event.get("text", "").strip()
        if not text:
            return

        user_id = event.get("user")
        thread_ts = event.get("thread_ts")  # 스레드면 부모 ts
        message_ts = event.get("ts")

        try:
            # 언어 감지
            source_lang = detect_language(text)
            logger.info(f"번역 요청: {source_lang.value} -> {text[:30]}...")

            # 컨텍스트 메시지 수집
            context_messages = _get_context_messages(
                client,
                channel,
                thread_ts,
                Config.TRANSLATE_CONTEXT_COUNT
            )

            # 번역
            translated = translate(text, source_lang, context_messages)

            # 사용자 이름 조회
            user_name = _get_user_display_name(client, user_id)

            # 응답 포맷
            response = _format_response(user_name, translated, source_lang)

            # 응답 위치: 스레드면 스레드에, 아니면 채널에 직접
            reply_ts = thread_ts if thread_ts else message_ts

            client.chat_postMessage(
                channel=channel,
                text=response,
                thread_ts=reply_ts
            )

            logger.info(f"번역 응답 완료: {user_name}")

        except Exception as e:
            logger.error(f"번역 실패: {e}", exc_info=True)
