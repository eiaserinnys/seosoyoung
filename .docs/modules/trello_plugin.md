# trello/plugin.py

> 경로: `seosoyoung/slackbot/plugins/trello/plugin.py`

## 개요

Trello plugin.

Trello watcher, list runner, reaction-based execution, and
resume command handling. All configuration comes from trello.yaml,
not from Config singleton or environment variables.

## 클래스

### `TrelloPlugin` (Plugin)
- 위치: 줄 31
- 설명: Trello watcher and card management plugin.

Manages TrelloWatcher lifecycle and handles reaction-based
execution and list-run resume commands.

#### 메서드

- `async on_load(self, config)` (줄 44): 
- `async on_unload(self)` (줄 74): 
- `register_hooks(self)` (줄 79): 
- `async _on_startup(self, ctx)` (줄 89): Receive runtime dependencies and start watcher.
- `async _on_shutdown(self, ctx)` (줄 124): Stop watcher on shutdown.
- `async _on_reaction(self, ctx)` (줄 130): Handle execute emoji reaction on trello watcher threads.
- `async _on_command(self, ctx)` (줄 326): Handle resume list-run command.

## 함수

### `_is_resume_command(command)`
- 위치: 줄 380
- 설명: Check if the command matches a resume list-run pattern.

## 내부 의존성

- `seosoyoung.core.hooks.HookContext`
- `seosoyoung.core.hooks.HookResult`
- `seosoyoung.core.plugin.Plugin`
- `seosoyoung.core.plugin.PluginMeta`
- `seosoyoung.slackbot.plugins.trello.client.TrelloClient`
- `seosoyoung.slackbot.plugins.trello.prompt_builder.PromptBuilder`
