# translate/plugin.py

> 경로: `seosoyoung/slackbot/plugins/translate/plugin.py`

## 개요

Translate plugin.

Automatically translates messages in configured channels.
Detects language (Korean/English) and translates to the other.

## 클래스

### `TranslatePlugin` (Plugin)
- 위치: 줄 22
- 설명: 자동 번역 플러그인.

설정된 채널의 메시지를 자동 감지하여 한↔영 번역합니다.

#### 메서드

- `async on_load(self, config)` (줄 34): 
- `async on_unload(self)` (줄 53): 
- `register_hooks(self)` (줄 56): 
- `_get_user_display_name(self, client, user_id)` (줄 74): 사용자의 표시 이름을 가져옵니다.
- `_get_context_messages(self, client, channel, thread_ts, limit)` (줄 89): 이전 메시지들을 컨텍스트로 가져옵니다.
- `_format_response(self, user_name, translated, source_lang, cost, glossary_terms)` (줄 123): 응답 메시지를 포맷팅합니다.
- `_send_debug_log(self, client, original_text, source_lang, match_result)` (줄 144): 디버그 로그를 지정된 슬랙 채널에 전송합니다.
- `_process_translate(self, event, client)` (줄 211): 메시지를 번역 처리합니다.

## 내부 의존성

- `seosoyoung.core.hooks.HookContext`
- `seosoyoung.core.hooks.HookResult`
- `seosoyoung.core.plugin.Plugin`
- `seosoyoung.core.plugin.PluginMeta`
- `seosoyoung.slackbot.plugins.translate.detector.Language`
- `seosoyoung.slackbot.plugins.translate.detector.detect_language`
- `seosoyoung.slackbot.plugins.translate.glossary.GlossaryMatchResult`
- `seosoyoung.slackbot.plugins.translate.translator.translate`
