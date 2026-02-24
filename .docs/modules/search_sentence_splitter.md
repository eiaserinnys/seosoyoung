# search/sentence_splitter.py

> 경로: `seosoyoung/slackbot/search/sentence_splitter.py`

## 개요

한/영 텍스트 문장 분할기.

전처리 → 분할 → 후처리 파이프라인으로 텍스트를 문장 단위로 분리한다.

## 함수

### `split_sentences(text, min_length)`
- 위치: 줄 16
- 설명: 텍스트를 문장 단위로 분할.

Args:
    text: 분할할 텍스트
    min_length: 최소 문장 길이 (이보다 짧은 문장은 제거)

Returns:
    분할된 문장 리스트
