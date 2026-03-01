# memory/token_counter.py

> 경로: `seosoyoung/slackbot/plugins/memory/token_counter.py`

## 개요

토큰 카운터

tiktoken o200k_base 인코딩 기반으로 텍스트와 메시지의 토큰 수를 계산합니다.

## 클래스

### `TokenCounter`
- 위치: 줄 9
- 설명: o200k_base 인코딩 기반 토큰 카운터

#### 메서드

- `__init__(self)` (줄 14): 
- `count_string(self, text)` (줄 17): 텍스트의 토큰 수를 반환합니다.
- `count_messages(self, messages)` (줄 23): 메시지 목록의 총 토큰 수를 반환합니다.
