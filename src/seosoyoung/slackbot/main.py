"""SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.
"""

import os
import signal
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.logging_config import setup_logging
from seosoyoung.slackbot.auth import check_permission, get_user_role
from pathlib import Path
from seosoyoung.slackbot.claude.session import SessionManager, SessionRuntime
from seosoyoung.slackbot.claude.executor import ClaudeExecutor
from seosoyoung.slackbot.slack.helpers import send_long_message
from seosoyoung.slackbot.slack.formatting import update_message
from seosoyoung.slackbot.handlers import register_all_handlers
from seosoyoung.slackbot.handlers.actions import send_restart_confirmation
from seosoyoung.core.plugin_manager import PluginManager
from seosoyoung.core.plugin_config import load_plugin_registry, load_plugin_config
from seosoyoung.slackbot.restart import RestartManager, RestartType
from seosoyoung.slackbot.marker_parser import parse_markers
from seosoyoung.slackbot.handlers.mention_tracker import MentionTracker

# 로깅 설정
logger = setup_logging()

# Slack 앱 초기화
app = App(token=Config.slack.bot_token, logger=logger)

# 세션 관리
session_manager = SessionManager(session_dir=Path(Config.get_session_path()))
session_runtime = SessionRuntime()

# Plugin-managed runtime references (populated via on_startup hook)
_trello_refs: dict = {"watcher": None, "list_runner": None}
_channel_refs: dict = {
    "channel_collector": None,
    "channel_store": None,
    "channel_observer": None,
    "channel_compressor": None,
    "channel_cooldown": None,
    "channel_observer_channels": [],
}


def _perform_restart(restart_type: RestartType) -> None:
    """재시작 수행"""
    notify_shutdown()
    os._exit(restart_type.value)


# 재시작 관리자
restart_manager = RestartManager(
    get_running_count=session_runtime.get_running_session_count,
    on_restart=_perform_restart
)


def _check_restart_on_session_stop():
    """세션 종료 시 재시작 확인"""
    if restart_manager.is_pending:
        restart_manager.check_and_restart_if_ready()


# 세션 종료 콜백 설정
session_runtime.set_on_session_stopped(_check_restart_on_session_stop)


_GRACEFUL_SHUTDOWN_TIMEOUT = 300  # 최대 대기 시간(초) — 사용자 응답 대기 포함


def _shutdown_with_session_wait(restart_type: RestartType, source: str) -> None:
    """활성 세션을 확인하고, 있으면 사용자에게 팝업으로 확인 후 종료.

    세션이 없으면 즉시 종료.
    세션이 있으면 Slack 팝업으로 사용자에게 확인을 받는다.
    - "지금 종료": 즉시 os._exit
    - "세션 완료 후 종료": pending 등록, 세션 0 도달 시 자동 종료
    최대 _GRACEFUL_SHUTDOWN_TIMEOUT 초 초과 시 강제 종료 (타임아웃 안전망).

    Args:
        restart_type: 재시작 유형
        source: 로그용 호출 출처 (예: "SIGTERM", "HTTP /shutdown")
    """
    logger.info(f"[{source}] graceful shutdown 시작")

    running_count = session_runtime.get_running_session_count()
    if running_count == 0:
        logger.info(f"[{source}] 활성 세션 없음 — 즉시 종료")
        _perform_restart(restart_type)
        return

    # 활성 세션 있음 — 사용자에게 팝업으로 확인
    logger.info(
        f"[{source}] 활성 세션 {running_count}개, 사용자 확인 팝업 전송"
    )
    channel = Config.slack.notify_channel
    if channel:
        from seosoyoung.slackbot.handlers.actions import send_deploy_shutdown_popup
        send_deploy_shutdown_popup(
            client=app.client,
            channel=channel,
            running_count=running_count,
            restart_type=restart_type,
        )
    else:
        # notify_channel 미설정 시 팝업 불가 → 세션 대기 모드로 진입
        logger.warning(
            f"[{source}] notify_channel 미설정, 세션 대기 모드로 진입"
        )
        restart_manager.request_system_shutdown(restart_type)

    # 타임아웃 안전망: 사용자 응답이 없으면 강제 종료
    def _force_shutdown():
        logger.warning(
            f"[{source}] 타임아웃 {_GRACEFUL_SHUTDOWN_TIMEOUT}초 초과 — 강제 종료"
        )
        _perform_restart(restart_type)

    timer = threading.Timer(_GRACEFUL_SHUTDOWN_TIMEOUT, _force_shutdown)
    timer.daemon = True
    timer.start()


