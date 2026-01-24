# trello/watcher.py

> 경로: `seosoyoung/trello/watcher.py`

## 개요

Trello 워처 - To Go 리스트 감시 및 처리

## 클래스

### `TrackedCard`
- 위치: 줄 19
- 설명: 추적 중인 카드 정보 (To Go 리스트 감시용)

### `ThreadCardInfo`
- 위치: 줄 34
- 설명: 스레드 ↔ 카드 매핑 정보 (리액션 처리용)

Claude 세션이 시작된 슬랙 스레드와 트렐로 카드의 연결을 유지합니다.
TrackedCard와 달리 Claude 실행 완료 후에도 유지되어 리액션 기반 실행을 지원합니다.

### `TrelloWatcher`
- 위치: 줄 50
- 설명: Trello 리스트 감시자

To Go 리스트에 새 카드가 들어오면:
1. 카드를 In Progress로 이동
2. Slack에 알림 메시지 전송
3. Claude Code 세션 시작
4. Execute 레이블 유무에 따라:
   - 없음: 계획 수립 후 Backlog로 이동
   - 있음: 작업 실행 후 Review/Blocked로 이동

#### 메서드

- `__init__(self, slack_client, session_manager, claude_runner_factory, get_session_lock, notify_channel, poll_interval, data_dir)` (줄 62): Args:
- `_load_tracked(self)` (줄 112): 추적 상태 로드
- `_save_tracked(self)` (줄 130): 추적 상태 저장
- `_load_thread_cards(self)` (줄 141): 스레드-카드 매핑 로드
- `_save_thread_cards(self)` (줄 152): 스레드-카드 매핑 저장
- `_register_thread_card(self, tracked)` (줄 163): 스레드-카드 매핑 등록
- `_untrack_card(self, card_id)` (줄 179): To Go 추적에서 카드 제거 (Claude 실행 완료 시 호출)
- `update_thread_card_session_id(self, thread_ts, session_id)` (줄 186): ThreadCardInfo의 session_id 업데이트
- `get_tracked_by_thread_ts(self, thread_ts)` (줄 202): thread_ts로 ThreadCardInfo 조회 (리액션 처리용)
- `update_tracked_session_id(self, card_id, session_id)` (줄 213): TrackedCard의 session_id 업데이트
- `start(self)` (줄 229): 워처 시작 (백그라운드 스레드)
- `stop(self)` (줄 244): 워처 중지
- `pause(self)` (줄 251): 워처 일시 중단 (재시작 대기용)
- `resume(self)` (줄 257): 워처 재개
- `is_paused(self)` (줄 264): 일시 중단 상태인지 확인
- `_run(self)` (줄 269): 워처 메인 루프
- `_poll(self)` (줄 280): 리스트 폴링
- `_check_review_list_for_completion(self)` (줄 310): Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동
- `_add_spinner_prefix(self, card)` (줄 335): 카드 제목에 🌀 prefix 추가
- `_remove_spinner_prefix(self, card_id, card_name)` (줄 342): 카드 제목에서 🌀 prefix 제거
- `_has_execute_label(self, card)` (줄 349): 카드에 Execute 레이블이 있는지 확인
- `_build_header(self, card_name, card_url, session_id)` (줄 356): 슬랙 메시지 헤더 생성
- `_handle_new_card(self, card, list_key)` (줄 372): 새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행
- `_build_task_context_hint(self)` (줄 493): 태스크 컨텍스트 힌트 생성
- `_build_to_go_prompt(self, card, has_execute)` (줄 500): To Go 카드용 프롬프트 생성
- `build_reaction_execute_prompt(self, info)` (줄 538): 리액션 기반 실행용 프롬프트 생성

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.trello.client.TrelloCard`
- `seosoyoung.trello.client.TrelloClient`
