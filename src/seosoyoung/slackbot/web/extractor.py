"""HTML에서 컨텐츠 및 메타데이터 추출"""

import json
import logging
from typing import Any

import anthropic
from bs4 import BeautifulSoup
from boilerpy3 import extractors
from goose3 import Goose
from htmldate import find_date
from trafilatura import extract as trafilatura_extract

from boilerpy3.extractors import ArticleExtractor

logger = logging.getLogger(__name__)

METADATA_EXTRACTION_PROMPT = """Extract article metadata from the following HTML.
Return a JSON object with these fields:
- title: The article title (string)
- published_date: Publication date in YYYY-MM-DD format if found, null otherwise
- authors: List of author names (array of strings)

HTML:
{html}

Return ONLY valid JSON, no other text."""


class ContentExtractor:
    """HTML에서 본문과 메타데이터를 추출하는 클래스"""

    def __init__(self, anthropic_api_key: str | None = None):
        """
        Args:
            anthropic_api_key: Anthropic API 키 (메타데이터 LLM 추출용)
        """
        self.anthropic_api_key = anthropic_api_key

    def extract_body(self, html: str) -> str:
        """HTML에서 본문 텍스트 추출

        trafilatura와 boilerpy3 중 더 긴 결과를 사용합니다.

        Args:
            html: 원본 HTML

        Returns:
            추출된 본문 텍스트
        """
        # trafilatura로 추출
        text_trafilatura = trafilatura_extract(html) or ""

        # boilerpy3로 추출
        try:
            text_boilerpy3 = ArticleExtractor().get_content(html) or ""
        except Exception as e:
            logger.warning(f"boilerpy3 extraction failed: {e}")
            text_boilerpy3 = ""

        # 더 긴 결과 사용
        if len(text_boilerpy3) > len(text_trafilatura):
            return text_boilerpy3
        return text_trafilatura

    def clean_html(self, html: str, max_length: int = 50000) -> str:
        """HTML 전처리 (script/style 제거, 길이 제한)

        Args:
            html: 원본 HTML
            max_length: 최대 길이 (기본 50K)

        Returns:
            정리된 HTML
        """
        soup = BeautifulSoup(html, "html.parser")

        # script, style, noscript, iframe 제거
        for element in soup(["script", "style", "noscript", "iframe"]):
            element.decompose()

        cleaned = str(soup)

        # 길이 제한
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
            logger.info(f"HTML truncated to {max_length} characters")

        return cleaned

    async def extract_metadata_with_llm(self, html: str) -> dict[str, Any] | None:
        """Claude Haiku로 메타데이터 추출

        Args:
            html: HTML 콘텐츠

        Returns:
            메타데이터 딕셔너리 (title, published_date, authors) 또는 None
        """
        if not self.anthropic_api_key:
            logger.warning("No Anthropic API key provided, skipping LLM extraction")
            return None

        try:
            cleaned_html = self.clean_html(html)
            prompt = METADATA_EXTRACTION_PROMPT.format(html=cleaned_html)

            client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text
            result = json.loads(result_text)

            logger.info(f"LLM extraction successful: title='{result.get('title', 'N/A')}'")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"LLM extraction failed: invalid JSON - {e}")
            return None
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return None

    def extract_metadata_fallback(self, html: str) -> dict[str, Any]:
        """goose3 + htmldate로 메타데이터 추출 (폴백)

        Args:
            html: HTML 콘텐츠

        Returns:
            메타데이터 딕셔너리 (title, published_date, authors)
        """
        g = Goose()

        try:
            article = g.extract(raw_html=html)
            title = article.title if article.title else "Title not found"
            authors = article.authors if article.authors else []
            published_date = article.publish_date
        except Exception as e:
            logger.error(f"goose3 extraction failed: {e}")
            title = "Title not found"
            authors = []
            published_date = None

        # goose3에서 날짜 못 찾으면 htmldate 사용
        if not published_date:
            try:
                published_date = find_date(html)
                if isinstance(published_date, list):
                    published_date = published_date[0] if published_date else None
            except Exception as e:
                logger.warning(f"htmldate extraction failed: {e}")
                published_date = None

        return {
            "title": title,
            "published_date": published_date,
            "authors": authors,
        }
