# memory/plugin.py

> 경로: `seosoyoung/slackbot/plugins/memory/plugin.py`

## 개요

Memory plugin.

Observational Memory injection and observation triggering.
All configuration comes from memory.yaml, not from Config
singleton or environment variables.

## 클래스

### `MemoryPlugin` (Plugin)
- 위치: 줄 22
- 설명: Observational Memory plugin.

Injects memory context before Claude execution (before_execute)
and triggers observation pipeline after execution (after_execute).

No self.enabled flag — if loaded, it's active.

#### 메서드

- `async on_load(self, config)` (줄 37): 
- `async on_unload(self)` (줄 76): 
- `register_hooks(self)` (줄 79): 
- `async _on_before_execute(self, ctx)` (줄 87): Inject memory context into the prompt before Claude execution.
- `async _on_after_execute(self, ctx)` (줄 132): Trigger observation pipeline after Claude execution.
- `on_compact_flag(self, thread_ts)` (줄 165): PreCompact 훅에서 OM inject 플래그 설정.
- `_prepare_injection(self, thread_ts, channel, session_id, prompt, channel_observer_channels)` (줄 182): OM 메모리 주입을 준비합니다.
- `_create_or_load_debug_anchor(self, thread_ts, session_id, store, prompt)` (줄 254): 디버그 앵커 메시지를 생성하거나 기존 앵커를 로드합니다.
- `_send_injection_debug_log(self, thread_ts, result, anchor_ts)` (줄 299): 디버그 이벤트: 주입 정보를 슬랙에 발송.
- `_trigger_observation(self, thread_ts, user_id, prompt, collected_messages, anchor_ts)` (줄 382): 관찰 파이프라인을 별도 스레드에서 비동기로 트리거.

## 내부 의존성

- `seosoyoung.core.hooks.HookContext`
- `seosoyoung.core.hooks.HookResult`
- `seosoyoung.core.plugin.Plugin`
- `seosoyoung.core.plugin.PluginMeta`
