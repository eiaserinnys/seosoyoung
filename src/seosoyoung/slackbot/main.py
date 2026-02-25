"""SeoSoyoung 슬랙 봇 메인

앱 초기화와 진입점만 담당합니다.
"""

import os
import signal
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.logging_config import setup_logging
from seosoyoung.slackbot.auth import check_permission, get_user_role
from pathlib import Path
from seosoyoung.slackbot.claude.session import SessionManager, SessionRuntime
from seosoyoung.slackbot.claude.executor import ClaudeExecutor
from seosoyoung.slackbot.claude.agent_runner import shutdown_all_sync
from seosoyoung.slackbot.slack.helpers import send_long_message
from seosoyoung.slackbot.slack.formatting import update_message
from seosoyoung.slackbot.handlers import register_all_handlers
from seosoyoung.slackbot.handlers.actions import send_restart_confirmation
from seosoyoung.slackbot.restart import RestartManager, RestartType
from seosoyoung.slackbot.marker_parser import parse_markers
from seosoyoung.slackbot.memory.injector import prepare_memory_injection, trigger_observation
from seosoyoung.slackbot.trello.watcher import TrelloWatcher
from seosoyoung.slackbot.trello.list_runner import ListRunner
from seosoyoung.slackbot.handlers.channel_collector import ChannelMessageCollector
from seosoyoung.slackbot.handlers.mention_tracker import MentionTracker
from seosoyoung.slackbot.memory.channel_store import ChannelStore
from seosoyoung.slackbot.memory.channel_intervention import InterventionHistory
from seosoyoung.slackbot.memory.channel_observer import ChannelObserver, DigestCompressor
from seosoyoung.slackbot.memory.channel_scheduler import ChannelDigestScheduler

# 로깅 설정
logger = setup_logging()

# Slack 앱 초기화
app = App(token=Config.slack.bot_token, logger=logger)

# 세션 관리
session_manager = SessionManager(session_dir=Path(Config.get_session_path()))
session_runtime = SessionRuntime()

# Trello 워처 (나중에 초기화)
trello_watcher: TrelloWatcher | None = None

# 리스트 러너 (리스트 정주행 기능)
list_runner: ListRunner | None = None


def _perform_restart(restart_type: RestartType) -> None:
    """실제 재시작 수행

    모든 ClaudeSDKClient를 정리한 후 프로세스를 종료합니다.
    이로써 고아 프로세스(Claude Code CLI)가 남지 않습니다.
    """
    # 모든 활성 클라이언트 종료 (고아 프로세스 방지)
    try:
        count = shutdown_all_sync()
        logger.info(f"재시작 전 {count}개 클라이언트 종료 완료")
    except Exception as e:
        logger.warning(f"클라이언트 종료 중 오류 (무시): {e}")

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


def _signal_handler(signum, frame):
    """시그널 수신 시 graceful shutdown 수행

    SIGTERM, SIGINT 수신 시 모든 클라이언트를 정리하고 프로세스를 종료합니다.
    """
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    logger.info(f"시그널 수신: {sig_name}")
    _perform_restart(RestartType.RESTART)


# 시그널 핸들러 등록
# Windows에서는 SIGTERM이 제한적이지만, SIGINT(Ctrl+C)는 지원됨
signal.signal(signal.SIGINT, _signal_handler)
# SIGTERM은 Unix 계열에서만 완전 지원, Windows에서는 TerminateProcess로 대체됨
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, _signal_handler)

def _on_compact_om_flag(thread_ts: str) -> None:
    """PreCompact 훅에서 OM inject 플래그 설정"""
    if Config.om.enabled:
        from seosoyoung.slackbot.memory.store import MemoryStore
        store = MemoryStore(Config.get_memory_path())
        record = store.get_record(thread_ts)
        if record and record.observations.strip():
            store.set_inject_flag(thread_ts)


# Claude 실행기
executor = ClaudeExecutor(
    session_manager=session_manager,
    session_runtime=session_runtime,
    restart_manager=restart_manager,
    send_long_message=send_long_message,
    send_restart_confirmation=send_restart_confirmation,
    update_message_fn=update_message,
    execution_mode=Config.claude.execution_mode,
    role_tools=Config.auth.role_tools,
    soul_url=Config.claude.soul_url,
    soul_token=Config.claude.soul_token,
    soul_client_id=Config.claude.soul_client_id,
    restart_type_update=RestartType.UPDATE,
    restart_type_restart=RestartType.RESTART,
    trello_watcher_ref=lambda: trello_watcher,
    list_runner_ref=lambda: list_runner,
    parse_markers_fn=parse_markers,
)

# 멘션 트래커 (채널 관찰자-멘션 핸들러 통합용)
_mention_tracker = MentionTracker()


