"""Slack 이벤트 핸들러 패키지"""

from seosoyoung.slackbot.handlers.mention import register_mention_handlers
from seosoyoung.slackbot.handlers.message import register_message_handlers
from seosoyoung.slackbot.handlers.actions import (
    register_action_handlers,
    register_credential_action_handlers,
)


def register_all_handlers(app, dependencies: dict):
    """모든 핸들러를 앱에 등록

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 핸들러에 필요한 의존성
            - session_manager: SessionManager
            - restart_manager: RestartManager
            - get_session_lock: callable
            - get_running_session_count: callable
            - run_claude_in_session: callable
            - trello_watcher_ref: callable (lambda: trello_watcher)
            - plugin_manager: PluginManager (플러그인 디스패치용)
    """
    register_mention_handlers(app, dependencies)
    register_message_handlers(app, dependencies)
    register_action_handlers(app, dependencies)
    register_credential_action_handlers(app, dependencies)


__all__ = [
    "register_all_handlers",
    "register_mention_handlers",
    "register_message_handlers",
    "register_action_handlers",
    "register_credential_action_handlers",
]