def _signal_handler(signum, frame):
    """시그널 수신 시 graceful shutdown 수행

    SIGTERM, SIGINT 수신 시 활성 세션이 있으면 완료를 기다린 후 종료합니다.
    최대 _GRACEFUL_SHUTDOWN_TIMEOUT 초 대기 후 강제 종료합니다.
    """
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    logger.info(f"시그널 수신: {sig_name}")
    _shutdown_with_session_wait(RestartType.RESTART, sig_name)


# 시그널 핸들러 등록
# Windows에서는 SIGTERM이 제한적이지만, SIGINT(Ctrl+C)는 지원됨
signal.signal(signal.SIGINT, _signal_handler)
# SIGTERM은 Unix 계열에서만 완전 지원, Windows에서는 TerminateProcess로 대체됨
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _signal_handler)


# Claude 실행기
executor = ClaudeExecutor(
    session_manager=session_manager,
    session_runtime=session_runtime,
    restart_manager=restart_manager,
    send_long_message=send_long_message,
    send_restart_confirmation=send_restart_confirmation,
    update_message_fn=update_message,
    role_tools=Config.auth.role_tools,
    soul_url=Config.claude.soul_url,
    soul_token=Config.claude.soul_token,
    soul_client_id=Config.claude.soul_client_id,
    restart_type_update=RestartType.UPDATE,
    restart_type_restart=RestartType.RESTART,
    trello_watcher_ref=lambda: _trello_refs["watcher"],
    list_runner_ref=lambda: _trello_refs["list_runner"],
    parse_markers_fn=parse_markers,
)

# 멘션 트래커 (채널 관찰자-멘션 핸들러 통합용)
_mention_tracker = MentionTracker()


# -- Plugin system -----------------------------------------------------------

async def _slack_notifier(message: str) -> None:
    """PluginManager 알림을 Slack에 전송."""
    channel = Config.slack.notify_channel
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text=message)
        except Exception as e:
            logger.warning(f"플러그인 알림 전송 실패: {e}")


plugin_manager = PluginManager(notifier=_slack_notifier)


def _load_plugins() -> None:
    """plugins.yaml 레지스트리에서 플러그인을 로드합니다."""
    from seosoyoung.utils.async_bridge import run_in_new_loop

    base_dir = Path(__file__).resolve().parent.parent.parent.parent  # project root
    registry_path = base_dir / "plugins" / "plugins.yaml"
    registry = load_plugin_registry(registry_path)

    if not registry:
        logger.info("플러그인 레지스트리가 비어있습니다.")
        return

    _ENTRY_REQUIRED = ("config", "priority")

    async def _load_all():
        for entry in registry:
            name = entry["name"]
            missing = [f for f in _ENTRY_REQUIRED if f not in entry]
            if missing:
                logger.error(
                    "플러그인 로드 스킵 (%s): plugins.yaml에 필수 필드 누락 %s",
                    name, missing,
                )
                continue

            try:
                config_path = base_dir / entry["config"]
                config = load_plugin_config(config_path)

                await plugin_manager.load(
                    module=entry["module"],
                    config=config,
                    priority=entry["priority"],
                    depends_on=entry.get("depends_on", []),
                )
            except Exception as e:
                logger.error(f"플러그인 로드 실패 ({name}): {e}")

        await plugin_manager.notify_startup_summary()

    run_in_new_loop(_load_all())


def _get_memory_plugin():
    """MemoryPlugin 인스턴스를 반환합니다."""
    return plugin_manager.plugins.get("memory")


def _build_dependencies():
    """핸들러 의존성 딕셔너리 빌드"""
    return {
        "session_manager": session_manager,
        "restart_manager": restart_manager,
        "get_session_lock": session_runtime.get_session_lock,
        "get_running_session_count": session_runtime.get_running_session_count,
        "run_claude_in_session": executor.run,
        "check_permission": check_permission,
        "get_user_role": get_user_role,
        "send_restart_confirmation": send_restart_confirmation,
        "trello_watcher_ref": lambda: _trello_refs["watcher"],
        "list_runner_ref": lambda: _trello_refs["list_runner"],
        # Channel observer refs (populated by plugin on_startup)
        "channel_collector": lambda: _channel_refs["channel_collector"],
        "channel_store": lambda: _channel_refs["channel_store"],
        "channel_observer_channels": lambda: _channel_refs["channel_observer_channels"],
        "mention_tracker": _mention_tracker,
        # 프레젠테이션 레이어 콜백 (호출부에서 사용)
        "update_message_fn": update_message,
        "plugin_manager": plugin_manager,
    }


