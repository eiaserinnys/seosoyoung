# handlers/translate.py

> 경로: `seosoyoung/slackbot/handlers/translate.py`

## 개요

번역 핸들러

특정 채널의 메시지를 감지하여 자동 번역합니다.

## 함수

### `_get_user_display_name(client, user_id)`
- 위치: 줄 15
- 설명: 사용자의 표시 이름을 가져옵니다.

### `_get_context_messages(client, channel, thread_ts, limit)`
- 위치: 줄 31
- 설명: 이전 메시지들을 컨텍스트로 가져옵니다.

Args:
    client: Slack 클라이언트
    channel: 채널 ID
    thread_ts: 스레드 타임스탬프 (없으면 채널 메시지)
    limit: 가져올 메시지 수

Returns:
    [{"user": "이름", "text": "내용"}, ...] 형태의 리스트 (시간순)

### `_format_response(user_name, translated, source_lang, cost, glossary_terms)`
- 위치: 줄 77
- 설명: 응답 메시지를 포맷팅합니다.

Args:
    user_name: 원본 메시지 작성자 이름
    translated: 번역된 텍스트
    source_lang: 원본 언어
    cost: 예상 번역 비용 (USD)
    glossary_terms: 참고한 용어 목록 [(원어, 번역어), ...]

Returns:
    포맷팅된 응답 문자열

### `_send_debug_log(client, original_text, source_lang, match_result)`
- 위치: 줄 114
- 설명: 디버그 로그를 지정된 슬랙 채널에 전송합니다.

Args:
    client: Slack 클라이언트
    original_text: 원본 텍스트
    source_lang: 원본 언어
    match_result: 용어 매칭 결과

### `process_translate_message(event, client)`
- 위치: 줄 194
- 설명: 메시지를 번역 처리합니다.

Args:
    event: 슬랙 메시지 이벤트
    client: 슬랙 클라이언트

Returns:
    처리 여부 (True: 처리됨, False: 처리하지 않음)

### `register_translate_handler(app, dependencies)`
- 위치: 줄 319
- 설명: 번역 핸들러를 앱에 등록합니다.

Note: 이 함수는 더 이상 핸들러를 등록하지 않습니다.
번역 처리는 message.py의 handle_message에서 process_translate_message를 호출합니다.

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.translator.GlossaryMatchResult`
- `seosoyoung.translator.Language`
- `seosoyoung.translator.detect_language`
- `seosoyoung.translator.translate`
