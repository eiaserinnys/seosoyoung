"""DM 채널 핸들러 테스트

앱 DM 채널에서 메시지를 보내면 일반 채널 멘션과 동일하게 동작하는지 검증합니다.
"""

import pytest
from unittest.mock import MagicMock, patch, call


def _make_deps(**overrides):
    """테스트용 dependencies 딕셔너리 생성"""
    defaults = {
        "session_manager": MagicMock(),
        "restart_manager": MagicMock(is_pending=False),
        "run_claude_in_session": MagicMock(),
        "check_permission": MagicMock(return_value=True),
        "get_user_role": MagicMock(return_value={"username": "tester", "role": "admin", "user_id": "U_USER", "allowed_tools": []}),
        "get_running_session_count": MagicMock(return_value=0),
        "send_restart_confirmation": MagicMock(),
        "list_runner_ref": MagicMock(return_value=None),
        "channel_store": None,
        "mention_tracker": None,
        "channel_collector": None,
        "channel_observer": None,
        "channel_compressor": None,
        "channel_cooldown": None,
    }
    defaults.update(overrides)
    return defaults


def _register_and_capture(register_fn, deps):
    """핸들러를 등록하고 이벤트 타입별 핸들러 함수를 캡처"""
    mock_app = MagicMock()
    handlers = {}

    def capture_handler(event_type):
        def decorator(fn):
            handlers[event_type] = fn
            return fn
        return decorator

    mock_app.event = capture_handler
    register_fn(mock_app, deps)
    return handlers


class TestDmMessageDetection:
    """message.py에서 DM 메시지 감지 및 라우팅 테스트"""

    @patch("seosoyoung.handlers.message.Config")
    def test_dm_message_routed_to_dm_handler(self, mock_config):
        """channel_type == 'im' 메시지가 DM 핸들러로 라우팅됨"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "안녕하세요",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "reply_ts"}

        with patch("seosoyoung.handlers.message._handle_dm_message") as mock_dm:
            handlers["message"](event, say, client)
            mock_dm.assert_called_once()

    @patch("seosoyoung.handlers.message.Config")
    def test_regular_channel_message_not_routed_to_dm(self, mock_config):
        """일반 채널 메시지는 DM 핸들러로 라우팅되지 않음"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "C_GENERAL",
            "text": "일반 메시지",
            "ts": "1234.5678",
            "thread_ts": "1234.0000",
        }

        say = MagicMock()
        client = MagicMock()

        with patch("seosoyoung.handlers.message._handle_dm_message") as mock_dm:
            handlers["message"](event, say, client)
            mock_dm.assert_not_called()

    @patch("seosoyoung.handlers.message.Config")
    def test_dm_bot_message_ignored(self, mock_config):
        """봇의 DM 메시지는 무시됨 (bot_id 체크가 DM 라우팅보다 먼저)"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "bot_id": "B_BOT",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "봇 메시지",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        with patch("seosoyoung.handlers.message._handle_dm_message") as mock_dm:
            handlers["message"](event, say, client)
            mock_dm.assert_not_called()


class TestDmFirstMessage:
    """DM 첫 메시지 처리 테스트 (세션 생성 + Claude 실행)"""

    @patch("seosoyoung.handlers.mention._get_channel_messages", return_value=[])
    @patch("seosoyoung.handlers.mention.Config")
    @patch("seosoyoung.handlers.message.Config")
    def test_dm_first_message_creates_session(
        self, mock_msg_config, mock_mention_config, mock_get_msgs
    ):
        """DM 첫 메시지 → 세션 생성 + Claude 실행"""
        mock_msg_config.BOT_USER_ID = "B_BOT"
        mock_msg_config.TRANSLATE_CHANNELS = []
        mock_msg_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []
        mock_mention_config.CHANNEL_OBSERVER_CHANNELS = []

        from seosoyoung.handlers.message import register_message_handlers

        mock_session = MagicMock(source_type="thread", last_seen_ts="")
        deps = _make_deps()
        deps["session_manager"].create.return_value = mock_session

        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "안녕하세요 질문이 있습니다",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "reply_ts"}

        handlers["message"](event, say, client)

        # 세션이 생성되어야 함
        deps["session_manager"].create.assert_called_once()
        create_kwargs = deps["session_manager"].create.call_args[1]
        assert create_kwargs["channel_id"] == "D_DM"
        assert create_kwargs["user_id"] == "U_USER"

        # Claude 실행이 호출되어야 함
        deps["run_claude_in_session"].assert_called_once()

    @patch("seosoyoung.handlers.message.Config")
    def test_dm_empty_message_ignored(self, mock_config):
        """빈 DM 메시지 → 무시"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        # 세션이 생성되지 않아야 함
        deps["session_manager"].create.assert_not_called()
        deps["run_claude_in_session"].assert_not_called()


