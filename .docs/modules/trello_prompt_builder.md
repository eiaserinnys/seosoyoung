# trello/prompt_builder.py

> 경로: `seosoyoung/slackbot/trello/prompt_builder.py`

## 개요

트렐로 카드 프롬프트 빌더

TrelloWatcher가 Claude에 전달할 프롬프트를 생성하는 로직을 담당합니다.
- To Go 카드 프롬프트 (실행/계획 모드)
- 리액션 기반 실행 프롬프트
- 리스트 정주행 프롬프트

## 클래스

### `PromptBuilder`
- 위치: 줄 14
- 설명: 트렐로 카드용 프롬프트 빌더

TrelloClient를 통해 카드의 체크리스트, 코멘트 등을 조회하고
Claude에 전달할 프롬프트 문자열을 생성합니다.

#### 메서드

- `__init__(self, trello)` (줄 21): 
- `build_card_context(self, card_id, desc)` (줄 24): 카드의 체크리스트, 코멘트, 리스트 ID 컨텍스트를 조합
- `build_to_go(self, card, has_execute)` (줄 53): To Go 카드용 프롬프트 생성
- `build_reaction_execute(self, info)` (줄 93): 리액션 기반 실행용 프롬프트 생성
- `build_list_run(self, card, session_id, current, total)` (줄 121): 리스트 정주행용 프롬프트 생성

## 함수

### `_build_task_context_hint()`
- 위치: 줄 153
- 설명: 태스크 컨텍스트 힌트 생성

### `_build_list_ids_context()`
- 위치: 줄 161
- 설명: 자주 사용하는 리스트 ID 컨텍스트 생성 (Config에서 동적으로 조회)

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.trello.client.TrelloCard`
- `seosoyoung.trello.client.TrelloClient`
- `seosoyoung.trello.formatting.format_checklists`
- `seosoyoung.trello.formatting.format_comments`
