"""HTML 페처 테스트"""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from seosoyoung.web.fetcher import HtmlFetcher


class TestHtmlFetcherChromeOptions:
    """Chrome 옵션 설정 테스트"""

    def test_get_chrome_options_returns_options(self):
        """Chrome 옵션 객체 반환"""
        fetcher = HtmlFetcher()
        options = fetcher.get_chrome_options()

        # ChromeOptions 타입이어야 함
        assert options is not None
        # headless 모드가 설정되어 있어야 함
        assert any("headless" in str(arg) for arg in options.arguments)

    def test_chrome_options_has_no_sandbox(self):
        """no-sandbox 옵션 포함"""
        fetcher = HtmlFetcher()
        options = fetcher.get_chrome_options()

        assert "--no-sandbox" in options.arguments

    def test_chrome_options_has_disable_gpu(self):
        """disable-gpu 옵션 포함"""
        fetcher = HtmlFetcher()
        options = fetcher.get_chrome_options()

        assert "--disable-gpu" in options.arguments


class TestHtmlFetcherFetch:
    """HTML 페칭 테스트"""

    @pytest.mark.asyncio
    async def test_fetch_returns_html(self):
        """HTML 문자열 반환"""
        fetcher = HtmlFetcher()

        # Mock webdriver
        mock_driver = MagicMock()
        mock_driver.execute_script.return_value = "<html><body>Test content " + "x" * 1000 + "</body></html>"

        with patch("seosoyoung.web.fetcher.webdriver.Chrome") as mock_chrome, \
             patch("seosoyoung.web.fetcher.ChromeDriverManager") as mock_manager:
            mock_manager.return_value.install.return_value = "/path/to/chromedriver"
            mock_chrome.return_value.__enter__ = MagicMock(return_value=mock_driver)
            mock_chrome.return_value.__exit__ = MagicMock(return_value=False)
            mock_chrome.return_value = mock_driver

            result = await fetcher.fetch("https://example.com")

            assert "<html>" in result
            assert "Test content" in result

    @pytest.mark.asyncio
    async def test_fetch_waits_for_content(self):
        """콘텐츠가 충분히 로드될 때까지 대기"""
        fetcher = HtmlFetcher()

        # 처음에는 짧은 콘텐츠, 이후 긴 콘텐츠
        call_count = 0
        def mock_execute_script(script):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return "<html><body>Short</body></html>"
            return "<html><body>" + "Content " * 200 + "</body></html>"

        mock_driver = MagicMock()
        mock_driver.execute_script.side_effect = mock_execute_script

        with patch("seosoyoung.web.fetcher.webdriver.Chrome") as mock_chrome, \
             patch("seosoyoung.web.fetcher.ChromeDriverManager") as mock_manager, \
             patch("seosoyoung.web.fetcher.asyncio.sleep", new_callable=AsyncMock):
            mock_manager.return_value.install.return_value = "/path/to/chromedriver"
            mock_chrome.return_value = mock_driver

            result = await fetcher.fetch("https://example.com")

            # 여러 번 호출되어야 함
            assert call_count >= 3
            assert "Content" in result

    @pytest.mark.asyncio
    async def test_fetch_cleans_up_driver(self):
        """드라이버 정리 확인"""
        fetcher = HtmlFetcher()

        mock_driver = MagicMock()
        mock_driver.execute_script.return_value = "<html><body>" + "x" * 1500 + "</body></html>"

        with patch("seosoyoung.web.fetcher.webdriver.Chrome") as mock_chrome, \
             patch("seosoyoung.web.fetcher.ChromeDriverManager") as mock_manager:
            mock_manager.return_value.install.return_value = "/path/to/chromedriver"
            mock_chrome.return_value = mock_driver

            await fetcher.fetch("https://example.com")

            # quit()이 호출되어야 함
            mock_driver.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_handles_timeout(self):
        """타임아웃 처리"""
        fetcher = HtmlFetcher()

        mock_driver = MagicMock()
        # 항상 짧은 콘텐츠만 반환 (타임아웃 유발)
        mock_driver.execute_script.return_value = "<html><body>Short</body></html>"

        with patch("seosoyoung.web.fetcher.webdriver.Chrome") as mock_chrome, \
             patch("seosoyoung.web.fetcher.ChromeDriverManager") as mock_manager, \
             patch("seosoyoung.web.fetcher.asyncio.sleep", new_callable=AsyncMock):
            mock_manager.return_value.install.return_value = "/path/to/chromedriver"
            mock_chrome.return_value = mock_driver

            # timeout=3으로 짧게 설정
            result = await fetcher.fetch("https://example.com", content_wait_iterations=3)

            # 타임아웃 후에도 결과 반환
            assert result == "<html><body>Short</body></html>"
            # quit() 호출 확인
            mock_driver.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_cleans_up_on_exception(self):
        """예외 발생 시에도 드라이버 정리"""
        fetcher = HtmlFetcher()

        mock_driver = MagicMock()
        mock_driver.get.side_effect = Exception("Network error")

        with patch("seosoyoung.web.fetcher.webdriver.Chrome") as mock_chrome, \
             patch("seosoyoung.web.fetcher.ChromeDriverManager") as mock_manager:
            mock_manager.return_value.install.return_value = "/path/to/chromedriver"
            mock_chrome.return_value = mock_driver

            with pytest.raises(Exception, match="Network error"):
                await fetcher.fetch("https://example.com")

            # 예외가 발생해도 quit() 호출
            mock_driver.quit.assert_called_once()


class TestHtmlFetcherConfig:
    """설정 테스트"""

    def test_default_page_load_timeout(self):
        """기본 페이지 로드 타임아웃"""
        fetcher = HtmlFetcher()
        assert fetcher.page_load_timeout == 60

    def test_custom_page_load_timeout(self):
        """커스텀 페이지 로드 타임아웃"""
        fetcher = HtmlFetcher(page_load_timeout=30)
        assert fetcher.page_load_timeout == 30

    def test_default_content_threshold(self):
        """기본 콘텐츠 임계값"""
        fetcher = HtmlFetcher()
        assert fetcher.content_threshold == 1000

    def test_custom_content_threshold(self):
        """커스텀 콘텐츠 임계값"""
        fetcher = HtmlFetcher(content_threshold=500)
        assert fetcher.content_threshold == 500
