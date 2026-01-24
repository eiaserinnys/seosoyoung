# trello/watcher.py

> 경로: `seosoyoung/trello/watcher.py`

## 개요

Trello 워처 - To Go 리스트 감시 및 처리

## 클래스

### `TrackedCard`
- 위치: 줄 19
- 설명: 추적 중인 카드 정보

### `TrelloWatcher`
- 위치: 줄 33
- 설명: Trello 리스트 감시자

To Go 리스트에 새 카드가 들어오면:
1. 카드를 In Progress로 이동
2. Slack에 알림 메시지 전송
3. Claude Code 세션 시작
4. Execute 레이블 유무에 따라:
   - 없음: 계획 수립 후 Backlog로 이동
   - 있음: 작업 실행 후 Review/Blocked로 이동

#### 메서드

- `__init__(self, slack_client, session_manager, claude_runner_factory, get_session_lock, notify_channel, poll_interval, data_dir)` (줄 45): Args:
- `_load_tracked(self)` (줄 90): 추적 상태 로드
- `_save_tracked(self)` (줄 108): 추적 상태 저장
- `get_tracked_by_thread_ts(self, thread_ts)` (줄 119): thread_ts로 TrackedCard 조회
- `update_tracked_session_id(self, card_id, session_id)` (줄 133): TrackedCard의 session_id 업데이트
- `start(self)` (줄 149): 워처 시작 (백그라운드 스레드)
- `stop(self)` (줄 164): 워처 중지
- `pause(self)` (줄 171): 워처 일시 중단 (재시작 대기용)
- `resume(self)` (줄 177): 워처 재개
- `is_paused(self)` (줄 184): 일시 중단 상태인지 확인
- `_run(self)` (줄 189): 워처 메인 루프
- `_poll(self)` (줄 200): 리스트 폴링
- `_check_review_list_for_completion(self)` (줄 240): Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동
- `_add_spinner_prefix(self, card)` (줄 265): 카드 제목에 🌀 prefix 추가
- `_remove_spinner_prefix(self, card_id, card_name)` (줄 272): 카드 제목에서 🌀 prefix 제거
- `_has_execute_label(self, card)` (줄 279): 카드에 Execute 레이블이 있는지 확인
- `_build_header(self, card_name, card_url, session_id)` (줄 286): 슬랙 메시지 헤더 생성
- `_handle_new_card(self, card, list_key)` (줄 302): 새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행
- `_build_task_context_hint(self)` (줄 418): 태스크 컨텍스트 힌트 생성
- `_build_to_go_prompt(self, card, has_execute)` (줄 425): To Go 카드용 프롬프트 생성
- `build_reaction_execute_prompt(self, tracked)` (줄 463): 리액션 기반 실행용 프롬프트 생성

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.trello.client.TrelloCard`
- `seosoyoung.trello.client.TrelloClient`
