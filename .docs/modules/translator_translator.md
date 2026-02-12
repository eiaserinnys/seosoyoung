# translator/translator.py

> 경로: `seosoyoung/translator/translator.py`

## 개요

번역 모듈

Anthropic 또는 OpenAI API를 호출하여 번역합니다.
backend 설정(Config.TRANSLATE_BACKEND)에 따라 분기합니다.

## 함수

### `_build_context_text(context_messages)`
- 위치: 줄 18
- 설명: 이전 대화 컨텍스트를 텍스트로 변환

Args:
    context_messages: 이전 메시지 목록 [{"user": "이름", "text": "내용"}, ...]

Returns:
    컨텍스트 텍스트

### `_build_glossary_section(text, source_lang)`
- 위치: 줄 37
- 설명: 텍스트에서 관련 용어를 찾아 용어집 섹션 생성

Args:
    text: 번역할 텍스트
    source_lang: 원본 언어

Returns:
    (용어집 섹션 문자열, 참고한 용어 목록, 매칭 결과 객체)
    용어가 없으면 ("", [], None)

### `_build_prompt(text, source_lang, context_messages)`
- 위치: 줄 62
- 설명: 번역 프롬프트 생성

Args:
    text: 번역할 텍스트
    source_lang: 원본 언어
    context_messages: 이전 대화 컨텍스트

Returns:
    (프롬프트 문자열, 참고한 용어 목록, 매칭 결과 객체)

### `_calculate_cost(input_tokens, output_tokens, model)`
- 위치: 줄 118
- 설명: 토큰 사용량으로 비용을 계산합니다.

Args:
    input_tokens: 입력 토큰 수
    output_tokens: 출력 토큰 수
    model: 사용한 모델명

Returns:
    예상 비용 (USD)

### `_translate_anthropic(prompt, model, api_key)`
- 위치: 줄 135
- 설명: Anthropic API로 번역

Returns:
    (번역된 텍스트, 입력 토큰 수, 출력 토큰 수)

### `_translate_openai(prompt, model, api_key)`
- 위치: 줄 151
- 설명: OpenAI API로 번역

Returns:
    (번역된 텍스트, 입력 토큰 수, 출력 토큰 수)

### `translate(text, source_lang, context_messages, model, backend)`
- 위치: 줄 169
- 설명: 텍스트를 번역

Args:
    text: 번역할 텍스트
    source_lang: 원본 언어
    context_messages: 이전 대화 컨텍스트
    model: 사용할 모델 (기본값: backend에 따라 Config에서 결정)
    backend: 번역 백엔드 ("anthropic" | "openai", 기본값: Config.TRANSLATE_BACKEND)

Returns:
    (번역된 텍스트, 예상 비용 USD, 참고한 용어 목록, 매칭 결과 객체)

Raises:
    ValueError: API 키 미설정 또는 잘못된 backend

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.translator.detector.Language`
- `seosoyoung.translator.glossary.GlossaryMatchResult`
- `seosoyoung.translator.glossary.find_relevant_terms_v2`
