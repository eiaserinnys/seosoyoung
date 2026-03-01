# trello/watcher.py

> 경로: `seosoyoung/slackbot/plugins/trello/watcher.py`

## 개요

Trello 워처 - To Go 리스트 감시 및 처리

Config 싱글턴 의존성 없이, 생성자에서 설정을 직접 받습니다.

## 클래스

### `TrackedCard`
- 위치: 줄 22
- 설명: 추적 중인 카드 정보 (To Go 리스트 감시용)

### `ThreadCardInfo`
- 위치: 줄 38
- 설명: 스레드 ↔ 카드 매핑 정보 (리액션 처리용)

### `TrelloWatcher`
- 위치: 줄 50
- 설명: Trello 리스트 감시자

모든 설정은 생성자에서 직접 전달받습니다.
Config 싱글턴에 의존하지 않습니다.

#### 메서드

- `__init__(self)` (줄 57): Args:
- `_load_tracked(self)` (줄 126): 추적 상태 로드
- `_save_tracked(self)` (줄 145): 추적 상태 저장
- `_load_thread_cards(self)` (줄 156): 스레드-카드 매핑 로드
- `_save_thread_cards(self)` (줄 167): 스레드-카드 매핑 저장
- `_register_thread_card(self, tracked)` (줄 178): 스레드-카드 매핑 등록
- `_untrack_card(self, card_id)` (줄 194): 카드 추적 해제
- `update_thread_card_session_id(self, thread_ts, session_id)` (줄 201): ThreadCardInfo의 session_id 업데이트
- `get_tracked_by_thread_ts(self, thread_ts)` (줄 209): thread_ts로 ThreadCardInfo 조회
- `update_tracked_session_id(self, card_id, session_id)` (줄 213): TrackedCard의 session_id 업데이트
- `start(self)` (줄 223): 워처 시작
- `stop(self)` (줄 238): 워처 중지
- `pause(self)` (줄 245): 워처 일시 중단
- `resume(self)` (줄 251): 워처 재개
- `is_paused(self)` (줄 258): 
- `_run(self)` (줄 262): 워처 메인 루프
- `_poll(self)` (줄 271): 리스트 폴링
- `_cleanup_stale_tracked(self, current_cards)` (줄 298): 만료된 _tracked 항목 정리
- `_check_review_list_for_completion(self)` (줄 320): Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동
- `_add_spinner_prefix(self, card)` (줄 347): 
- `_remove_spinner_prefix(self, card_id, card_name)` (줄 353): 
- `_has_execute_label(self, card)` (줄 359): 
- `_has_run_list_label(self, card)` (줄 365): 
- `_get_run_list_label_id(self, card)` (줄 371): 
- `_build_header(self, card_name, card_url, session_id)` (줄 377): 
- `_get_dm_or_notify_channel(self)` (줄 381): 
- `_open_dm_thread(self, card_name, card_url)` (줄 390): 
- `_handle_new_card(self, card, list_key)` (줄 414): 새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행
- `build_reaction_execute_prompt(self, info)` (줄 490): 하위 호환: PromptBuilder에 위임
- `_spawn_claude_thread(self)` (줄 494): Claude 실행 스레드 스포닝
- `_get_operational_list_ids(self)` (줄 562): 운영 리스트 ID 집합 반환
- `_check_run_list_labels(self)` (줄 573): 🏃 Run List 레이블을 가진 카드 감지 및 리스트 정주행 시작
- `_preemptive_compact(self, thread_ts, channel, card_name)` (줄 618): 카드 완료 후 선제적 컨텍스트 컴팩트
- `_start_list_run(self, list_id, list_name, cards)` (줄 648): 리스트 정주행 시작
- `_process_list_run_card(self, session_id, thread_ts, run_channel)` (줄 690): 리스트 정주행 카드 처리
- `_process_list_run_card_inner(self, list_runner, session_id, thread_ts, channel, run_channel)` (줄 717): 

## 내부 의존성

- `seosoyoung.slackbot.plugins.trello.client.TrelloCard`
- `seosoyoung.slackbot.plugins.trello.client.TrelloClient`
- `seosoyoung.slackbot.plugins.trello.prompt_builder.PromptBuilder`
