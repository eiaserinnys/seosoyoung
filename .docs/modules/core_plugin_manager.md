# core/plugin_manager.py

> 경로: `seosoyoung/core/plugin_manager.py`

## 개요

Plugin lifecycle manager.

Handles loading, unloading, reloading of plugins and dispatching
hook chains. Priority and dependencies are explicit load() parameters.

Notification is delegated to an async callable injected at construction.
The manager does not know about Slack — it only calls the notifier.

## 클래스

### `PluginManager`
- 위치: 줄 25
- 설명: Manages plugin lifecycle and hook dispatch.

Priority and dependencies are explicit ``load()`` parameters,
not buried in plugin config dicts.

#### 메서드

- `__init__(self, notifier)` (줄 32): 
- `plugins(self)` (줄 42): Snapshot of currently loaded plugins.
- `async load(self, module, config, priority, depends_on)` (줄 46): Load a plugin from a dotted module path.
- `async unload(self, name)` (줄 131): Unload a plugin by name.
- `async reload(self, name)` (줄 173): Reload a plugin, preserving config, priority, and dependencies.
- `async dispatch(self, hook_name, context)` (줄 210): Dispatch a hook through registered handlers in priority order.
- `async notify_startup_summary(self)` (줄 246): Send a summary of all loaded plugins.
- `async _notify(self, message)` (줄 260): Send a notification if a notifier is configured.
- `_find_plugin_class(mod)` (줄 274): Find the single Plugin subclass in a module.
- `_cleanup_module(module_path)` (줄 298): Remove a module and its submodules from sys.modules.

## 내부 의존성

- `seosoyoung.core.hooks.HookContext`
- `seosoyoung.core.hooks.HookPriority`
- `seosoyoung.core.hooks.HookResult`
- `seosoyoung.core.plugin.Plugin`
