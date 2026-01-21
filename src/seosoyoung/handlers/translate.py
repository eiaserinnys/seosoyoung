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


def _format_response(user_name: str, translated: str, source_lang: Language, cost: float) -> str:
    """응답 메시지를 포맷팅합니다.

    Args:
        user_name: 원본 메시지 작성자 이름
        translated: 번역된 텍스트
        source_lang: 원본 언어
        cost: 예상 번역 비용 (USD)

    Returns:
        포맷팅된 응답 문자열
    """
    cost_line = f"`💸 예상 번역 비용: ${cost:.4f}`"

    if source_lang == Language.KOREAN:
        # 한국어 -> 영어: `Name said,` "번역"
        return f"`{user_name} said,` \"{translated}\"\n{cost_line}"
    else:
        # 영어 -> 한국어: `이름님이` "번역"`라고 하셨습니다.`
        return f"`{user_name}님이` \"{translated}\"`라고 하셨습니다.`\n{cost_line}"


def process_translate_message(event: dict, client) -> bool:
    """메시지를 번역 처리합니다.

    Args:
        event: 슬랙 메시지 이벤트
        client: 슬랙 클라이언트

    Returns:
        처리 여부 (True: 처리됨, False: 처리하지 않음)
    """
    # 봇 메시지 무시
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return False

    # 메시지 수정/삭제 이벤트 무시
    subtype = event.get("subtype")
    if subtype in ("message_changed", "message_deleted"):
        return False

    text = event.get("text", "").strip()
    if not text:
        return False

    channel = event.get("channel")
    user_id = event.get("user")
    thread_ts = event.get("thread_ts")  # 스레드면 부모 ts
    message_ts = event.get("ts")

    try:
        # 번역 시작 리액션
        client.reactions_add(
            channel=channel,
            timestamp=message_ts,
            name="hn-curious"
        )

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
        translated, cost = translate(text, source_lang, context_messages)

        # 사용자 이름 조회
        user_name = _get_user_display_name(client, user_id)

        # 응답 포맷
        response = _format_response(user_name, translated, source_lang, cost)

        # 응답 위치: 스레드면 스레드에, 아니면 채널에 직접
        reply_ts = thread_ts if thread_ts else message_ts

        client.chat_postMessage(
            channel=channel,
            text=response,
            thread_ts=reply_ts
        )

        # 번역 완료: 리액션 교체
        client.reactions_remove(
            channel=channel,
            timestamp=message_ts,
            name="hn-curious"
        )
        client.reactions_add(
            channel=channel,
            timestamp=message_ts,
            name="hn_deal_rainbow"
        )

        logger.info(f"번역 응답 완료: {user_name}")
        return True

    except Exception as e:
        logger.error(f"번역 실패: {e}", exc_info=True)
        # 실패 시 리액션 교체 (hn-curious -> hn-embarrass)
        try:
            client.reactions_remove(
                channel=channel,
                timestamp=message_ts,
                name="hn-curious"
            )
        except Exception:
            pass
        try:
            client.reactions_add(
                channel=channel,
                timestamp=message_ts,
                name="hn-embarrass"
            )
        except Exception:
            pass
        # 실패 이유를 스레드에 알림
        try:
            reply_ts = thread_ts if thread_ts else message_ts
            client.chat_postMessage(
                channel=channel,
                text=f"번역 실패: `{e}`",
                thread_ts=reply_ts
            )
        except Exception:
            pass
        return False


def register_translate_handler(app: App, dependencies: dict):
    """번역 핸들러를 앱에 등록합니다.

    Note: 이 함수는 더 이상 핸들러를 등록하지 않습니다.
    번역 처리는 message.py의 handle_message에서 process_translate_message를 호출합니다.
    """
    translate_channel = Config.TRANSLATE_CHANNEL
    if translate_channel:
        logger.info(f"번역 기능 활성화: 채널 {translate_channel}")
