# trello/client.py

> 경로: `seosoyoung/slackbot/plugins/trello/client.py`

## 개요

Trello API 클라이언트

Config 의존성 없이, 생성자에서 api_key/token/board_id를 직접 받습니다.

## 클래스

### `TrelloCard`
- 위치: 줄 17
- 설명: 트렐로 카드 정보

### `TrelloClient`
- 위치: 줄 29
- 설명: Trello API 클라이언트

모든 설정은 생성자에서 직접 전달받습니다.
Config 싱글턴에 의존하지 않습니다.

#### 메서드

- `__init__(self)` (줄 36): 
- `_request(self, method, endpoint)` (줄 41): API 요청
- `get_cards_in_list(self, list_id)` (줄 56): 특정 리스트의 카드 목록 조회
- `get_card(self, card_id)` (줄 75): 카드 상세 조회
- `update_card_name(self, card_id, name)` (줄 90): 카드 제목 변경
- `move_card(self, card_id, list_id)` (줄 95): 카드를 다른 리스트로 이동
- `get_card_checklists(self, card_id)` (줄 100): 카드의 체크리스트 목록 조회
- `get_card_comments(self, card_id, limit)` (줄 122): 카드의 코멘트 목록 조회
- `get_lists(self)` (줄 143): 보드의 리스트 목록 조회
- `remove_label_from_card(self, card_id, label_id)` (줄 154): 카드에서 레이블 제거
- `is_configured(self)` (줄 159): API 설정 여부 확인
