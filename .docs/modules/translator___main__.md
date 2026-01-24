# translator/__main__.py

> 경로: `seosoyoung/translator/__main__.py`

## 개요

번역 기능 CLI 테스트

사용법:
    python -m seosoyoung.translator "번역할 텍스트"
    python -m seosoyoung.translator -f en "Translate this to Korean"
    python -m seosoyoung.translator --detect "자동 감지 테스트"

## 함수

### `main()`
- 위치: 줄 18

## 내부 의존성

- `seosoyoung.translator.detector.Language`
- `seosoyoung.translator.detector.detect_language`
- `seosoyoung.translator.glossary.find_relevant_terms_v2`
- `seosoyoung.translator.translator.translate`
