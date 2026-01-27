# trello/client.py

> 경로: `seosoyoung/trello/client.py`

## 개요

Trello API 클라이언트

## 클래스

### `TrelloCard`
- 위치: 줄 16
- 설명: 트렐로 카드 정보

### `TrelloClient`
- 위치: 줄 28
- 설명: Trello API 클라이언트

#### 메서드

- `__init__(self, api_key, token, board_id)` (줄 31): 
- `_request(self, method, endpoint)` (줄 44): API 요청
- `get_cards_in_list(self, list_id)` (줄 59): 특정 리스트의 카드 목록 조회
- `get_card(self, card_id)` (줄 78): 카드 상세 조회
- `update_card_name(self, card_id, name)` (줄 93): 카드 제목 변경
- `move_card(self, card_id, list_id)` (줄 106): 카드를 다른 리스트로 이동
- `get_card_checklists(self, card_id)` (줄 119): 카드의 체크리스트 목록 조회
- `get_card_comments(self, card_id, limit)` (줄 157): 카드의 코멘트 목록 조회
- `is_configured(self)` (줄 195): API 설정 여부 확인

## 내부 의존성

- `seosoyoung.config.Config`
