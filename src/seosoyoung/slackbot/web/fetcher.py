"""Selenium 기반 HTML 페처"""

import asyncio
import logging

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


class HtmlFetcher:
    """Selenium을 사용한 동적 웹 페이지 HTML 페처"""

    def __init__(
        self,
        page_load_timeout: int = 60,
        content_threshold: int = 1000,
    ):
        """
        Args:
            page_load_timeout: 페이지 로드 타임아웃 (초)
            content_threshold: 콘텐츠 로드 완료로 간주할 최소 텍스트 길이
        """
        self.page_load_timeout = page_load_timeout
        self.content_threshold = content_threshold

    def get_chrome_options(self) -> webdriver.ChromeOptions:
        """Chrome 옵션 설정

        Returns:
            설정된 ChromeOptions 객체
        """
        options = webdriver.ChromeOptions()

        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        return options

    async def fetch(
        self,
        url: str,
        content_wait_iterations: int = 15,
    ) -> str:
        """URL에서 렌더링된 HTML 가져오기

        동적 JavaScript 콘텐츠가 로드될 때까지 대기합니다.

        Args:
            url: 가져올 URL
            content_wait_iterations: 콘텐츠 로드 대기 반복 횟수

        Returns:
            렌더링된 HTML 문자열

        Raises:
            Exception: 페이지 로드 실패 시
        """
        driver = None

        try:
            options = self.get_chrome_options()

            logger.info("preparing browser...")
            chrome_service = ChromeService(ChromeDriverManager().install())

            driver = webdriver.Chrome(service=chrome_service, options=options)
            driver.set_page_load_timeout(self.page_load_timeout)

            logger.info(f"fetching page (timeout={self.page_load_timeout}s)...")
            driver.get(url)

            logger.info("waiting for content to load...")
            dynamic_html = None

            for _ in range(content_wait_iterations):
                dynamic_html = driver.execute_script(
                    "return document.documentElement.outerHTML;"
                )

                # 콘텐츠가 충분히 로드되었는지 확인
                soup = BeautifulSoup(dynamic_html, "html.parser")
                all_text = " ".join(text.strip() for text in soup.stripped_strings)

                if len(all_text) > self.content_threshold:
                    logger.info("content loaded successfully")
                    break

                logger.debug("waiting for more content...")
                await asyncio.sleep(0.3)

            return dynamic_html

        finally:
            if driver:
                try:
                    driver.quit()
                    logger.debug("browser closed")
                except Exception as e:
                    logger.warning(f"failed to close browser: {e}")
