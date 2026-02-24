"""웹 콘텐츠 추출 모듈"""

import logging
import os
from typing import Any

from .cache import WebCache
from .fetcher import HtmlFetcher
from .extractor import ContentExtractor

__all__ = [
    "WebCache",
    "HtmlFetcher",
    "ContentExtractor",
    "get_article",
    "format_article_for_prompt",
]

logger = logging.getLogger(__name__)


async def get_article(
    url: str,
    cache_dir: str | None = None,
    anthropic_api_key: str | None = None,
    ignore_cache: bool = False,
) -> dict[str, Any]:
    """URL에서 아티클 추출

    캐시 확인 → HTML 페칭 → 컨텐츠/메타데이터 추출 → 캐시 저장

    Args:
        url: 추출할 URL
        cache_dir: 캐시 디렉토리 (기본: .local/cache/web)
        anthropic_api_key: Anthropic API 키 (메타데이터 LLM 추출용)
        ignore_cache: True면 캐시 무시하고 새로 추출

    Returns:
        아티클 데이터 딕셔너리:
        - url: 원본 URL
        - title: 제목
        - text: 본문
        - published_date: 발행일 (YYYY-MM-DD 또는 None)
        - authors: 저자 목록
        - cache_hit: 캐시에서 로드했는지 여부
    """
    # 기본 캐시 디렉토리
    if cache_dir is None:
        from seosoyoung.config import Config
        cache_dir = Config.get_web_cache_path()

    # API 키 (계정 과금 모드 - RECALL_API_KEY 사용)
    if anthropic_api_key is None:
        anthropic_api_key = os.getenv("RECALL_API_KEY")

    cache = WebCache(cache_dir)

    # 캐시 확인
    if not ignore_cache and cache.exists(url):
        logger.info(f"Cache hit for {url}")
        data = cache.load(url)
        data["cache_hit"] = True
        return data

    # HTML 페칭
    logger.info(f"Fetching {url}")
    fetcher = HtmlFetcher()
    html = await fetcher.fetch(url)

    # 컨텐츠 추출
    extractor = ContentExtractor(anthropic_api_key=anthropic_api_key)
    body = extractor.extract_body(html)

    # 메타데이터 추출 (LLM 우선, 실패 시 폴백)
    metadata = await extractor.extract_metadata_with_llm(html)
    if metadata is None or not metadata.get("title"):
        logger.info("LLM extraction failed, using fallback")
        metadata = extractor.extract_metadata_fallback(html)

    # 결과 조합
    data = {
        "url": url,
        "title": metadata.get("title", "Title not found"),
        "text": body or "No content extracted",
        "published_date": metadata.get("published_date"),
        "authors": metadata.get("authors", []),
    }

    # 캐시 저장
    cache.save(url, data)
    logger.info(f"Cached article: {data['title']}")

    data["cache_hit"] = False
    return data


def format_article_for_prompt(
    article: dict[str, Any],
    max_body_length: int = 50000,
) -> str:
    """아티클 데이터를 프롬프트용 문자열로 포맷

    Args:
        article: get_article()의 반환값
        max_body_length: 본문 최대 길이

    Returns:
        포맷된 문자열
    """
    lines = []

    # 제목
    lines.append(f"# {article.get('title', 'Untitled')}")
    lines.append("")

    # 메타데이터
    meta_parts = []
    if article.get("published_date"):
        meta_parts.append(f"Published: {article['published_date']}")
    if article.get("authors"):
        authors_str = ", ".join(article["authors"])
        meta_parts.append(f"Authors: {authors_str}")
    if article.get("url"):
        meta_parts.append(f"URL: {article['url']}")

    if meta_parts:
        lines.append(" | ".join(meta_parts))
        lines.append("")

    # 본문
    text = article.get("text", "")
    if len(text) > max_body_length:
        text = text[:max_body_length] + "\n\n[... content truncated ...]"
    lines.append(text)

    return "\n".join(lines)
