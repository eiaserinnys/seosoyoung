# slackbot/main.py

> 경로: `seosoyoung/slackbot/main.py`

## 개요

SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.

## 함수

### `_perform_restart(restart_type)`
- 위치: 줄 51
- 설명: 실제 재시작 수행

모든 ClaudeSDKClient를 정리한 후 프로세스를 종료합니다.
이로써 고아 프로세스(Claude Code CLI)가 남지 않습니다.

### `_check_restart_on_session_stop()`
- 위치: 줄 75
- 설명: 세션 종료 시 재시작 확인

### `_shutdown_with_session_wait(restart_type, source)`
- 위치: 줄 88
- 설명: 활성 세션을 확인하고, 있으면 사용자에게 팝업으로 확인 후 종료.

세션이 없으면 즉시 종료.
세션이 있으면 Slack 팝업으로 사용자에게 확인을 받는다.
- "지금 종료": 즉시 os._exit
- "세션 완료 후 종료": pending 등록, 세션 0 도달 시 자동 종료
최대 _GRACEFUL_SHUTDOWN_TIMEOUT 초 초과 시 강제 종료 (타임아웃 안전망).

Args:
    restart_type: 재시작 유형
    source: 로그용 호출 출처 (예: "SIGTERM", "HTTP /shutdown")

### `_signal_handler(signum, frame)`
- 위치: 줄 141
- 설명: 시그널 수신 시 graceful shutdown 수행

SIGTERM, SIGINT 수신 시 활성 세션이 있으면 완료를 기다린 후 종료합니다.
최대 _GRACEFUL_SHUTDOWN_TIMEOUT 초 대기 후 강제 종료합니다.

### `async _slack_notifier(message)`
- 위치: 줄 186
- 설명: PluginManager 알림을 Slack에 전송.

### `_load_plugins()`
- 위치: 줄 199
- 설명: plugins.yaml 레지스트리에서 플러그인을 로드합니다.

### `_get_memory_plugin()`
- 위치: 줄 242
- 설명: MemoryPlugin 인스턴스를 반환합니다.

### `_build_dependencies()`
- 위치: 줄 247
- 설명: 핸들러 의존성 딕셔너리 빌드

### `notify_startup()`
- 위치: 줄 275
- 설명: 봇 시작 알림

### `notify_shutdown()`
- 위치: 줄 286
- 설명: 봇 종료 알림

### `_dispatch_plugin_startup()`
- 위치: 줄 297
- 설명: Dispatch on_startup hook to all loaded plugins.

Plugins return runtime references (e.g. watcher, list_runner,
channel_store, channel_collector) which are stored for handler access.

### `init_bot_user_id()`
- 위치: 줄 335
- 설명: 봇 사용자 ID 초기화

### `main()`
- 위치: 줄 345
- 설명: 봇 메인 진입점

## 내부 의존성

- `seosoyoung.core.plugin_config.load_plugin_config`
- `seosoyoung.core.plugin_config.load_plugin_registry`
- `seosoyoung.core.plugin_manager.PluginManager`
- `seosoyoung.slackbot.auth.check_permission`
- `seosoyoung.slackbot.auth.get_user_role`
- `seosoyoung.slackbot.claude.agent_runner.shutdown_all_sync`
- `seosoyoung.slackbot.claude.executor.ClaudeExecutor`
- `seosoyoung.slackbot.claude.session.SessionManager`
- `seosoyoung.slackbot.claude.session.SessionRuntime`
- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.handlers.actions.send_restart_confirmation`
- `seosoyoung.slackbot.handlers.mention_tracker.MentionTracker`
- `seosoyoung.slackbot.handlers.register_all_handlers`
- `seosoyoung.slackbot.logging_config.setup_logging`
- `seosoyoung.slackbot.marker_parser.parse_markers`
- `seosoyoung.slackbot.restart.RestartManager`
- `seosoyoung.slackbot.restart.RestartType`
- `seosoyoung.slackbot.slack.formatting.update_message`
- `seosoyoung.slackbot.slack.helpers.send_long_message`
