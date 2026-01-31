"""웹 콘텐츠 추출 통합 테스트"""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from seosoyoung.web import get_article


class TestGetArticle:
    """통합 API get_article 테스트"""

    @pytest.mark.asyncio
    async def test_returns_cached_data(self, tmp_path):
        """캐시된 데이터가 있으면 캐시에서 반환"""
        cached_data = {
            "url": "https://example.com/article",
            "title": "Cached Title",
            "text": "Cached content",
            "published_date": "2024-01-01",
            "authors": ["Cached Author"],
        }

        with patch("seosoyoung.web.WebCache") as mock_cache_cls:
            mock_cache = MagicMock()
            mock_cache.exists.return_value = True
            mock_cache.load.return_value = cached_data
            mock_cache_cls.return_value = mock_cache

            result = await get_article("https://example.com/article")

            assert result["title"] == "Cached Title"
            assert result["cache_hit"] is True
            mock_cache.load.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetches_and_extracts_when_not_cached(self, tmp_path):
        """캐시 없으면 페칭 후 추출"""
        with patch("seosoyoung.web.WebCache") as mock_cache_cls, \
             patch("seosoyoung.web.HtmlFetcher") as mock_fetcher_cls, \
             patch("seosoyoung.web.ContentExtractor") as mock_extractor_cls:

            # 캐시 미스
            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_cache_cls.return_value = mock_cache

            # 페칭
            mock_fetcher = MagicMock()
            mock_fetcher.fetch = AsyncMock(return_value="<html><body>Content</body></html>")
            mock_fetcher_cls.return_value = mock_fetcher

            # 추출
            mock_extractor = MagicMock()
            mock_extractor.extract_body.return_value = "Extracted body"
            mock_extractor.extract_metadata_with_llm = AsyncMock(return_value={
                "title": "New Title",
                "published_date": "2024-02-01",
                "authors": ["New Author"],
            })
            mock_extractor_cls.return_value = mock_extractor

            result = await get_article(
                "https://example.com/new",
                cache_dir=str(tmp_path),
            )

            assert result["title"] == "New Title"
            assert result["text"] == "Extracted body"
            assert result["cache_hit"] is False
            # 캐시에 저장
            mock_cache.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_fallback_when_llm_fails(self, tmp_path):
        """LLM 실패 시 폴백 사용"""
        with patch("seosoyoung.web.WebCache") as mock_cache_cls, \
             patch("seosoyoung.web.HtmlFetcher") as mock_fetcher_cls, \
             patch("seosoyoung.web.ContentExtractor") as mock_extractor_cls:

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_cache_cls.return_value = mock_cache

            mock_fetcher = MagicMock()
            mock_fetcher.fetch = AsyncMock(return_value="<html><body>Content</body></html>")
            mock_fetcher_cls.return_value = mock_fetcher

            mock_extractor = MagicMock()
            mock_extractor.extract_body.return_value = "Body text"
            mock_extractor.extract_metadata_with_llm = AsyncMock(return_value=None)  # LLM 실패
            mock_extractor.extract_metadata_fallback.return_value = {
                "title": "Fallback Title",
                "published_date": "2024-03-01",
                "authors": ["Fallback Author"],
            }
            mock_extractor_cls.return_value = mock_extractor

            result = await get_article(
                "https://example.com/fallback",
                cache_dir=str(tmp_path),
            )

            assert result["title"] == "Fallback Title"
            mock_extractor.extract_metadata_fallback.assert_called_once()

    @pytest.mark.asyncio
    async def test_ignore_cache_forces_fetch(self, tmp_path):
        """ignore_cache=True면 캐시 무시하고 페칭"""
        with patch("seosoyoung.web.WebCache") as mock_cache_cls, \
             patch("seosoyoung.web.HtmlFetcher") as mock_fetcher_cls, \
             patch("seosoyoung.web.ContentExtractor") as mock_extractor_cls:

            mock_cache = MagicMock()
            mock_cache.exists.return_value = True  # 캐시 있음
            mock_cache.load.return_value = {"title": "Old"}
            mock_cache_cls.return_value = mock_cache

            mock_fetcher = MagicMock()
            mock_fetcher.fetch = AsyncMock(return_value="<html>New</html>")
            mock_fetcher_cls.return_value = mock_fetcher

            mock_extractor = MagicMock()
            mock_extractor.extract_body.return_value = "New body"
            mock_extractor.extract_metadata_with_llm = AsyncMock(return_value={
                "title": "Fresh Title",
                "published_date": None,
                "authors": [],
            })
            mock_extractor_cls.return_value = mock_extractor

            result = await get_article(
                "https://example.com/cached",
                cache_dir=str(tmp_path),
                ignore_cache=True,
            )

            assert result["title"] == "Fresh Title"
            # 캐시 로드는 호출되지 않음 (exists도 체크 안함)
            mock_fetcher.fetch.assert_called_once()


class TestFormatArticleForPrompt:
    """프롬프트용 포맷 테스트"""

    def test_formats_article_data(self):
        """아티클 데이터를 프롬프트용 문자열로 포맷"""
        from seosoyoung.web import format_article_for_prompt

        article = {
            "url": "https://example.com/article",
            "title": "Test Article",
            "text": "Article body content here.",
            "published_date": "2024-01-15",
            "authors": ["John Doe", "Jane Smith"],
        }

        result = format_article_for_prompt(article)

        assert "Test Article" in result
        assert "2024-01-15" in result
        assert "John Doe" in result
        assert "Article body content here." in result

    def test_handles_missing_fields(self):
        """필드 누락 시 처리"""
        from seosoyoung.web import format_article_for_prompt

        article = {
            "url": "https://example.com/article",
            "title": "Minimal Article",
            "text": "Content",
            "published_date": None,
            "authors": [],
        }

        result = format_article_for_prompt(article)

        assert "Minimal Article" in result
        assert "Content" in result

    def test_truncates_long_text(self):
        """긴 본문 자르기"""
        from seosoyoung.web import format_article_for_prompt

        article = {
            "url": "https://example.com/long",
            "title": "Long Article",
            "text": "x" * 100000,
            "published_date": None,
            "authors": [],
        }

        result = format_article_for_prompt(article, max_body_length=10000)

        # 본문이 잘려야 함
        assert len(result) < 100000
