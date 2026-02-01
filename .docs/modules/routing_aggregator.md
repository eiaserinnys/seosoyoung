# routing/aggregator.py

> 경로: `seosoyoung/routing/aggregator.py`

## 개요

결과 집계기

개별 평가 결과를 종합하여 최적 도구를 선택하고 요약을 생성하는 모듈.

## 클래스

### `AggregationResult`
- 위치: 줄 112
- 설명: 집계 결과

#### 메서드

- `has_suitable_tool(self)` (줄 123): 적합한 도구가 있는지 여부
- `to_dict(self)` (줄 127): 딕셔너리 변환
- `from_evaluation_results(cls, results, user_request, threshold)` (줄 139): 평가 결과에서 집계 결과 생성.

### `ResultAggregator`
- 위치: 줄 202
- 설명: 결과 집계기

평가 결과를 종합하여 최적 도구를 선택하고 요약을 생성합니다.

#### 메서드

- `__init__(self, client, model, threshold)` (줄 208): Args:
- `aggregate(self, results, user_request)` (줄 224): 평가 결과 집계 (요약 생성 없이).
- `async aggregate_with_summary(self, results, user_request)` (줄 242): 평가 결과 집계 및 요약 생성.

## 함수

### `rank_results(results)`
- 위치: 줄 18
- 설명: 평가 결과를 점수 기준으로 정렬.

Args:
    results: 평가 결과 리스트

Returns:
    점수 내림차순 정렬된 리스트 (동점 시 이름 순)

### `select_best_tool(results, threshold)`
- 위치: 줄 33
- 설명: 최적 도구 선택.

Args:
    results: 평가 결과 리스트
    threshold: 최소 적합도 임계값

Returns:
    가장 높은 점수의 EvaluationResult 또는 None (모두 임계값 미만일 경우)

### `build_summary_prompt(results, user_request, selected_tool)`
- 위치: 줄 58
- 설명: 요약 생성 프롬프트.

Args:
    results: 평가 결과 리스트
    user_request: 사용자 요청
    selected_tool: 선택된 도구 이름 (없으면 None)

Returns:
    요약 생성 프롬프트
