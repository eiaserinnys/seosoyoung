"""Jev-gated routing from new Slack mentions to the lore-search service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import json
import logging
import re
import threading
from pathlib import PurePosixPath
from typing import Any, Callable

import requests

from seosoyoung.slackbot.config import Config


logger = logging.getLogger(__name__)
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
REQUEST_TIMEOUT_SECONDS = 35
SEARCH_TIMEOUT_SECONDS = 100
INTENT_THRESHOLD = 0.7
MAX_RESULTS = 5
MAX_BLOCKS = 50
MAX_BLOCK_TEXT = 2800
LORE_SEARCH_SETTING_NAMES = (
    ("jev_api_key", "JEV_API_KEY"),
    ("lore_search_url", "LORE_SEARCH_URL"),
    ("lore_search_api_key", "LORE_SEARCH_API_KEY"),
)
LANGUAGES = {
    "ko": ("한국어", "한국어"),
    "en": ("영어", "English"),
    "ja": ("일본어", "日本語"),
    "zh": ("중국어", "中文"),
    "fr": ("프랑스어", "Français"),
    "de": ("독일어", "Deutsch"),
    "pt": ("포르투갈어", "Português"),
    "es": ("스페인어", "Español"),
    "ru": ("러시아어", "Русский"),
    "other": ("그 밖의 언어", "그 밖의 언어"),
}


def missing_lore_search_settings() -> list[str]:
    config = getattr(Config, "lore_search", None)
    missing = []
    for attribute, setting_name in LORE_SEARCH_SETTING_NAMES:
        value = getattr(config, attribute, None)
        if not isinstance(value, str) or not value.strip():
            missing.append(setting_name)
    return missing


def log_lore_search_routing_status() -> None:
    missing = missing_lore_search_settings()
    status = "enabled" if not missing else "disabled"
    logger.info(
        "Lore-search routing status=%s missing_settings=%s",
        status,
        ",".join(missing) or "none",
    )


def _post_jev(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    response = requests.post(
        JEV_URL,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Jev returned an invalid response")
    return body


def judge_lore_search(user_prompt: str, api_key: str) -> float:
    state = {
        "context": "엠버 앤 블레이드 게임의 로어(인물, 사건, 세계관, 설정, 대사)를 다루는 슬랙 봇에게 온 발화",
        "user_prompt": user_prompt,
    }
    payload = {
        "model": JEV_MODEL,
        "state": json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        "questions": {
            "lore_search": {
                "type": "noul",
                "instructions": "이 발화가 로어 정보나 기존 대사를 찾아 달라는 질의인가?",
                "criteria": {"true": "요청함", "false": "요청하지 않음"},
            }
        },
    }
    body = _post_jev(payload, api_key)
    answer = body.get("answers", {}).get("lore_search")
    score = answer.get("noul") if isinstance(answer, dict) and answer.get("type") == "noul" else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise ValueError("Jev returned no valid lore-search intent score")
    return float(score)


def judge_answer_language(user_prompt: str, api_key: str) -> tuple[float, str]:
    state = {
        "context": "엠버 앤 블레이드 게임의 로어(인물, 사건, 세계관, 설정, 대사)를 다루는 슬랙 봇에게 온 발화. 기본 답변 언어는 한국어",
        "user_prompt": user_prompt,
    }
    payload = {
        "model": JEV_MODEL,
        "state": json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        "questions": {
            "answer_language_requested": {
                "type": "noul",
                "instructions": "이 발화가 다른 언어로 답변할 것을 요구하고 있는가?",
                "criteria": {"true": "요구함", "false": "요구하지 않음"},
            },
            "answer_language": {
                "type": "choice",
                "instructions": "이 발화가 답변을 받고자 하는 언어",
                "criteria": {
                    "ko": "한국어", "en": "영어", "ja": "일본어", "zh": "중국어", "fr": "프랑스어",
                    "de": "독일어", "pt": "포르투갈어", "es": "스페인어", "ru": "러시아어",
                    "other": "그 밖의 언어",
                },
            },
        },
    }
    body = _post_jev(payload, api_key)
    answers = body.get("answers", {})
    requested = answers.get("answer_language_requested") if isinstance(answers, dict) else None
    choice_answer = answers.get("answer_language") if isinstance(answers, dict) else None
    score = requested.get("noul") if isinstance(requested, dict) and requested.get("type") == "noul" else None
    choice = choice_answer.get("choice") if isinstance(choice_answer, dict) and choice_answer.get("type") == "choice" else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise ValueError("Jev returned no valid answer-language score")
    if not isinstance(choice, str) or choice not in LANGUAGES:
        raise ValueError("Jev returned no valid answer-language choice")
    return float(score), choice


def _answer_language(score: float, choice: str) -> str:
    return "ko" if score < INTENT_THRESHOLD or choice == "ko" else choice


def search_lore(
    query: str,
    base_url: str,
    api_key: str,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/search",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/x-ndjson"},
        json={"query": query},
        timeout=SEARCH_TIMEOUT_SECONDS,
        stream=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type == "application/x-ndjson":
        result = None
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            event = json.loads(line)
            if not isinstance(event, dict):
                continue
            if event.get("type") == "progress" and isinstance(event.get("message"), str):
                if on_progress is not None:
                    on_progress(event["message"])
            elif event.get("type") == "result":
                result = {key: value for key, value in event.items() if key != "type"}
            elif event.get("type") == "error":
                raise RuntimeError("lore-search stream failed")
        body = result
    else:
        body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        raise ValueError("lore-search returned an invalid response")
    return body


def _slack_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _display_text(item: dict[str, Any], language: str) -> tuple[str, bool]:
    translations = item.get("translations")
    if isinstance(translations, dict):
        translated = translations.get(language) if language in LANGUAGES and language != "other" else None
        if isinstance(translated, str) and translated.strip():
            return translated.strip(), True
        korean = translations.get("ko")
        if isinstance(korean, str) and korean.strip():
            return korean.strip(), False
    text = item.get("text") or item.get("excerpt") or ""
    return str(text), False


def _dialogue_elements(text: str) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    skip_english_continuation = False
    for line in text.splitlines():
        match = re.match(r"^([^:\n]{1,80}):(?: ?)(.*)$", line)
        if match:
            if match.group(1).endswith(" [en]"):
                skip_english_continuation = True
                continue
            skip_english_continuation = False
        elif skip_english_continuation:
            continue
        if match:
            if elements:
                elements.append({"type": "text", "text": "\n"})
            elements.append({"type": "text", "text": match.group(1), "style": {"bold": True}})
            elements.append({"type": "text", "text": ": " + match.group(2)})
        else:
            continuation = line.strip()
            if not continuation:
                continue
            if elements:
                elements.append({"type": "text", "text": " "})
            elements.append({"type": "text", "text": continuation})
    return elements


def _rich_text_blocks(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_length = 0
    for element in elements:
        text = element["text"]
        while text:
            room = MAX_BLOCK_TEXT - current_length
            if room == 0:
                chunks.append(current)
                current = []
                current_length = 0
                room = MAX_BLOCK_TEXT
            fragment, text = text[:room], text[room:]
            current.append({**element, "text": fragment})
            current_length += len(fragment)
            if text:
                chunks.append(current)
                current = []
                current_length = 0
    if current:
        chunks.append(current)
    return [
        {"type": "rich_text", "elements": [{"type": "rich_text_quote", "elements": chunk}]}
        for chunk in chunks
    ]


def _split_section_text(text: str) -> list[str]:
    formatted = re.sub(r"^###\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    return [formatted[index:index + MAX_BLOCK_TEXT] for index in range(0, len(formatted), MAX_BLOCK_TEXT)]


def _is_internal_dialogue_title(title: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+(?:\s*·\s*[A-Za-z0-9_-]+)*", title))


def _dialogue_title(item: dict[str, Any], title: str) -> str:
    if not _is_internal_dialogue_title(title):
        return title or "대사"
    speakers = item.get("participants")
    names = [str(name).strip() for name in speakers if str(name).strip()] if isinstance(speakers, list) else []
    return " ↔ ".join(dict.fromkeys(names)) or "대사"


def _strip_markdown_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def _body_blocks(item: dict[str, Any], text: str) -> list[dict[str, Any]]:
    text = _strip_markdown_links(text)
    if item.get("source_type") == "shay":
        return _rich_text_blocks(_dialogue_elements(text))
    safe_text = _slack_text(text)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
        for chunk in _split_section_text(safe_text)
    ]


def build_search_blocks(body: dict[str, Any], language: str = "ko") -> list[dict[str, Any]]:
    results = [item for item in body.get("results", []) if isinstance(item, dict)][:MAX_RESULTS]
    normalized_language = language if language in LANGUAGES else "other"
    fallback_count = sum(
        1 for item in results
        if normalized_language != "ko" and not _display_text(item, normalized_language)[1]
    )
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "📜 로어 검색 결과"}},
    ]
    summary = f"질의 「{_slack_text(body.get('query'))}」 · 적중 {len(results)}건"
    if normalized_language == "other" and results:
        summary += " · 요청하신 언어의 번역이 없어 한국어로 보여 드립니다"
    elif fallback_count == len(results) and fallback_count:
        summary += f" · 요청하신 {LANGUAGES[normalized_language][0]} 번역이 없어 한국어로 보여 드립니다"
    elif fallback_count:
        summary += f" · 일부 결과는 {LANGUAGES[normalized_language][0]} 번역이 없어 한국어로 보여 드립니다"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": summary}]})

    search_url = body.get("search_url")
    has_button = isinstance(search_url, str) and bool(search_url)
    for index, item in enumerate(results, start=1):
        is_dialogue = item.get("source_type") == "shay"
        title = str(item.get("title") or "")
        displayed_title = _dialogue_title(item, title) if is_dialogue else (title or "제목 없음")
        blocks.extend([
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{index}. {_slack_text(displayed_title)}*"}},
        ])
        meta = ["대사" if is_dialogue else "설정 문서" if item.get("source_type") == "lore" else "자료"]
        path = str(item.get("path") or "")
        if is_dialogue and path:
            filename = PurePosixPath(path).stem
            section = title.rsplit("·", 1)[-1].strip() if "·" in title else ""
            location = f"{filename} ({section})" if section else filename
            meta.append(_slack_text(location))
        elif path:
            meta.append(_slack_text(path))
        relevance = item.get("relevance")
        if isinstance(relevance, (int, float)) and not isinstance(relevance, bool):
            meta.append(f"관련도 {relevance:.2f}")
        display_text, translated = _display_text(item, normalized_language)
        if translated and normalized_language != "ko":
            meta.append(LANGUAGES[normalized_language][1])
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(meta)}]})

        result_body = _body_blocks(item, display_text)
        results_after = len(results) - index
        reserve = results_after * 4 + (1 if has_button else 0)
        available = max(1, MAX_BLOCKS - len(blocks) - reserve)
        if len(result_body) > available:
            marker = "… 전체는 검색 사이트에서"
            result_body = result_body[:available]
            last = result_body[-1]
            if last["type"] == "section":
                value = last["text"]["text"]
                last["text"]["text"] = value[:max(0, MAX_BLOCK_TEXT - len(marker))] + marker
            else:
                quote = last["elements"][0]
                quote["elements"].append({"type": "text", "text": marker})
        blocks.extend(result_body)

    if not results:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "검색 결과가 없습니다."}})
    if has_button:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "검색 사이트에서 보기"},
                "url": search_url,
                "action_id": "open_lore_search",
            }],
        })
    return blocks[:MAX_BLOCKS]


def try_handle_lore_search(query: str, say, *, client, channel: str, thread_ts: str) -> bool:
    if missing_lore_search_settings():
        return False

    config = Config.lore_search
    jev_api_key = config.jev_api_key
    search_url = config.lore_search_url
    search_api_key = config.lore_search_api_key
    try:
        score = judge_lore_search(query, jev_api_key)
    except Exception as error:
        logger.warning("Jev lore-search routing failed exception_type=%s", type(error).__name__)
        return False
    decision = "search" if score >= INTENT_THRESHOLD else "general"
    logger.info(
        "Jev lore-search intent score=%s threshold=%.1f decision=%s",
        score,
        INTENT_THRESHOLD,
        decision,
    )
    if score < INTENT_THRESHOLD:
        return False

    placeholder = say(text="🔎 로어를 찾고 있습니다", thread_ts=thread_ts)
    progress_lock = threading.Lock()
    last_progress_message = None

    def update_progress(message: str) -> None:
        nonlocal last_progress_message
        with progress_lock:
            if message == last_progress_message:
                return
            last_progress_message = message
        try:
            client.chat_update(
                channel=channel,
                ts=placeholder["ts"],
                text=f"🔎 로어를 찾고 있습니다 · {message}",
            )
        except Exception as error:
            logger.warning("Lore-search progress update failed exception_type=%s", type(error).__name__)

    with ThreadPoolExecutor(max_workers=1) as language_executor:
        language_future = language_executor.submit(judge_answer_language, query, jev_api_key)
        try:
            result = search_lore(query, search_url, search_api_key, on_progress=update_progress)
        except Exception as error:
            logger.warning("Lore-search request failed exception_type=%s", type(error).__name__)
            try:
                client.chat_delete(channel=channel, ts=placeholder["ts"])
            except Exception as cleanup_error:
                logger.warning(
                    "Lore-search placeholder cleanup failed exception_type=%s",
                    type(cleanup_error).__name__,
                )
            return False

        try:
            language_score, language_choice = language_future.result()
            answer_language = _answer_language(language_score, language_choice)
            logger.info(
                "Jev lore-search answer language requested_score=%s choice=%s decision=%s",
                language_score,
                language_choice,
                answer_language,
            )
        except Exception as error:
            logger.warning("Jev answer-language judgement failed exception_type=%s", type(error).__name__)
            answer_language = "ko"

    blocks = build_search_blocks(result, answer_language)
    result_count = min(len(result["results"]), MAX_RESULTS)
    text = f"로어 검색 결과 {result_count}건" if result_count else "로어 검색 결과가 없습니다."
    client.chat_update(channel=channel, ts=placeholder["ts"], text=text, blocks=blocks)
    return True
