# core/plugin.py

> 경로: `seosoyoung/core/plugin.py`

## 개요

Plugin base class and metadata.

Plugins are self-describing units of functionality. Each plugin declares
its identity via PluginMeta and registers hook handlers.

Priority and dependencies are NOT part of plugin metadata; they belong
to the plugin registry (plugins.yaml) and are passed as explicit
parameters to PluginManager.load().

## 클래스

### `PluginMeta`
- 위치: 줄 22
- 설명: Immutable plugin identity.

Contains only name, version, and description.
No priority, no dependencies — those are registry concerns.

### `Plugin` (ABC)
- 위치: 줄 37
- 설명: Base class for all plugins.

Subclasses must:
  - Set ``meta`` as a class attribute or in ``__init__``.
  - Implement ``on_load()`` and ``on_unload()``.
  - Optionally override ``register_hooks()`` to participate in hook chains.

#### 메서드

- `async on_load(self, config)` (줄 49): Called when the plugin is loaded.
- `async on_unload(self)` (줄 56): Called when the plugin is about to be unloaded.
- `register_hooks(self)` (줄 59): Return a mapping of hook_name -> async handler.