class TestDmThreadMessage:
    """DM 스레드 메시지 처리 테스트"""

    @patch("seosoyoung.handlers.message.process_thread_message")
    @patch("seosoyoung.handlers.message.Config")
    def test_dm_thread_message_processes_in_session(
        self, mock_config, mock_process_thread
    ):
        """DM 스레드 메시지 → 기존 세션에서 처리"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        mock_session = MagicMock()
        deps = _make_deps()
        deps["session_manager"].get.return_value = mock_session

        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "후속 질문입니다",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        # process_thread_message가 호출되어야 함
        mock_process_thread.assert_called_once()
        call_kwargs = mock_process_thread.call_args
        assert call_kwargs[0][2] == "1234.5678"  # thread_ts
        assert call_kwargs[1]["log_prefix"] == "DM 메시지"

    @patch("seosoyoung.handlers.message.process_thread_message")
    @patch("seosoyoung.handlers.message.Config")
    def test_dm_thread_message_without_session_ignored(
        self, mock_config, mock_process_thread
    ):
        """세션 없는 DM 스레드 메시지 → 무시"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        deps["session_manager"].get.return_value = None

        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "세션 없는 스레드 메시지",
            "ts": "1234.9999",
            "thread_ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        mock_process_thread.assert_not_called()


class TestDmAdminCommands:
    """DM 관리자 명령어 테스트"""

    @patch("seosoyoung.handlers.message.Config")
    def test_help_command_in_dm(self, mock_config):
        """DM에서 help 명령어"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "help",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        # help 응답이 전송되어야 함
        say.assert_called_once()
        help_text = say.call_args[1]["text"]
        assert "사용법" in help_text or "help" in help_text.lower()

        # 세션이 생성되지 않아야 함
        deps["session_manager"].create.assert_not_called()

    @patch("seosoyoung.handlers.message.Config")
    def test_status_command_in_dm(self, mock_config):
        """DM에서 status 명령어"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []
        mock_config.ADMIN_USERS = ["admin"]
        mock_config.DEBUG = False

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        deps["session_manager"].count.return_value = 3
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "status",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        say.assert_called_once()
        status_text = say.call_args[1]["text"]
        assert "상태" in status_text or "status" in status_text.lower()


class TestDmRestartPending:
    """DM 재시작 대기 중 테스트"""

    @patch("seosoyoung.handlers.message.Config")
    def test_dm_restart_pending_non_command(self, mock_config):
        """재시작 대기 중 DM 일반 메시지 → 안내 메시지"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        deps["restart_manager"].is_pending = True
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "질문입니다",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        say.assert_called_once()
        assert "재시작" in say.call_args[1]["text"]

    @patch("seosoyoung.handlers.message.Config")
    def test_dm_restart_pending_admin_command_still_works(self, mock_config):
        """재시작 대기 중이라도 관리자 명령어(help, status)는 동작"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        deps["restart_manager"].is_pending = True
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "channel_type": "im",
            "text": "help",
            "ts": "1234.5678",
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        say.assert_called_once()
        assert "사용법" in say.call_args[1]["text"] or "help" in say.call_args[1]["text"].lower()


class TestDmSubtypeHandling:
    """DM 메시지 subtype 처리 테스트"""

    @patch("seosoyoung.handlers.message.Config")
    def test_dm_message_changed_ignored(self, mock_config):
        """DM message_changed 이벤트는 무시"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        deps = _make_deps()
        handlers = _register_and_capture(register_message_handlers, deps)

        event = {
            "channel": "D_DM",
            "channel_type": "im",
            "subtype": "message_changed",
            "ts": "1234.5678",
            "message": {"user": "U_USER", "text": "수정된 메시지"},
        }

        say = MagicMock()
        client = MagicMock()

        handlers["message"](event, say, client)

        # 세션 생성이나 Claude 실행이 없어야 함
        deps["session_manager"].create.assert_not_called()
        deps["run_claude_in_session"].assert_not_called()
