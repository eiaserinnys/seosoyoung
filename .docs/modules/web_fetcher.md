# web/fetcher.py

> 경로: `seosoyoung/web/fetcher.py`

## 개요

Selenium 기반 HTML 페처

## 클래스

### `HtmlFetcher`
- 위치: 줄 14
- 설명: Selenium을 사용한 동적 웹 페이지 HTML 페처

#### 메서드

- `__init__(self, page_load_timeout, content_threshold)` (줄 17): Args:
- `get_chrome_options(self)` (줄 30): Chrome 옵션 설정
- `async fetch(self, url, content_wait_iterations)` (줄 49): URL에서 렌더링된 HTML 가져오기
