"""번역 핸들러

특정 채널의 메시지를 감지하여 자동 번역합니다.
"""

import logging
from slack_bolt import App

from seosoyoung.config import Config
from seosoyoung.translator import detect_language, translate, Language, GlossaryMatchResult

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


def _format_response(
    user_name: str,
    translated: str,
    source_lang: Language,
    cost: float,
    glossary_terms: list[tuple[str, str]] | None = None
) -> str:
    """응답 메시지를 포맷팅합니다.

    Args:
        user_name: 원본 메시지 작성자 이름
        translated: 번역된 텍스트
        source_lang: 원본 언어
        cost: 예상 번역 비용 (USD)
        glossary_terms: 참고한 용어 목록 [(원어, 번역어), ...]

    Returns:
        포맷팅된 응답 문자열
    """
    # 용어 라인 생성 (TRANSLATE_SHOW_GLOSSARY가 True이고 용어가 있는 경우에만)
    glossary_line = ""
    if Config.translate.show_glossary and glossary_terms:
        # 원어 (번역어) 형식으로 나열
        term_strs = [f"{src} ({tgt})" for src, tgt in glossary_terms]
        glossary_line = f"\n`📖 {', '.join(term_strs)}`"

    # 비용 라인 (TRANSLATE_SHOW_COST가 True인 경우에만)
    cost_line = f"\n`~💵${cost:.4f}`" if Config.translate.show_cost else ""

    if source_lang == Language.KOREAN:
        # 한국어 -> 영어
        return f"`{user_name} said,`\n\"{translated}\"{glossary_line}{cost_line}"
    else:
        # 영어 -> 한국어
        return f"`{user_name}님이`\n\"{translated}\"\n`라고 하셨습니다.`{glossary_line}{cost_line}"


def _send_debug_log(
    client,
    original_text: str,
    source_lang: Language,
    match_result: GlossaryMatchResult | None
) -> None:
    """디버그 로그를 지정된 슬랙 채널에 전송합니다.

    Args:
        client: Slack 클라이언트
        original_text: 원본 텍스트
        source_lang: 원본 언어
        match_result: 용어 매칭 결과
    """
    debug_channel = Config.translate.debug_channel
    if not debug_channel or not match_result:
        return

    try:
        debug_info = match_result.debug_info

        # 디버그 메시지 구성
        lines = [
            f"*🔍 번역 디버그 로그* ({source_lang.value} → {'en' if source_lang == Language.KOREAN else 'ko'})",
            f"```원문: {original_text[:100]}{'...' if len(original_text) > 100 else ''}```",
            "",
            f"*추출된 단어 ({len(match_result.extracted_words)}개):*",
            f"`{', '.join(match_result.extracted_words[:20])}{'...' if len(match_result.extracted_words) > 20 else ''}`",
            "",
        ]

        # 정확한 매칭
        exact_matches = debug_info.get("exact_matches", [])
        if exact_matches:
            lines.append(f"*✅ 정확한 매칭 ({len(exact_matches)}개):*")
            for match in exact_matches[:10]:
                lines.append(f"  • {match}")
            if len(exact_matches) > 10:
                lines.append(f"  ... 외 {len(exact_matches) - 10}개")
            lines.append("")

        # 부분 문자열 매칭
        substring_matches = debug_info.get("substring_matches", [])
        if substring_matches:
            lines.append(f"*📎 부분 매칭 ({len(substring_matches)}개):*")
            for match in substring_matches[:10]:
                lines.append(f"  • {match}")
            if len(substring_matches) > 10:
                lines.append(f"  ... 외 {len(substring_matches) - 10}개")
            lines.append("")

        # 퍼지 매칭
        fuzzy_matches = debug_info.get("fuzzy_matches", [])
        if fuzzy_matches:
            lines.append(f"*🔮 퍼지 매칭 ({len(fuzzy_matches)}개):*")
            for match in fuzzy_matches[:10]:
                lines.append(f"  • {match}")
            if len(fuzzy_matches) > 10:
                lines.append(f"  ... 외 {len(fuzzy_matches) - 10}개")
            lines.append("")

        # 최종 결과
        lines.append(f"*📖 최종 용어집 포함 ({len(match_result.matched_terms)}개):*")
        if match_result.matched_terms:
            for src, tgt in match_result.matched_terms[:10]:
                lines.append(f"  • {src} → {tgt}")
            if len(match_result.matched_terms) > 10:
                lines.append(f"  ... 외 {len(match_result.matched_terms) - 10}개")
        else:
            lines.append("  (없음)")

        client.chat_postMessage(
            channel=debug_channel,
            text="\n".join(lines)
        )

    except Exception as e:
        logger.warning(f"디버그 로그 전송 실패: {e}")


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
            Config.translate.context_count
        )

        # 번역
        translated, cost, glossary_terms, match_result = translate(text, source_lang, context_messages)

        # 디버그 로그 전송 (설정된 경우)
        _send_debug_log(client, text, source_lang, match_result)

        # 사용자 이름 조회
        user_name = _get_user_display_name(client, user_id)

        # 응답 포맷
        response = _format_response(user_name, translated, source_lang, cost, glossary_terms)

        # 응답 위치: 스레드면 스레드에, 채널이면 채널에 (스레드 열지 않음)
        if thread_ts:
            client.chat_postMessage(
                channel=channel,
                text=response,
                thread_ts=thread_ts
            )
        else:
            client.chat_postMessage(
                channel=channel,
                text=response
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
        logger.exception(f"번역 실패: {e}")
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
        # 실패 이유를 같은 위치에 알림 (스레드 열지 않음)
        try:
            if thread_ts:
                client.chat_postMessage(
                    channel=channel,
                    text=f"번역 실패: `{e}`",
                    thread_ts=thread_ts
                )
            else:
                client.chat_postMessage(
                    channel=channel,
                    text=f"번역 실패: `{e}`"
                )
        except Exception:
            pass
        return False


def register_translate_handler(app: App, dependencies: dict):
    """번역 핸들러를 앱에 등록합니다.

    Note: 이 함수는 더 이상 핸들러를 등록하지 않습니다.
    번역 처리는 message.py의 handle_message에서 process_translate_message를 호출합니다.
    """
    translate_channels = Config.translate.channels
    if translate_channels:
        logger.info(f"번역 기능 활성화: 채널 {translate_channels}")
