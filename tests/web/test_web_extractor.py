"""컨텐츠 추출기 테스트"""

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from seosoyoung.slackbot.web.extractor import ContentExtractor


class TestContentExtractorExtractBody:
    """본문 추출 테스트"""

    def test_extract_body_uses_trafilatura(self):
        """trafilatura로 본문 추출"""
        html = "<html><body><article>Main article content here.</article></body></html>"

        with patch("seosoyoung.slackbot.web.extractor.trafilatura_extract") as mock_traf, \
             patch("seosoyoung.slackbot.web.extractor.ArticleExtractor") as mock_bp:
            mock_traf.return_value = "Main article content here."
            mock_bp.return_value.get_content.return_value = "Short"

            extractor = ContentExtractor()
            result = extractor.extract_body(html)

            assert result == "Main article content here."

    def test_extract_body_uses_longer_result(self):
        """trafilatura와 boilerpy3 중 더 긴 결과 사용"""
        html = "<html><body>Test</body></html>"

        with patch("seosoyoung.slackbot.web.extractor.trafilatura_extract") as mock_traf, \
             patch("seosoyoung.slackbot.web.extractor.ArticleExtractor") as mock_bp:
            mock_traf.return_value = "Short text"
            mock_bp.return_value.get_content.return_value = "Much longer text from boilerpy3 extractor"

            extractor = ContentExtractor()
            result = extractor.extract_body(html)

            assert result == "Much longer text from boilerpy3 extractor"

    def test_extract_body_handles_none_trafilatura(self):
        """trafilatura가 None 반환 시 boilerpy3 사용"""
        html = "<html><body>Test</body></html>"

        with patch("seosoyoung.slackbot.web.extractor.trafilatura_extract") as mock_traf, \
             patch("seosoyoung.slackbot.web.extractor.ArticleExtractor") as mock_bp:
            mock_traf.return_value = None
            mock_bp.return_value.get_content.return_value = "Boilerpy3 result"

            extractor = ContentExtractor()
            result = extractor.extract_body(html)

            assert result == "Boilerpy3 result"

    def test_extract_body_handles_empty_results(self):
        """둘 다 빈 결과 시 빈 문자열 반환"""
        html = "<html><body></body></html>"

        with patch("seosoyoung.slackbot.web.extractor.trafilatura_extract") as mock_traf, \
             patch("seosoyoung.slackbot.web.extractor.ArticleExtractor") as mock_bp:
            mock_traf.return_value = ""
            mock_bp.return_value.get_content.return_value = ""

            extractor = ContentExtractor()
            result = extractor.extract_body(html)

            assert result == ""


class TestContentExtractorCleanHtml:
    """HTML 전처리 테스트"""

    def test_removes_script_tags(self):
        """script 태그 제거"""
        html = "<html><script>alert('test')</script><body>Content</body></html>"

        extractor = ContentExtractor()
        result = extractor.clean_html(html)

        assert "<script>" not in result
        assert "alert" not in result
        assert "Content" in result

    def test_removes_style_tags(self):
        """style 태그 제거"""
        html = "<html><style>.test{color:red}</style><body>Content</body></html>"

        extractor = ContentExtractor()
        result = extractor.clean_html(html)

        assert "<style>" not in result
        assert "color:red" not in result
        assert "Content" in result

    def test_truncates_long_html(self):
        """50K 문자 이상 시 자르기"""
        html = "<html><body>" + "x" * 60000 + "</body></html>"

        extractor = ContentExtractor()
        result = extractor.clean_html(html, max_length=50000)

        assert len(result) <= 50000


class TestContentExtractorExtractMetadataWithLLM:
    """LLM 기반 메타데이터 추출 테스트"""

    @pytest.mark.asyncio
    async def test_extracts_metadata_from_llm(self):
        """LLM으로 메타데이터 추출"""
        html = "<html><body><h1>Test Title</h1><p>By John Doe on 2024-01-15</p></body></html>"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "title": "Test Title",
            "published_date": "2024-01-15",
            "authors": ["John Doe"]
        }))]

        with patch("seosoyoung.slackbot.web.extractor.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response

            extractor = ContentExtractor(anthropic_api_key="test-key")
            result = await extractor.extract_metadata_with_llm(html)

            assert result["title"] == "Test Title"
            assert result["published_date"] == "2024-01-15"
            assert result["authors"] == ["John Doe"]

    @pytest.mark.asyncio
    async def test_returns_none_on_llm_failure(self):
        """LLM 실패 시 None 반환"""
        html = "<html><body>Test</body></html>"

        with patch("seosoyoung.slackbot.web.extractor.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.side_effect = Exception("API error")

            extractor = ContentExtractor(anthropic_api_key="test-key")
            result = await extractor.extract_metadata_with_llm(html)

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        """API 키 없이 호출 시 None 반환"""
        html = "<html><body>Test</body></html>"

        extractor = ContentExtractor(anthropic_api_key=None)
        result = await extractor.extract_metadata_with_llm(html)

        assert result is None


class TestContentExtractorExtractMetadataFallback:
    """폴백 메타데이터 추출 테스트"""

    def test_extracts_with_goose3(self):
        """goose3로 메타데이터 추출"""
        html = "<html><head><title>Test Title</title></head><body>Content</body></html>"

        with patch("seosoyoung.slackbot.web.extractor.Goose") as mock_goose, \
             patch("seosoyoung.slackbot.web.extractor.find_date") as mock_date:
            mock_article = MagicMock()
            mock_article.title = "Test Title"
            mock_article.authors = ["Jane Doe"]
            mock_article.publish_date = "2024-01-20"
            mock_goose.return_value.extract.return_value = mock_article
            mock_date.return_value = None

            extractor = ContentExtractor()
            result = extractor.extract_metadata_fallback(html)

            assert result["title"] == "Test Title"
            assert result["authors"] == ["Jane Doe"]
            assert result["published_date"] == "2024-01-20"

    def test_uses_htmldate_when_goose_date_missing(self):
        """goose3 날짜 없을 때 htmldate 사용"""
        html = "<html><body>Content published on 2024-02-10</body></html>"

        with patch("seosoyoung.slackbot.web.extractor.Goose") as mock_goose, \
             patch("seosoyoung.slackbot.web.extractor.find_date") as mock_date:
            mock_article = MagicMock()
            mock_article.title = "Test"
            mock_article.authors = []
            mock_article.publish_date = None
            mock_goose.return_value.extract.return_value = mock_article
            mock_date.return_value = "2024-02-10"

            extractor = ContentExtractor()
            result = extractor.extract_metadata_fallback(html)

            assert result["published_date"] == "2024-02-10"

    def test_handles_goose_exception(self):
        """goose3 예외 처리"""
        html = "<html><body>Test</body></html>"

        with patch("seosoyoung.slackbot.web.extractor.Goose") as mock_goose, \
             patch("seosoyoung.slackbot.web.extractor.find_date") as mock_date:
            mock_goose.return_value.extract.side_effect = Exception("Parse error")
            mock_date.return_value = "2024-03-01"

            extractor = ContentExtractor()
            result = extractor.extract_metadata_fallback(html)

            # 예외 발생해도 기본값 반환
            assert result["title"] == "Title not found"
            assert result["published_date"] == "2024-03-01"
