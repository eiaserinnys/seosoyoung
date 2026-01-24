# translator/detector.py

> 경로: `seosoyoung/translator/detector.py`

## 개요

언어 감지 모듈

Unicode 블록 기반으로 한글/영어를 감지합니다.

## 클래스

### `Language` (Enum)
- 위치: 줄 9

## 함수

### `is_korean_char(char)`
- 위치: 줄 14
- 설명: 한글 문자인지 확인 (한글 자모, 음절 모두 포함)

### `detect_language(text, threshold)`
- 위치: 줄 27
- 설명: 텍스트의 언어를 감지

Args:
    text: 감지할 텍스트
    threshold: 한글 비율 임계값 (기본 30%)

Returns:
    Language.KOREAN 또는 Language.ENGLISH
