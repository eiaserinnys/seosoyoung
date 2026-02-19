"""SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.
"""

import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.config import Config
from seosoyoung.logging_config import setup_logging
from seosoyoung.auth import check_permission, get_user_role
from seosoyoung.claude.session import SessionManager, SessionRuntime
from seosoyoung.claude.executor import ClaudeExecutor
from seosoyoung.slack.helpers import upload_file_to_slack, send_long_message
from seosoyoung.handlers import register_all_handlers
from seosoyoung.handlers.actions import send_restart_confirmation
from seosoyoung.restart import RestartManager, RestartType
from seosoyoung.trello.watcher import TrelloWatcher
from seosoyoung.trello.list_runner import ListRunner
from seosoyoung.handlers.channel_collector import ChannelMessageCollector
from seosoyoung.handlers.mention_tracker import MentionTracker
from seosoyoung.memory.channel_store import ChannelStore
from seosoyoung.memory.channel_intervention import InterventionHistory
from seosoyoung.memory.channel_observer import ChannelObserver, DigestCompressor
from seosoyoung.memory.channel_scheduler import ChannelDigestScheduler

# 로깅 설정
logger = setup_logging()

# Slack 앱 초기화
app = App(token=Config.SLACK_BOT_TOKEN, logger=logger)

# 세션 관리
session_manager = SessionManager()
session_runtime = SessionRuntime()

# Trello 워처 (나중에 초기화)
trello_watcher: TrelloWatcher | None = None

# 리스트 러너 (리스트 정주행 기능)
list_runner: ListRunner | None = None


def _perform_restart(restart_type: RestartType) -> None:
    """실제 재시작 수행"""
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
session_runtime.set_on_all_sessions_stopped(_check_restart_on_session_stop)

# Claude 실행기
executor = ClaudeExecutor(
    session_manager=session_manager,
    get_session_lock=session_runtime.get_session_lock,
    mark_session_running=session_runtime.mark_session_running,
    mark_session_stopped=session_runtime.mark_session_stopped,
    get_running_session_count=session_runtime.get_running_session_count,
    restart_manager=restart_manager,
    upload_file_to_slack=upload_file_to_slack,
    send_long_message=send_long_message,
    send_restart_confirmation=send_restart_confirmation,
    trello_watcher_ref=lambda: trello_watcher,
    list_runner_ref=lambda: list_runner,
)

# 멘션 트래커 (채널 관찰자-멘션 핸들러 통합용)
_mention_tracker = MentionTracker()

# 채널 관찰 시스템 초기화
_channel_store: ChannelStore | None = None
_channel_collector: ChannelMessageCollector | None = None
_channel_cooldown: InterventionHistory | None = None
_channel_observer: ChannelObserver | None = None
_channel_compressor: DigestCompressor | None = None
_channel_scheduler: ChannelDigestScheduler | None = None

if Config.CHANNEL_OBSERVER_ENABLED and Config.CHANNEL_OBSERVER_CHANNELS:
    _channel_store = ChannelStore(base_dir=Config.get_memory_path())
    _channel_collector = ChannelMessageCollector(
        store=_channel_store,
        target_channels=Config.CHANNEL_OBSERVER_CHANNELS,
        mention_tracker=_mention_tracker,
    )
    _channel_cooldown = InterventionHistory(
        base_dir=Config.get_memory_path(),
    )
    if Config.CHANNEL_OBSERVER_API_KEY:
        _channel_observer = ChannelObserver(
            api_key=Config.CHANNEL_OBSERVER_API_KEY,
            model=Config.CHANNEL_OBSERVER_MODEL,
        )
        _channel_compressor = DigestCompressor(
            api_key=Config.CHANNEL_OBSERVER_API_KEY,
            model=Config.CHANNEL_OBSERVER_COMPRESSOR_MODEL,
        )
    if _channel_observer and Config.CHANNEL_OBSERVER_PERIODIC_SEC > 0:
        _channel_scheduler = ChannelDigestScheduler(
            store=_channel_store,
            observer=_channel_observer,
            compressor=_channel_compressor,
            cooldown=_channel_cooldown,
            slack_client=app.client,
            channels=Config.CHANNEL_OBSERVER_CHANNELS,
            interval_sec=Config.CHANNEL_OBSERVER_PERIODIC_SEC,
            buffer_threshold=Config.CHANNEL_OBSERVER_BUFFER_THRESHOLD,
            digest_max_tokens=Config.CHANNEL_OBSERVER_DIGEST_MAX_TOKENS,
            digest_target_tokens=Config.CHANNEL_OBSERVER_DIGEST_TARGET_TOKENS,
            debug_channel=Config.CHANNEL_OBSERVER_DEBUG_CHANNEL,
            intervention_threshold=Config.CHANNEL_OBSERVER_INTERVENTION_THRESHOLD,
            mention_tracker=_mention_tracker,
        )
    logger.info(
        f"채널 관찰 시스템 초기화: channels={Config.CHANNEL_OBSERVER_CHANNELS}, "
        f"threshold={Config.CHANNEL_OBSERVER_INTERVENTION_THRESHOLD}, "
        f"periodic={Config.CHANNEL_OBSERVER_PERIODIC_SEC}s"
    )

