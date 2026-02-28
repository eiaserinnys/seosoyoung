# api/credentials.py

> 경로: `seosoyoung/soul/api/credentials.py`

## 개요

Credentials API - 프로필 관리 REST 엔드포인트

프로필 목록 조회, 활성 프로필 확인, 저장/활성화/삭제, rate limit 현황.
모든 엔드포인트는 Bearer 토큰 인증이 필요합니다.

## 함수

### `create_credentials_router(store, swapper, rate_limit_tracker)`
- 위치: 줄 21
- 설명: Credentials API 라우터 팩토리.

Args:
    store: 프로필 저장소
    swapper: 크레덴셜 교체기
    rate_limit_tracker: rate limit 추적기 (None이면 rate-limits 엔드포인트 비활성)

Returns:
    FastAPI APIRouter

## 내부 의존성

- `seosoyoung.soul.api.auth.verify_token`
- `seosoyoung.soul.service.credential_store.CredentialStore`
- `seosoyoung.soul.service.credential_swapper.CredentialSwapper`
- `seosoyoung.soul.service.rate_limit_tracker.RateLimitTracker`
