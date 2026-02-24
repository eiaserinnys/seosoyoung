# web/extractor.py

> 경로: `seosoyoung/slackbot/web/extractor.py`

## 개요

HTML에서 컨텐츠 및 메타데이터 추출

## 클래스

### `ContentExtractor`
- 위치: 줄 30
- 설명: HTML에서 본문과 메타데이터를 추출하는 클래스

#### 메서드

- `__init__(self, anthropic_api_key)` (줄 33): Args:
- `extract_body(self, html)` (줄 40): HTML에서 본문 텍스트 추출
- `clean_html(self, html, max_length)` (줄 66): HTML 전처리 (script/style 제거, 길이 제한)
- `async extract_metadata_with_llm(self, html)` (줄 91): Claude Haiku로 메타데이터 추출
- `extract_metadata_fallback(self, html)` (줄 128): goose3 + htmldate로 메타데이터 추출 (폴백)
