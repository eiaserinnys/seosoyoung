# seosoyoung/main.py

> 경로: `seosoyoung/main.py`

## 개요

SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.

## 함수

### `_perform_restart(restart_type)`
- 위치: 줄 39
- 설명: 실제 재시작 수행

### `_check_restart_on_session_stop()`
- 위치: 줄 52
- 설명: 세션 종료 시 재시작 확인

### `notify_startup()`
- 위치: 줄 94
- 설명: 봇 시작 알림

### `notify_shutdown()`
- 위치: 줄 105
- 설명: 봇 종료 알림

### `start_trello_watcher()`
- 위치: 줄 116
- 설명: Trello 워처 시작

### `start_list_runner()`
- 위치: 줄 136
- 설명: 리스트 러너 초기화

### `init_bot_user_id()`
- 위치: 줄 146
- 설명: 봇 사용자 ID 초기화

## 내부 의존성

- `seosoyoung.auth.check_permission`
- `seosoyoung.auth.get_user_role`
- `seosoyoung.claude.executor.ClaudeExecutor`
- `seosoyoung.claude.session.SessionManager`
- `seosoyoung.claude.session.SessionRuntime`
- `seosoyoung.config.Config`
- `seosoyoung.handlers.actions.send_restart_confirmation`
- `seosoyoung.handlers.register_all_handlers`
- `seosoyoung.logging_config.setup_logging`
- `seosoyoung.restart.RestartManager`
- `seosoyoung.restart.RestartType`
- `seosoyoung.slack.helpers.send_long_message`
- `seosoyoung.slack.helpers.upload_file_to_slack`
- `seosoyoung.trello.list_runner.ListRunner`
- `seosoyoung.trello.watcher.TrelloWatcher`
