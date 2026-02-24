# claude/result_processor.py

> 경로: `seosoyoung/claude/result_processor.py`

## 개요

Claude 실행 결과 처리

실행 결과(성공/실패/중단)에 따른 슬랙 메시지 응답 로직을 담당합니다.

## 클래스

### `ResultProcessor`
- 위치: 줄 20
- 설명: Claude 실행 결과를 처리하여 슬랙에 응답

성공/실패/중단 분기 처리, 트렐로/일반 모드 분기,
재기동 마커 및 LIST_RUN 마커 핸들링을 담당합니다.

#### 메서드

- `__init__(self, send_long_message, restart_manager, get_running_session_count, send_restart_confirmation, trello_watcher_ref)` (줄 27): 
- `replace_thinking_message(self, client, channel, old_msg_ts, new_text, new_blocks, thread_ts)` (줄 41): 사고 과정 메시지를 최종 응답으로 교체 (chat_update)
- `handle_interrupted(self, ctx)` (줄 49): 인터럽트로 중단된 실행의 사고 과정 메시지 정리
- `handle_success(self, ctx, result)` (줄 74): 성공 결과 처리
- `handle_trello_success(self, ctx, result, response, is_list_run, usage_bar)` (줄 108): 트렐로 모드 성공 처리
- `handle_normal_success(self, ctx, result, response, is_list_run, usage_bar)` (줄 152): 일반 모드(멘션) 성공 처리
- `handle_restart_marker(self, result, session, channel, thread_ts, say)` (줄 228): 재기동 마커 처리
- `handle_list_run_marker(self, list_name, channel, thread_ts, say, client)` (줄 251): LIST_RUN 마커 처리 - 정주행 시작
- `handle_error(self, ctx, error)` (줄 308): 오류 결과 처리
- `handle_exception(self, ctx, e)` (줄 331): 예외 처리

## 내부 의존성

- `seosoyoung.claude.message_formatter.build_context_usage_bar`
- `seosoyoung.claude.message_formatter.build_trello_header`
- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.slack.formatting.update_message`
