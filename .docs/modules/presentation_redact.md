# presentation/redact.py

> 경로: `seosoyoung/slackbot/presentation/redact.py`

## 개요

민감 정보 REDACT 유틸리티

tool 결과 텍스트에 포함될 수 있는 API 키, 토큰, 비밀번호 등의
민감 정보를 가림 처리합니다.

## 함수

### `redact_sensitive(text)`
- 위치: 줄 75
- 설명: 텍스트에서 민감 정보를 [REDACTED]로 대체합니다.

대상 패턴:
- 잘 알려진 토큰 프리픽스 (sk-..., xoxb-..., ghp_... 등)
- Authorization 헤더 값 (Bearer, Token, Basic)
- 민감 키워드를 포함한 환경변수 값 (API_KEY=..., PASSWORD=... 등)
- AWS 스타일 액세스 키 (AKIA..., ASIA... 등)

Args:
    text: 원본 텍스트. None 또는 빈 문자열이면 그대로 반환합니다.

Returns:
    민감 정보가 [REDACTED]로 대체된 텍스트. 입력이 None이면 None.
