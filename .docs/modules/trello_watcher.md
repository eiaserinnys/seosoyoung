# trello/watcher.py

> 경로: `seosoyoung/trello/watcher.py`

## 개요

Trello 워처 - To Go 리스트 감시 및 처리

## 클래스

### `TrackedCard`
- 위치: 줄 19
- 설명: 추적 중인 카드 정보 (To Go 리스트 감시용)

### `ThreadCardInfo`
- 위치: 줄 35
- 설명: 스레드 ↔ 카드 매핑 정보 (리액션 처리용)

Claude 세션이 시작된 슬랙 스레드와 트렐로 카드의 연결을 유지합니다.
TrackedCard와 달리 Claude 실행 완료 후에도 유지되어 리액션 기반 실행을 지원합니다.

### `TrelloWatcher`
- 위치: 줄 51
- 설명: Trello 리스트 감시자

To Go 리스트에 새 카드가 들어오면:
1. 카드를 In Progress로 이동
2. Slack에 알림 메시지 전송
3. Claude Code 세션 시작
4. Execute 레이블 유무에 따라:
   - 없음: 계획 수립 후 Backlog로 이동
   - 있음: 작업 실행 후 Review/Blocked로 이동

#### 메서드

- `__init__(self, slack_client, session_manager, claude_runner_factory, get_session_lock, notify_channel, poll_interval, data_dir, list_runner_ref)` (줄 63): Args:
- `_load_tracked(self)` (줄 117): 추적 상태 로드
- `_save_tracked(self)` (줄 137): 추적 상태 저장
- `_load_thread_cards(self)` (줄 148): 스레드-카드 매핑 로드
- `_save_thread_cards(self)` (줄 159): 스레드-카드 매핑 저장
- `_register_thread_card(self, tracked)` (줄 170): 스레드-카드 매핑 등록
- `_untrack_card(self, card_id)` (줄 186): To Go 추적에서 카드 제거 (Claude 실행 완료 시 호출)
- `update_thread_card_session_id(self, thread_ts, session_id)` (줄 193): ThreadCardInfo의 session_id 업데이트
- `get_tracked_by_thread_ts(self, thread_ts)` (줄 209): thread_ts로 ThreadCardInfo 조회 (리액션 처리용)
- `update_tracked_session_id(self, card_id, session_id)` (줄 220): TrackedCard의 session_id 업데이트
- `start(self)` (줄 236): 워처 시작 (백그라운드 스레드)
- `stop(self)` (줄 251): 워처 중지
- `pause(self)` (줄 258): 워처 일시 중단 (재시작 대기용)
- `resume(self)` (줄 264): 워처 재개
- `is_paused(self)` (줄 271): 일시 중단 상태인지 확인
- `_run(self)` (줄 276): 워처 메인 루프
- `_poll(self)` (줄 287): 리스트 폴링
- `_cleanup_stale_tracked(self, current_cards)` (줄 322): 만료된 _tracked 항목 정리 (방안 A + C)
- `_check_review_list_for_completion(self)` (줄 351): Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동
- `_add_spinner_prefix(self, card)` (줄 377): 카드 제목에 🌀 prefix 추가
- `_remove_spinner_prefix(self, card_id, card_name)` (줄 384): 카드 제목에서 🌀 prefix 제거
- `_has_execute_label(self, card)` (줄 391): 카드에 Execute 레이블이 있는지 확인
- `_has_run_list_label(self, card)` (줄 398): 카드에 🏃 Run List 레이블이 있는지 확인
- `_get_run_list_label_id(self, card)` (줄 405): 카드에서 🏃 Run List 레이블 ID 반환
- `_build_header(self, card_name, card_url, session_id)` (줄 412): 슬랙 메시지 헤더 생성
- `_get_dm_or_notify_channel(self)` (줄 428): DM 대상 사용자가 설정되어 있으면 DM 채널 ID를, 없으면 notify_channel을 반환
- `_open_dm_thread(self, card_name, card_url)` (줄 443): DM 채널을 열고 앵커 메시지를 전송하여 DM 스레드를 생성
- `_handle_new_card(self, card, list_key)` (줄 480): 새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행
- `build_reaction_execute_prompt(self, info)` (줄 590): 하위 호환: PromptBuilder에 위임
- `_build_to_go_prompt(self, card, has_execute)` (줄 594): 하위 호환: PromptBuilder에 위임
- `_spawn_claude_thread(self)` (줄 598): Claude 실행 스레드 스포닝 (공통)
- `_check_run_list_labels(self)` (줄 674): 🏃 Run List 레이블을 가진 카드 감지 및 리스트 정주행 시작
- `_preemptive_compact(self, thread_ts, channel, card_name)` (줄 712): 카드 완료 후 선제적 컨텍스트 컴팩트
- `_start_list_run(self, list_id, list_name, cards)` (줄 744): 리스트 정주행 시작
- `_process_list_run_card(self, session_id, thread_ts, run_channel)` (줄 812): 리스트 정주행 카드 처리

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.trello.client.TrelloCard`
- `seosoyoung.trello.client.TrelloClient`
- `seosoyoung.trello.prompt_builder.PromptBuilder`