# 핸들러 의존성
dependencies = {
    "session_manager": session_manager,
    "restart_manager": restart_manager,
    "get_session_lock": session_runtime.get_session_lock,
    "get_running_session_count": session_runtime.get_running_session_count,
    "run_claude_in_session": executor.run,
    "check_permission": check_permission,
    "get_user_role": get_user_role,
    "send_restart_confirmation": send_restart_confirmation,
    "trello_watcher_ref": lambda: trello_watcher,
    "list_runner_ref": lambda: list_runner,
    "channel_collector": _channel_collector,
    "channel_store": _channel_store,
    "channel_observer": _channel_observer,
    "channel_compressor": _channel_compressor,
    "channel_cooldown": _channel_cooldown,
    "mention_tracker": _mention_tracker,
}

# 핸들러 등록
register_all_handlers(app, dependencies)


def notify_startup():
    """봇 시작 알림"""
    channel = Config.TRELLO_NOTIFY_CHANNEL
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text="안녕하세요, 서소영입니다.")
            logger.info(f"시작 알림 전송: {channel}")
        except Exception as e:
            logger.error(f"시작 알림 실패: {e}")


def notify_shutdown():
    """봇 종료 알림"""
    channel = Config.TRELLO_NOTIFY_CHANNEL
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text="다음에 또 뵙겠습니다, 안녕히 계세요.")
            logger.info(f"종료 알림 전송: {channel}")
        except Exception as e:
            logger.error(f"종료 알림 실패: {e}")


def start_trello_watcher():
    """Trello 워처 시작"""
    global trello_watcher

    if not Config.TRELLO_API_KEY or not Config.TRELLO_TOKEN:
        logger.info("Trello API 키가 설정되지 않아 워처를 시작하지 않습니다.")
        return

    trello_watcher = TrelloWatcher(
        slack_client=app.client,
        session_manager=session_manager,
        claude_runner_factory=executor.run,
        get_session_lock=session_runtime.get_session_lock,
        poll_interval=15,
        list_runner_ref=lambda: list_runner,
    )
    trello_watcher.start()
    logger.info("Trello 워처 시작됨")


def start_list_runner():
    """리스트 러너 초기화"""
    global list_runner

    from pathlib import Path
    data_dir = Path(Config.get_session_path()).parent / "data"
    list_runner = ListRunner(data_dir=data_dir)
    logger.info("리스트 러너 초기화 완료")


def init_bot_user_id():
    """봇 사용자 ID 초기화"""
    try:
        auth_result = app.client.auth_test()
        Config.BOT_USER_ID = auth_result["user_id"]
        logger.info(f"BOT_USER_ID: {Config.BOT_USER_ID}")
    except Exception as e:
        logger.error(f"봇 ID 조회 실패: {e}")


if __name__ == "__main__":
    logger.info("SeoSoyoung 봇을 시작합니다...")
    logger.info(f"LOG_PATH: {Config.get_log_path()}")
    logger.info(f"ADMIN_USERS: {Config.ADMIN_USERS}")
    logger.info(f"ALLOWED_USERS: {Config.ALLOWED_USERS}")
    logger.info(f"DEBUG: {Config.DEBUG}")
    init_bot_user_id()
    notify_startup()
    start_trello_watcher()
    start_list_runner()
    if _channel_scheduler:
        _channel_scheduler.start()
    handler = SocketModeHandler(app, Config.SLACK_APP_TOKEN)
    handler.start()
