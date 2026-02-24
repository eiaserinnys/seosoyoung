# api/auth.py

> 경로: `seosoyoung/soul/api/auth.py`

## 개요

Authentication - Bearer 토큰 인증

## 함수

### `async verify_token(authorization)`
- 위치: 줄 20
- 설명: Bearer 토큰 검증

Args:
    authorization: Authorization 헤더 값

Returns:
    검증된 토큰

Raises:
    HTTPException: 인증 실패

## 내부 의존성

- `seosoyoung.soul.config.get_settings`
