# seosoyoung/main.py

> 경로: `seosoyoung/main.py`

## 개요

SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.

## 함수

### `_perform_restart(restart_type)`
- 위치: 줄 47
- 설명: 실제 재시작 수행

모든 ClaudeSDKClient를 정리한 후 프로세스를 종료합니다.
이로써 고아 프로세스(Claude Code CLI)가 남지 않습니다.

### `_check_restart_on_session_stop()`
- 위치: 줄 71
- 설명: 세션 종료 시 재시작 확인

### `_signal_handler(signum, frame)`
- 위치: 줄 81
- 설명: 시그널 수신 시 graceful shutdown 수행

SIGTERM, SIGINT 수신 시 모든 클라이언트를 정리하고 프로세스를 종료합니다.

### `_init_channel_observer(slack_client, mention_tracker)`
- 위치: 줄 116
- 설명: 채널 관찰 시스템 초기화

Returns:
    tuple: (store, collector, cooldown, observer, compressor, scheduler)
           비활성화 시 모두 None.

### `_build_dependencies()`
- 위치: 줄 183
- 설명: 핸들러 의존성 딕셔너리 빌드

### `notify_startup()`
- 위치: 줄 209
- 설명: 봇 시작 알림

### `notify_shutdown()`
- 위치: 줄 220
- 설명: 봇 종료 알림

### `start_trello_watcher()`
- 위치: 줄 231
- 설명: Trello 워처 시작

### `start_list_runner()`
- 위치: 줄 251
- 설명: 리스트 러너 초기화

### `init_bot_user_id()`
- 위치: 줄 261
- 설명: 봇 사용자 ID 초기화

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
- `seosoyoung.slackbot.memory.channel_intervention.InterventionHistory`
- `seosoyoung.slackbot.memory.channel_observer.ChannelObserver`
- `seosoyoung.slackbot.memory.channel_observer.DigestCompressor`
- `seosoyoung.slackbot.memory.channel_scheduler.ChannelDigestScheduler`
- `seosoyoung.slackbot.memory.channel_store.ChannelStore`
- `seosoyoung.slackbot.restart.RestartManager`
- `seosoyoung.slackbot.restart.RestartType`
- `seosoyoung.slackbot.slack.helpers.send_long_message`
- `seosoyoung.slackbot.trello.list_runner.ListRunner`
- `seosoyoung.slackbot.trello.watcher.TrelloWatcher`
