# translator/__main__.py

> 경로: `seosoyoung/slackbot/translator/__main__.py`

## 개요

번역 기능 CLI 테스트

사용법:
    python -m seosoyoung.slackbot.translator "번역할 텍스트"
    python -m seosoyoung.slackbot.translator -f en "Translate this to Korean"
    python -m seosoyoung.slackbot.translator --detect "자동 감지 테스트"

## 함수

### `main()`
- 위치: 줄 18

## 내부 의존성

- `seosoyoung.slackbot.translator.detector.Language`
- `seosoyoung.slackbot.translator.detector.detect_language`
- `seosoyoung.slackbot.translator.glossary.find_relevant_terms_v2`
- `seosoyoung.slackbot.translator.translator.translate`
