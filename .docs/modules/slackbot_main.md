# slackbot/main.py

> 경로: `seosoyoung/slackbot/main.py`

## 개요

SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.

## 함수

### `_perform_restart(restart_type)`
- 위치: 줄 52
- 설명: 실제 재시작 수행

모든 ClaudeSDKClient를 정리한 후 프로세스를 종료합니다.
이로써 고아 프로세스(Claude Code CLI)가 남지 않습니다.

### `_check_restart_on_session_stop()`
- 위치: 줄 76
- 설명: 세션 종료 시 재시작 확인

### `_shutdown_with_session_wait(restart_type, source)`
- 위치: 줄 89
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
- 위치: 줄 142
- 설명: 시그널 수신 시 graceful shutdown 수행

SIGTERM, SIGINT 수신 시 활성 세션이 있으면 완료를 기다린 후 종료합니다.
최대 _GRACEFUL_SHUTDOWN_TIMEOUT 초 대기 후 강제 종료합니다.

### `_on_compact_om_flag(thread_ts)`
- 위치: 줄 160
- 설명: PreCompact 훅에서 OM inject 플래그 설정

### `_init_channel_observer(slack_client, mention_tracker)`
- 위치: 줄 194
- 설명: 채널 관찰 시스템 초기화

Returns:
    tuple: (store, collector, cooldown, observer, compressor, scheduler)
           비활성화 시 모두 None.

### `_build_dependencies()`
- 위치: 줄 261
- 설명: 핸들러 의존성 딕셔너리 빌드

### `notify_startup()`
- 위치: 줄 292
- 설명: 봇 시작 알림

### `notify_shutdown()`
- 위치: 줄 303
- 설명: 봇 종료 알림

### `start_trello_watcher()`
- 위치: 줄 314
- 설명: Trello 워처 시작

### `start_list_runner()`
- 위치: 줄 334
- 설명: 리스트 러너 초기화

### `init_bot_user_id()`
- 위치: 줄 344
- 설명: 봇 사용자 ID 초기화

### `main()`
- 위치: 줄 354
- 설명: 봇 메인 진입점

## 내부 의존성

- `seosoyoung.slackbot.auth.check_permission`
- `seosoyoung.slackbot.auth.get_user_role`
- `seosoyoung.slackbot.claude.agent_runner.shutdown_all_sync`
- `seosoyoung.slackbot.claude.executor.ClaudeExecutor`
- `seosoyoung.slackbot.claude.session.SessionManager`
- `seosoyoung.slackbot.claude.session.SessionRuntime`
- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.handlers.actions.send_restart_confirmation`
- `seosoyoung.slackbot.handlers.channel_collector.ChannelMessageCollector`
- `seosoyoung.slackbot.handlers.mention_tracker.MentionTracker`
- `seosoyoung.slackbot.handlers.register_all_handlers`
- `seosoyoung.slackbot.logging_config.setup_logging`
- `seosoyoung.slackbot.marker_parser.parse_markers`
- `seosoyoung.slackbot.memory.channel_intervention.InterventionHistory`
- `seosoyoung.slackbot.memory.channel_observer.ChannelObserver`
- `seosoyoung.slackbot.memory.channel_observer.DigestCompressor`
- `seosoyoung.slackbot.memory.channel_scheduler.ChannelDigestScheduler`
- `seosoyoung.slackbot.memory.channel_store.ChannelStore`
- `seosoyoung.slackbot.memory.injector.prepare_memory_injection`
- `seosoyoung.slackbot.memory.injector.trigger_observation`
- `seosoyoung.slackbot.restart.RestartManager`
- `seosoyoung.slackbot.restart.RestartType`
- `seosoyoung.slackbot.slack.formatting.update_message`
- `seosoyoung.slackbot.slack.helpers.send_long_message`
- `seosoyoung.slackbot.trello.list_runner.ListRunner`
- `seosoyoung.slackbot.trello.watcher.TrelloWatcher`