# 핸들러 등록
register_all_handlers(app, _build_dependencies())


def notify_startup():
    """봇 시작 알림"""
    channel = Config.slack.notify_channel
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text="안녕하세요, 서소영입니다.")
            logger.info(f"시작 알림 전송: {channel}")
        except Exception as e:
            logger.error(f"시작 알림 실패: {e}")


def notify_shutdown():
    """봇 종료 알림"""
    channel = Config.slack.notify_channel
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text="다음에 또 뵙겠습니다, 안녕히 계세요.")
            logger.info(f"종료 알림 전송: {channel}")
        except Exception as e:
            logger.error(f"종료 알림 실패: {e}")


def _dispatch_plugin_startup():
    """Dispatch on_startup hook to all loaded plugins.

    Plugins return runtime references (e.g. watcher, list_runner,
    channel_store, channel_collector) which are stored for handler access.
    """
    from seosoyoung.utils.async_bridge import run_in_new_loop
    from seosoyoung.core.context import create_hook_context

    ctx = create_hook_context(
        "on_startup",
        slack_client=app.client,
        session_manager=session_manager,
        session_runtime=session_runtime,
        claude_runner_factory=executor.run,
        get_session_lock=session_runtime.get_session_lock,
        restart_manager=restart_manager,
        update_message_fn=update_message,
        data_dir=Path(Config.get_session_path()).parent / "data",
        mention_tracker=_mention_tracker,
        bot_user_id=Config.slack.bot_user_id or "",
    )
    ctx = run_in_new_loop(plugin_manager.dispatch("on_startup", ctx))

    # Update refs from plugin results
    for result in ctx.results:
        if isinstance(result, dict):
            # Trello plugin refs
            if "watcher" in result:
                _trello_refs["watcher"] = result["watcher"]
            if "list_runner" in result:
                _trello_refs["list_runner"] = result["list_runner"]
            # Channel observer plugin refs
            for key in _channel_refs:
                if key in result:
                    _channel_refs[key] = result[key]


def init_bot_user_id():
    """봇 사용자 ID 초기화"""
    try:
        auth_result = app.client.auth_test()
        Config.slack.bot_user_id = auth_result["user_id"]
        logger.info(f"BOT_USER_ID: {Config.slack.bot_user_id}")
    except Exception as e:
        logger.error(f"봇 ID 조회 실패: {e}")


def main():
    """봇 메인 진입점"""
    logger.info("SeoSoyoung 봇을 시작합니다...")
    logger.info(f"LOG_PATH: {Config.get_log_path()}")
    logger.info(f"ADMIN_USERS: {Config.auth.admin_users}")
    logger.info(f"ALLOWED_USERS: {Config.auth.allowed_users}")
    logger.info(f"DEBUG: {Config.debug}")

    # Shutdown 서버 시작 (supervisor graceful shutdown용)
    from seosoyoung.slackbot.shutdown import start_shutdown_server

    _SHUTDOWN_PORT = int(os.environ.get("SHUTDOWN_PORT", "3106"))

    def _on_shutdown_request():
        """supervisor에서 graceful shutdown 요청을 받았을 때

        활성 세션이 있으면 완료를 기다린 후 종료합니다.
        최대 _GRACEFUL_SHUTDOWN_TIMEOUT 초 대기 후 강제 종료합니다.
        """
        _shutdown_with_session_wait(RestartType.RESTART, "HTTP /shutdown")

    start_shutdown_server(_SHUTDOWN_PORT, _on_shutdown_request)
    logger.info(f"Shutdown server started on port {_SHUTDOWN_PORT}")
    init_bot_user_id()
    _load_plugins()
    _dispatch_plugin_startup()  # on_startup hooks (trello watcher, channel observer, etc.)
    notify_startup()
    handler = SocketModeHandler(app, Config.slack.app_token)
    handler.start()


if __name__ == "__main__":
    main()
