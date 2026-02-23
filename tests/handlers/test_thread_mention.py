"""스레드 내 멘션 메시지 처리 테스트

세션이 있는 스레드에서 @멘션 메시지가 정상 처리되는지 확인합니다.
(버그 수정: mention.py와 message.py 사각지대 해소)
"""

import pytest
from unittest.mock import MagicMock, patch


class TestProcessThreadMessage:
    """process_thread_message 공통 함수 테스트"""

    def test_processes_text_message(self):
        """텍스트 메시지 정상 처리"""
        from seosoyoung.handlers.message import process_thread_message

        event = {"user": "U123", "text": "<@BOT> 질문입니다"}
        session = MagicMock()
        say = MagicMock()
        client = MagicMock()
        get_user_role = MagicMock(return_value={"username": "tester", "role": "user"})
        run_claude = MagicMock()

        result = process_thread_message(
            event, event["text"], "thread_1", "ts_1", "C123",
            session, say, client, get_user_role, run_claude
        )

        assert result is True
        run_claude.assert_called_once()
        args = run_claude.call_args
        # 프롬프트에서 멘션이 제거되었는지 확인
        prompt = args[0][1]
        assert "<@BOT>" not in prompt
        assert "질문입니다" in prompt

    def test_skips_empty_message(self):
        """빈 메시지는 처리하지 않음"""
        from seosoyoung.handlers.message import process_thread_message

        event = {"user": "U123", "text": "<@BOT>"}
        session = MagicMock()
        say = MagicMock()
        client = MagicMock()
        get_user_role = MagicMock()
        run_claude = MagicMock()

        result = process_thread_message(
            event, event["text"], "thread_1", "ts_1", "C123",
            session, say, client, get_user_role, run_claude
        )

        assert result is False
        run_claude.assert_not_called()

    def test_passes_user_role(self):
        """사용자 역할이 올바르게 전달됨"""
        from seosoyoung.handlers.message import process_thread_message

        event = {"user": "U123", "text": "질문"}
        session = MagicMock()
        say = MagicMock()
        client = MagicMock()
        get_user_role = MagicMock(return_value={"username": "admin", "role": "admin"})
        run_claude = MagicMock()

        process_thread_message(
            event, event["text"], "thread_1", "ts_1", "C123",
            session, say, client, get_user_role, run_claude
        )

        run_claude.assert_called_once()
        kwargs = run_claude.call_args[1]
        assert kwargs["role"] == "admin"

    def test_handles_file_attachment(self):
        """파일 첨부 처리"""
        from seosoyoung.handlers.message import process_thread_message

        event = {
            "user": "U123",
            "text": "<@BOT>",
            "files": [{"id": "F123", "name": "test.txt"}]
        }
        session = MagicMock()
        say = MagicMock()
        client = MagicMock()
        get_user_role = MagicMock(return_value={"username": "tester", "role": "user"})
        run_claude = MagicMock()

        with patch("seosoyoung.handlers.message.download_files_sync") as mock_download, \
             patch("seosoyoung.handlers.message.build_file_context") as mock_context:
            mock_download.return_value = [{"path": "/tmp/test.txt"}]
            mock_context.return_value = "\n파일: test.txt\n내용: hello"

            result = process_thread_message(
                event, event["text"], "thread_1", "ts_1", "C123",
                session, say, client, get_user_role, run_claude
            )

        assert result is True
        run_claude.assert_called_once()

    def test_user_info_failure(self):
        """사용자 정보 조회 실패 시 에러 메시지"""
        from seosoyoung.handlers.message import process_thread_message

        event = {"user": "U123", "text": "질문"}
        session = MagicMock()
        say = MagicMock()
        client = MagicMock()
        get_user_role = MagicMock(return_value=None)
        run_claude = MagicMock()

        result = process_thread_message(
            event, event["text"], "thread_1", "ts_1", "C123",
            session, say, client, get_user_role, run_claude
        )

        assert result is True
        run_claude.assert_not_called()
        say.assert_called_once()
        assert "사용자 정보" in say.call_args[1]["text"]


