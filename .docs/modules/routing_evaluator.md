# routing/evaluator.py

> 경로: `seosoyoung/routing/evaluator.py`

## 개요

하이쿠 평가 클라이언트

Anthropic SDK로 하이쿠 모델을 호출하여 도구 적합도를 평가하는 모듈.

## 클래스

### `EvaluationResult`
- 위치: 줄 181
- 설명: 도구 평가 결과

#### 메서드

- `is_suitable(self)` (줄 192): 임계값 이상이면 적합
- `to_dict(self)` (줄 196): 딕셔너리 변환

### `ToolEvaluator`
- 위치: 줄 207
- 설명: 도구 적합도 평가기

Anthropic SDK를 사용하여 하이쿠 모델로 도구 적합도를 평가합니다.

#### 메서드

- `__init__(self, client, model, timeout, max_retries, retry_delay, max_concurrent)` (줄 213): Args:
- `async evaluate_tool(self, tool, user_request)` (줄 239): 단일 도구 평가.
- `async _call_api(self, prompt)` (줄 301): API 호출.
- `async evaluate_all(self, tools, user_request)` (줄 317): 모든 도구 병렬 평가.

## 함수

### `build_evaluation_prompt(tool, user_request)`
- 위치: 줄 27
- 설명: 도구 평가를 위한 프롬프트 생성.

Args:
    tool: 평가할 도구 정의
    user_request: 사용자 요청

Returns:
    평가 프롬프트 문자열

### `parse_evaluation_response(response, tool_name, tool_type)`
- 위치: 줄 89
- 설명: 평가 응답 파싱.

Args:
    response: 모델 응답 텍스트
    tool_name: 도구 이름
    tool_type: 도구 타입 (agent, skill, unknown)

Returns:
    EvaluationResult 객체

### `_parse_with_regex_fallback(response, tool_name, tool_type)`
- 위치: 줄 133
- 설명: 정규식을 사용한 폴백 파싱.

Args:
    response: 모델 응답 텍스트
    tool_name: 도구 이름
    tool_type: 도구 타입 (agent, skill, unknown)

Returns:
    EvaluationResult 객체
