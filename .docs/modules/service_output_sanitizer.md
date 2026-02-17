# service/output_sanitizer.py

> 경로: `seosoyoung/mcp/soul/service/output_sanitizer.py`

## 개요

출력 민감 정보 마스킹 모듈

Claude Code 출력에서 API 키, 토큰 등 민감 정보를 마스킹합니다.

## 함수

### `sanitize_output(text)`
- 위치: 줄 32
- 설명: 출력에서 민감 정보를 마스킹합니다.

Args:
    text: 마스킹할 텍스트

Returns:
    민감 정보가 마스킹된 텍스트
