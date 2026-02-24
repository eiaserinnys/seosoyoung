# seosoyoung/auth.py

> 경로: `seosoyoung/auth.py`

## 개요

권한 및 역할 관리

사용자 권한 확인과 역할 조회 기능을 제공합니다.

## 함수

### `check_permission(user_id, client)`
- 위치: 줄 13
- 설명: 사용자 권한 확인 (관리자 명령어용)

### `get_user_role(user_id, client)`
- 위치: 줄 26
- 설명: 사용자 역할 정보 반환

Returns:
    dict: {"user_id", "username", "role", "allowed_tools"} 또는 실패 시 None

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
