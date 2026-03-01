# channel_observer/plugin.py

> 경로: `seosoyoung/slackbot/plugins/channel_observer/plugin.py`

## 개요

Channel Observer plugin.

Collects channel messages, runs digest/judge pipelines, and
manages periodic digest scheduling. All configuration comes
from channel_observer.yaml, not from Config singleton or
environment variables.

## 클래스

### `ChannelObserverPlugin` (Plugin)
- 위치: 줄 25
- 설명: Channel observation and digest management plugin.

Collects messages from monitored channels via on_message hook,
triggers digest/judge pipelines when thresholds are met, and
runs a periodic scheduler via on_startup hook.

No self.enabled flag — if loaded, it's active.
PluginMeta에 dependencies 없음 — plugins.yaml depends_on이 정본.

#### 메서드

- `async on_load(self, config)` (줄 42): 
- `async on_unload(self)` (줄 85): 
- `register_hooks(self)` (줄 90): 
- `async _on_startup(self, ctx)` (줄 99): Initialize runtime components and start periodic scheduler.
- `async _on_shutdown(self, ctx)` (줄 187): Stop scheduler on shutdown.
- `async _on_message(self, ctx)` (줄 195): Collect channel messages and trigger digest pipeline.
- `collect_reaction(self, event, action)` (줄 232): Collect reaction events for channel observation.
- `store(self)` (줄 244): ChannelStore instance (for session_context hybrid mode).
- `channels(self)` (줄 249): Monitored channel IDs.
- `_contains_trigger_word(self, text)` (줄 255): 텍스트에 트리거 워드가 포함되어 있는지 확인합니다.
- `_maybe_trigger_digest(self, channel_id, client)` (줄 264): pending 토큰이 threshold_A 이상이면 파이프라인을 실행합니다.
- `_send_collect_log(self, client, channel_id, event)` (줄 322): 수집 디버그 로그를 전송합니다.

## 내부 의존성

- `seosoyoung.core.hooks.HookContext`
- `seosoyoung.core.hooks.HookResult`
- `seosoyoung.core.plugin.Plugin`
- `seosoyoung.core.plugin.PluginMeta`
