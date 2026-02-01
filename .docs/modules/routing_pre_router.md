# routing/pre_router.py

> 경로: `seosoyoung/routing/pre_router.py`

## 개요

PreRouter - 전체 사전 라우팅 파이프라인

loader, evaluator, aggregator를 조합하여 사용자 요청에 가장 적합한
도구를 결정하는 오케스트레이션 클래스.

## 클래스

### `RoutingResult`
- 위치: 줄 29
- 설명: 라우팅 결과

#### 메서드

- `has_recommendation(self)` (줄 43): 추천 도구가 있는지 여부
- `to_dict(self)` (줄 47): 딕셔너리 변환
- `to_prompt_injection(self)` (줄 61): Claude Code 프롬프트에 주입할 텍스트 생성

### `PreRouter`
- 위치: 줄 90
- 설명: 사전 라우팅 파이프라인

사용자 요청을 분석하여 가장 적합한 에이전트/스킬을 결정합니다.

#### 메서드

- `__init__(self, workspace_path, client, model, timeout, threshold, max_concurrent, enabled)` (줄 96): Args:
- `get_tools(self)` (줄 128): 도구 목록 로드 (캐싱)
- `refresh_tools(self)` (줄 134): 도구 목록 캐시 갱신
- `async route(self, user_request)` (줄 138): 사용자 요청에 대한 최적 도구 결정.
- `async _route_internal(self, user_request)` (줄 196): 내부 라우팅 로직
- `route_sync(self, user_request)` (줄 266): 동기 버전의 라우팅.
