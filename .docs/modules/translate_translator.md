# translate/translator.py

> 경로: `seosoyoung/slackbot/plugins/translate/translator.py`

## 개요

번역 모듈

Anthropic 또는 OpenAI API를 호출하여 번역합니다.
backend 파라미터에 따라 분기합니다.

이 모듈은 Config에 의존하지 않습니다.
모든 설정은 호출 시 명시적 파라미터로 전달받습니다.

## 함수

### `_build_context_text(context_messages)`
- 위치: 줄 20
- 설명: 이전 대화 컨텍스트를 텍스트로 변환

Args:
    context_messages: 이전 메시지 목록 [{"user": "이름", "text": "내용"}, ...]

Returns:
    컨텍스트 텍스트

### `_build_glossary_section(text, source_lang, glossary_path)`
- 위치: 줄 39
- 설명: 텍스트에서 관련 용어를 찾아 용어집 섹션 생성

Args:
    text: 번역할 텍스트
    source_lang: 원본 언어
    glossary_path: 용어집 파일 경로

Returns:
    (용어집 섹션 문자열, 참고한 용어 목록, 매칭 결과 객체)
    용어가 없으면 ("", [], None)

### `_build_prompt(text, source_lang, glossary_path, context_messages)`
- 위치: 줄 69
- 설명: 번역 프롬프트 생성

Args:
    text: 번역할 텍스트
    source_lang: 원본 언어
    glossary_path: 용어집 파일 경로
    context_messages: 이전 대화 컨텍스트

Returns:
    (프롬프트 문자열, 참고한 용어 목록, 매칭 결과 객체)

### `_calculate_cost(input_tokens, output_tokens, model)`
- 위치: 줄 129
- 설명: 토큰 사용량으로 비용을 계산합니다.

Args:
    input_tokens: 입력 토큰 수
    output_tokens: 출력 토큰 수
    model: 사용한 모델명

Returns:
    예상 비용 (USD)

### `_translate_anthropic(prompt, model, api_key)`
- 위치: 줄 146
- 설명: Anthropic API로 번역

Returns:
    (번역된 텍스트, 입력 토큰 수, 출력 토큰 수)

### `_translate_openai(prompt, model, api_key)`
- 위치: 줄 162
- 설명: OpenAI API로 번역

Returns:
    (번역된 텍스트, 입력 토큰 수, 출력 토큰 수)

### `translate(text, source_lang)`
- 위치: 줄 180
- 설명: 텍스트를 번역

Args:
    text: 번역할 텍스트
    source_lang: 원본 언어
    backend: 번역 백엔드 ("anthropic" | "openai")
    model: 사용할 모델명
    api_key: API 키
    glossary_path: 용어집 파일 경로
    context_messages: 이전 대화 컨텍스트

Returns:
    (번역된 텍스트, 예상 비용 USD, 참고한 용어 목록, 매칭 결과 객체)

Raises:
    ValueError: 잘못된 backend

## 내부 의존성

- `seosoyoung.slackbot.plugins.translate.detector.Language`
- `seosoyoung.slackbot.plugins.translate.glossary.GlossaryMatchResult`
- `seosoyoung.slackbot.plugins.translate.glossary.find_relevant_terms_v2`