def _init_channel_observer(slack_client, mention_tracker):
    """채널 관찰 시스템 초기화

    Returns:
        tuple: (store, collector, cooldown, observer, compressor, scheduler)
               비활성화 시 모두 None.
    """
    nones = (None, None, None, None, None, None)
    if not (Config.channel_observer.enabled and Config.channel_observer.channels):
        return nones

    store = ChannelStore(base_dir=Config.get_memory_path())
    collector = ChannelMessageCollector(
        store=store,
        target_channels=Config.channel_observer.channels,
        mention_tracker=mention_tracker,
    )
    cooldown = InterventionHistory(base_dir=Config.get_memory_path())

    observer = None
    compressor = None
    if Config.channel_observer.api_key:
        observer = ChannelObserver(
            api_key=Config.channel_observer.api_key,
            model=Config.channel_observer.model,
        )
        compressor = DigestCompressor(
            api_key=Config.channel_observer.api_key,
            model=Config.channel_observer.compressor_model,
        )

    scheduler = None
    if observer and Config.channel_observer.periodic_sec > 0:
        scheduler = ChannelDigestScheduler(
            store=store,
            observer=observer,
            compressor=compressor,
            cooldown=cooldown,
            slack_client=slack_client,
            channels=Config.channel_observer.channels,
            interval_sec=Config.channel_observer.periodic_sec,
            buffer_threshold=Config.channel_observer.buffer_threshold,
            digest_max_tokens=Config.channel_observer.digest_max_tokens,
            digest_target_tokens=Config.channel_observer.digest_target_tokens,
            debug_channel=Config.channel_observer.debug_channel,
            intervention_threshold=Config.channel_observer.intervention_threshold,
            mention_tracker=mention_tracker,
        )

    logger.info(
        f"채널 관찰 시스템 초기화: channels={Config.channel_observer.channels}, "
        f"threshold={Config.channel_observer.intervention_threshold}, "
        f"periodic={Config.channel_observer.periodic_sec}s"
    )
    return store, collector, cooldown, observer, compressor, scheduler


(
    _channel_store,
    _channel_collector,
    _channel_cooldown,
    _channel_observer,
    _channel_compressor,
    _channel_scheduler,
) = _init_channel_observer(app.client, _mention_tracker)


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
        "trello_watcher_ref": lambda: trello_watcher,
        "list_runner_ref": lambda: list_runner,
        "channel_collector": _channel_collector,
        "channel_store": _channel_store,
        "channel_observer": _channel_observer,
        "channel_compressor": _channel_compressor,
        "channel_cooldown": _channel_cooldown,
        "mention_tracker": _mention_tracker,
        # 프레젠테이션 레이어 콜백 (호출부에서 사용)
        "update_message_fn": update_message,
        "prepare_memory_fn": prepare_memory_injection,
        "trigger_observation_fn": trigger_observation,
        "on_compact_om_flag": _on_compact_om_flag,
    }


# 핸들러 등록
register_all_handlers(app, _build_dependencies())


def notify_startup():
    """봇 시작 알림"""
    channel = Config.trello.notify_channel
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text="안녕하세요, 서소영입니다.")
            logger.info(f"시작 알림 전송: {channel}")
        except Exception as e:
            logger.error(f"시작 알림 실패: {e}")


def notify_shutdown():
    """봇 종료 알림"""
    channel = Config.trello.notify_channel
    if channel:
        try:
            app.client.chat_postMessage(channel=channel, text="다음에 또 뵙겠습니다, 안녕히 계세요.")
            logger.info(f"종료 알림 전송: {channel}")
        except Exception as e:
            logger.error(f"종료 알림 실패: {e}")


def start_trello_watcher():
    """Trello 워처 시작"""
    global trello_watcher

    if not Config.trello.api_key or not Config.trello.token:
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
        """supervisor에서 graceful shutdown 요청을 받았을 때"""
        logger.info("Graceful shutdown 요청 수신")
        try:
            count = shutdown_all_sync()
            logger.info(f"셧다운: {count}개 클라이언트 종료")
        except Exception as e:
            logger.warning(f"클라이언트 종료 중 오류: {e}")
        notify_shutdown()
        os._exit(0)

    start_shutdown_server(_SHUTDOWN_PORT, _on_shutdown_request)
    logger.info(f"Shutdown server started on port {_SHUTDOWN_PORT}")
    init_bot_user_id()
    notify_startup()
    start_trello_watcher()
    start_list_runner()
    if _channel_scheduler:
        _channel_scheduler.start()
    handler = SocketModeHandler(app, Config.slack.app_token)
    handler.start()


if __name__ == "__main__":
    main()
