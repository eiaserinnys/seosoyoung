# recall/recall.py

> 경로: `seosoyoung/recall/recall.py`

## 개요

Recall - 도구 선택 사전 분석 파이프라인

loader, evaluator, aggregator를 조합하여 사용자 요청에 가장 적합한
도구를 결정하는 오케스트레이션 클래스.

## 클래스

### `RecallResult`
- 위치: 줄 30
- 설명: Recall 결과

#### 메서드

- `has_recommendation(self)` (줄 44): 추천 도구가 있는지 여부
- `to_dict(self)` (줄 48): 딕셔너리 변환
- `to_prompt_injection(self)` (줄 62): Claude Code 프롬프트에 주입할 텍스트 생성

### `Recall`
- 위치: 줄 106
- 설명: Recall - 도구 선택 사전 분석 파이프라인

사용자 요청을 분석하여 가장 적합한 에이전트/스킬을 결정합니다.

#### 메서드

- `__init__(self, workspace_path, client, model, timeout, threshold, max_concurrent, enabled)` (줄 112): Args:
- `get_tools(self)` (줄 144): 도구 목록 로드 (캐싱)
- `refresh_tools(self)` (줄 150): 도구 목록 캐시 갱신
- `async analyze(self, user_request)` (줄 154): 사용자 요청에 대한 최적 도구 결정.
- `async _analyze_internal(self, user_request)` (줄 212): 내부 분석 로직
- `analyze_sync(self, user_request)` (줄 282): 동기 버전의 분석.
- `async route(self, user_request)` (줄 294): analyze()의 별칭 (하위 호환성)
- `route_sync(self, user_request)` (줄 298): analyze_sync()의 별칭 (하위 호환성)
