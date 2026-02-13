# tools/user_profile.py

> 경로: `seosoyoung/mcp/tools/user_profile.py`

## 개요

Slack 사용자 프로필 조회 및 아바타 다운로드 MCP 도구

## 함수

### `_get_slack_client()`
- 위치: 줄 20
- 설명: Slack WebClient 인스턴스 반환

### `get_user_profile(user_id)`
- 위치: 줄 25
- 설명: Slack 사용자 프로필 정보를 조회

Args:
    user_id: Slack User ID (예: U08HWT0C6K1)

Returns:
    dict: success, profile 키를 포함하는 결과 딕셔너리

### `async download_user_avatar(user_id, size)`
- 위치: 줄 67
- 설명: Slack 사용자 프로필 이미지를 다운로드

Args:
    user_id: Slack User ID
    size: 이미지 크기 (24, 32, 48, 72, 192, 512, 1024). 기본값 512.

Returns:
    dict: success, file_path 키를 포함하는 결과 딕셔너리

## 내부 의존성

- `seosoyoung.mcp.config.SLACK_BOT_TOKEN`
- `seosoyoung.mcp.config.WORKSPACE_ROOT`