class TestMentionHandlerThreadSession:
    """mention.py의 스레드+세션 분기 테스트"""

    @pytest.fixture
    def handler_deps(self):
        """핸들러 의존성 모킹"""
        session_manager = MagicMock()
        restart_manager = MagicMock()
        restart_manager.is_pending = False
        run_claude_in_session = MagicMock()
        check_permission = MagicMock(return_value=True)
        get_user_role = MagicMock(return_value={"username": "tester", "role": "user"})
        get_running_session_count = MagicMock(return_value=0)
        send_restart_confirmation = MagicMock()
        list_runner_ref = MagicMock(return_value=None)

        return {
            "session_manager": session_manager,
            "restart_manager": restart_manager,
            "run_claude_in_session": run_claude_in_session,
            "check_permission": check_permission,
            "get_user_role": get_user_role,
            "get_running_session_count": get_running_session_count,
            "send_restart_confirmation": send_restart_confirmation,
            "list_runner_ref": list_runner_ref,
        }

    def test_thread_mention_with_session_calls_process(self, handler_deps):
        """스레드 멘션 + 세션 있음 → process_thread_message 호출"""
        session = MagicMock()
        handler_deps["session_manager"].get.return_value = session

        with patch("seosoyoung.handlers.mention.process_thread_message") as mock_process:
            mock_process.return_value = True

            from seosoyoung.handlers.mention import register_mention_handlers

            app = MagicMock()
            captured_handler = None

            def capture_handler(event_type):
                def decorator(func):
                    nonlocal captured_handler
                    captured_handler = func
                    return func
                return decorator

            app.event = capture_handler
            register_mention_handlers(app, handler_deps)

            # 스레드에서 멘션 이벤트 시뮬레이션
            event = {
                "user": "U123",
                "text": "<@BOT> 이것 좀 해줘",
                "channel": "C123",
                "ts": "ts_2",
                "thread_ts": "thread_1",
            }

            say = MagicMock()
            client = MagicMock()

            captured_handler(event, say, client)

            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args
            assert call_kwargs[1]["log_prefix"] == "스레드 멘션"

    def test_thread_mention_without_session_falls_through(self, handler_deps):
        """스레드 멘션 + 세션 없음 → 원샷 답변 경로"""
        handler_deps["session_manager"].get.return_value = None
        handler_deps["session_manager"].exists.return_value = False

        with patch("seosoyoung.handlers.mention.process_thread_message") as mock_process, \
             patch("seosoyoung.handlers.mention.get_channel_history", return_value=""):

            from seosoyoung.handlers.mention import register_mention_handlers

            app = MagicMock()
            captured_handler = None

            def capture_handler(event_type):
                def decorator(func):
                    nonlocal captured_handler
                    captured_handler = func
                    return func
                return decorator

            app.event = capture_handler
            register_mention_handlers(app, handler_deps)

            event = {
                "user": "U123",
                "text": "<@BOT> 질문",
                "channel": "C123",
                "ts": "ts_1",
                "thread_ts": "thread_1",
            }

            say = MagicMock()
            client = MagicMock()
            client.chat_postMessage.return_value = {"ts": "msg_ts"}

            captured_handler(event, say, client)

            # process_thread_message는 호출되지 않아야 함
            mock_process.assert_not_called()
            # 대신 세션 생성 + Claude 실행 경로로 진행
            handler_deps["session_manager"].create.assert_called_once()

    def test_channel_mention_not_affected(self, handler_deps):
        """채널 멘션 (thread_ts 없음) → 기존 로직 유지"""
        handler_deps["session_manager"].get.return_value = None

        with patch("seosoyoung.handlers.mention.process_thread_message") as mock_process, \
             patch("seosoyoung.handlers.mention.get_channel_history", return_value=""):

            from seosoyoung.handlers.mention import register_mention_handlers

            app = MagicMock()
            captured_handler = None

            def capture_handler(event_type):
                def decorator(func):
                    nonlocal captured_handler
                    captured_handler = func
                    return func
                return decorator

            app.event = capture_handler
            register_mention_handlers(app, handler_deps)

            event = {
                "user": "U123",
                "text": "<@BOT> 새 질문",
                "channel": "C123",
                "ts": "ts_1",
            }

            say = MagicMock()
            client = MagicMock()
            client.chat_postMessage.return_value = {"ts": "msg_ts"}

            captured_handler(event, say, client)

            # process_thread_message는 호출되지 않아야 함
            mock_process.assert_not_called()
            # 세션 생성 경로로 진행
            handler_deps["session_manager"].create.assert_called_once()


    def test_thread_mention_with_session_restart_pending(self, handler_deps):
        """스레드 멘션 + 세션 있음 + 재시작 대기 → 안내 메시지"""
        session = MagicMock()
        handler_deps["session_manager"].get.return_value = session
        handler_deps["restart_manager"].is_pending = True

        with patch("seosoyoung.handlers.mention.process_thread_message") as mock_process:
            from seosoyoung.handlers.mention import register_mention_handlers

            app = MagicMock()
            captured_handler = None

            def capture_handler(event_type):
                def decorator(func):
                    nonlocal captured_handler
                    captured_handler = func
                    return func
                return decorator

            app.event = capture_handler
            register_mention_handlers(app, handler_deps)

            event = {
                "user": "U123",
                "text": "<@BOT> 질문",
                "channel": "C123",
                "ts": "ts_1",
                "thread_ts": "thread_1",
            }

            say = MagicMock()
            client = MagicMock()

            captured_handler(event, say, client)

            # 재시작 대기 중이므로 process_thread_message는 호출되지 않아야 함
            mock_process.assert_not_called()
            # 안내 메시지 전송
            say.assert_called_once()
            assert "재시작" in say.call_args[1]["text"]


class TestMessageHandlerBotMention:
    """message.py의 봇 멘션 체크 동작 확인"""

    def test_message_with_bot_mention_returns(self):
        """봇 멘션 포함 메시지는 message.py에서 무시됨 (mention.py에서 처리)"""
        from seosoyoung.handlers.message import _contains_bot_mention
        from seosoyoung.config import Config

        original_bot_id = Config.BOT_USER_ID
        try:
            Config.BOT_USER_ID = "BOT123"
            assert _contains_bot_mention("<@BOT123> hello") is True
            assert _contains_bot_mention("hello <@BOT123>") is True
            assert _contains_bot_mention("hello") is False
            assert _contains_bot_mention("<@OTHER> hello") is False
        finally:
            Config.BOT_USER_ID = original_bot_id
