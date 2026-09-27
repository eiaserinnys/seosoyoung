"""Jev-gated routing from new Slack mentions to the lore-search service."""

from __future__ import annotations

import html
import json
import logging
from typing import Any

import requests

from seosoyoung.slackbot.config import Config


logger = logging.getLogger(__name__)
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
REQUEST_TIMEOUT_SECONDS = 35
SEARCH_TIMEOUT_SECONDS = 100
INTENT_THRESHOLD = 0.7
MAX_RESULTS = 5
MAX_EXCERPT_LENGTH = 240
LORE_SEARCH_SETTING_NAMES = (
    ("jev_api_key", "JEV_API_KEY"),
    ("lore_search_url", "LORE_SEARCH_URL"),
    ("lore_search_api_key", "LORE_SEARCH_API_KEY"),
)


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
    response = requests.post(
        JEV_URL,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    answer = body.get("answers", {}).get("lore_search") if isinstance(body, dict) else None
    score = answer.get("noul") if isinstance(answer, dict) and answer.get("type") == "noul" else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise ValueError("Jev returned no valid lore-search intent score")
    return float(score)


def search_lore(query: str, base_url: str, api_key: str) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/search",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        json={"query": query},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        raise ValueError("lore-search returned an invalid response")
    return body


def _slack_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def build_search_blocks(body: dict[str, Any]) -> list[dict[str, Any]]:
    results = [item for item in body.get("results", []) if isinstance(item, dict)][:MAX_RESULTS]
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "로어 검색 결과"}},
    ]
    if results:
        for index, item in enumerate(results, start=1):
            title = _slack_text(item.get("title") or "제목 없음")
            source_type = item.get("source_type")
            source = {"shay": "대화", "lore": "로어"}.get(source_type, "자료")
            path = _slack_text(item.get("path"))
            excerpt = _slack_text(item.get("excerpt"))[:MAX_EXCERPT_LENGTH]
            lines = [f"*{index}. {title}* · {source}"]
            if path:
                lines.append(path)
            if excerpt:
                lines.append(excerpt)
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)[:2900]}})
    else:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "검색 결과가 없습니다."}})

    search_url = body.get("search_url")
    if isinstance(search_url, str) and search_url:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "검색 사이트에서 보기"},
                "url": search_url,
                "action_id": "open_lore_search",
            }],
        })
    return blocks


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

    placeholder = say(text=Config.bot.thinking_text, thread_ts=thread_ts)
    try:
        result = search_lore(query, search_url, search_api_key)
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

    blocks = build_search_blocks(result)
    result_count = min(len(result["results"]), MAX_RESULTS)
    text = f"로어 검색 결과 {result_count}건" if result_count else "로어 검색 결과가 없습니다."
    client.chat_update(channel=channel, ts=placeholder["ts"], text=text, blocks=blocks)
    return True
