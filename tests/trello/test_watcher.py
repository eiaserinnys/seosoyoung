"""TrelloWatcher 테스트"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import threading
from pathlib import Path

from seosoyoung.slackbot.plugins.trello.watcher import TrelloWatcher, TrackedCard


def _make_watcher(tmp_path, **overrides):
    """TrelloWatcher 인스턴스를 생성하는 헬퍼.

    새 생성자 시그니처에 맞춰 기본 Mock 값을 제공하고,
    overrides 로 개별 파라미터를 덮어쓸 수 있다.
    """
    trello_client = overrides.pop("trello_client", MagicMock())
    prompt_builder = overrides.pop("prompt_builder", MagicMock())
    slack_client = overrides.pop("slack_client", MagicMock())
    session_manager = overrides.pop("session_manager", MagicMock())
    claude_runner_factory = overrides.pop("claude_runner_factory", MagicMock())
    get_session_lock = overrides.pop("get_session_lock", None)
    list_runner_ref = overrides.pop("list_runner_ref", None)
    data_dir = overrides.pop("data_dir", tmp_path)

    config = overrides.pop("config", {})
    # 기본 config 값 (테스트용)
    default_config = {
        "notify_channel": "C12345",
        "poll_interval": 5,
        "watch_lists": {},
        "dm_target_user_id": "",
        "polling_debug": False,
        "list_ids": {
            "to_go": None,
            "in_progress": None,
            "review": None,
            "done": None,
            "blocked": None,
            "backlog": None,
            "draft": None,
        },
    }
    # config 오버라이드 머지
    for k, v in config.items():
        if k == "list_ids" and isinstance(v, dict):
            default_config["list_ids"].update(v)
        else:
            default_config[k] = v

    return TrelloWatcher(
        trello_client=trello_client,
        prompt_builder=prompt_builder,
        slack_client=slack_client,
        session_manager=session_manager,
        claude_runner_factory=claude_runner_factory,
        config=default_config,
        get_session_lock=get_session_lock,
        data_dir=data_dir,
        list_runner_ref=list_runner_ref,
    )


class TestTrelloWatcherPauseResume:
    """TrelloWatcher pause/resume 기능 테스트"""

    def test_initial_not_paused(self, tmp_path):
        """초기 상태는 일시 중단 아님"""
        watcher = _make_watcher(tmp_path)
        assert watcher.is_paused is False

    def test_pause(self, tmp_path):
        """일시 중단"""
        watcher = _make_watcher(tmp_path)
        watcher.pause()
        assert watcher.is_paused is True

    def test_resume(self, tmp_path):
        """재개"""
        watcher = _make_watcher(tmp_path)
        watcher.pause()
        assert watcher.is_paused is True
        watcher.resume()
        assert watcher.is_paused is False

    def test_poll_skipped_when_paused(self, tmp_path):
        """일시 중단 상태면 폴링 스킵"""
        mock_trello = MagicMock()
        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            config={"watch_lists": {"to_plan": "list123"}},
        )
        watcher.pause()
        watcher._poll()
        mock_trello.get_cards_in_list.assert_not_called()

    def test_poll_works_when_not_paused(self, tmp_path):
        """일시 중단 아니면 정상 폴링"""
        mock_trello = MagicMock()
        mock_trello.get_cards_in_list.return_value = []
        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            config={"watch_lists": {"to_plan": "list123"}},
        )
        watcher._poll()
        mock_trello.get_cards_in_list.assert_called()


class TestTrelloWatcherTrackedCardLookup:
    """TrackedCard 조회 기능 테스트"""

    def test_get_tracked_by_thread_ts_found(self, tmp_path):
        """thread_ts로 TrackedCard 조회 - 찾음"""
        from seosoyoung.slackbot.plugins.trello.watcher import ThreadCardInfo

        watcher = _make_watcher(tmp_path)

        tracked = TrackedCard(
            card_id="card123",
            card_name="테스트 카드",
            card_url="https://trello.com/c/abc123",
            list_id="list123",
            list_key="to_go",
            thread_ts="1234567890.123456",
            channel_id="C12345",
            detected_at="2024-01-01T00:00:00"
        )
        watcher._tracked["card123"] = tracked
        watcher._register_thread_card(tracked)

        result = watcher.get_tracked_by_thread_ts("1234567890.123456")
        assert result is not None
        assert result.card_id == "card123"
        assert result.card_name == "테스트 카드"

    def test_get_tracked_by_thread_ts_not_found(self, tmp_path):
        """thread_ts로 TrackedCard 조회 - 못 찾음"""
        watcher = _make_watcher(tmp_path)
        result = watcher.get_tracked_by_thread_ts("nonexistent_ts")
        assert result is None

    def test_build_reaction_execute_prompt(self, tmp_path):
        """리액션 기반 실행 프롬프트 생성"""
        from seosoyoung.slackbot.plugins.trello.watcher import ThreadCardInfo
        from seosoyoung.slackbot.plugins.trello.prompt_builder import PromptBuilder

        mock_trello = MagicMock()
        mock_trello.get_card.return_value = MagicMock(desc="")
        mock_trello.get_card_checklists.return_value = []
        mock_trello.get_card_comments.return_value = []

        prompt_builder = PromptBuilder(mock_trello, list_ids={})
        watcher = _make_watcher(tmp_path, prompt_builder=prompt_builder)

        info = ThreadCardInfo(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            card_id="card123",
            card_name="기능 구현 작업",
            card_url="https://trello.com/c/abc123",
            created_at="2024-01-01T00:00:00"
        )

        prompt = watcher.build_reaction_execute_prompt(info)

        assert "🚀 리액션으로 실행이 요청된" in prompt
        assert "기능 구현 작업" in prompt
        assert "card123" in prompt
        assert "https://trello.com/c/abc123" in prompt
        assert "이미 워처에 의해 🔨 In Progress로 이동되었습니다" in prompt


class TestAutoMoveNoticeInPrompts:
    """프롬프트에 카드 자동 이동 안내가 포함되는지 테스트"""

    def test_to_go_execute_prompt_has_auto_move_notice(self, tmp_path):
        """실행 모드 프롬프트에 자동 이동 안내 포함"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.prompt_builder import PromptBuilder

        mock_trello = MagicMock()
        mock_trello.get_card_checklists.return_value = []
        mock_trello.get_card_comments.return_value = []
        prompt_builder = PromptBuilder(mock_trello, list_ids={})

        watcher = _make_watcher(tmp_path, prompt_builder=prompt_builder, trello_client=mock_trello)

        card = TrelloCard(
            id="card123",
            name="테스트 태스크",
            desc="태스크 본문",
            url="https://trello.com/c/abc123",
            list_id="list123",
            labels=[],
        )

        prompt = watcher.prompt_builder.build_to_go(card, has_execute=True)
        assert "이미 워처에 의해 🔨 In Progress로 이동되었습니다" in prompt
        assert "In Progress로 이동하지 마세요" in prompt

    def test_to_go_plan_prompt_has_auto_move_notice(self, tmp_path):
        """계획 모드 프롬프트에 자동 이동 안내 포함"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.prompt_builder import PromptBuilder

        mock_trello = MagicMock()
        mock_trello.get_card_checklists.return_value = []
        mock_trello.get_card_comments.return_value = []
        prompt_builder = PromptBuilder(mock_trello, list_ids={})

        watcher = _make_watcher(tmp_path, prompt_builder=prompt_builder, trello_client=mock_trello)

        card = TrelloCard(
            id="card456",
            name="계획 태스크",
            desc="태스크 본문",
            url="https://trello.com/c/def456",
            list_id="list123",
            labels=[],
        )

        prompt = watcher.prompt_builder.build_to_go(card, has_execute=False)
        assert "이미 워처에 의해 🔨 In Progress로 이동되었습니다" in prompt
        assert "In Progress로 이동하지 마세요" in prompt
        assert "📦 Backlog로 이동하세요" in prompt


class TestListRunSaySignature:
    """정주행 say() 함수가 send_long_message와 호환되는 시그니처를 갖는지 테스트"""

    def test_list_run_say_accepts_thread_ts_keyword(self, tmp_path):
        """정주행 say()가 thread_ts= 키워드 인자를 받을 수 있어야 함

        send_long_message가 say(text=..., thread_ts=thread_ts)로 호출하므로,
        정주행용 say()도 thread_ts 키워드를 받아야 TypeError가 발생하지 않음.
        """
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.slack.helpers import send_long_message

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        list_runner = ListRunner(data_dir=tmp_path)

        watcher = _make_watcher(
            tmp_path,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
        )

        # 세션 생성
        session = list_runner.create_session(
            list_id="list_123",
            list_name="📦 Backlog",
            card_ids=["card_a"],
        )
        list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

        card = TrelloCard(
            id="card_a",
            name="Test Card",
            desc="",
            url="https://trello.com/c/abc",
            list_id="list_123",
            labels=[],
        )

        thread_ts = "1234567890.123456"

        # say를 PresentationContext에서 캡처하기 위해 claude_runner_factory를 이용
        captured_pctx = {}

        def capturing_factory(**kwargs):
            captured_pctx["presentation"] = kwargs.get("presentation")
            # 실행 완료 표시를 위해 mark_card_processed 호출
            list_runner.mark_card_processed(session.session_id, card.id, "completed")

        watcher.claude_runner_factory = capturing_factory

        # get_session_lock을 None으로 설정하여 lock 부분 스킵
        watcher.get_session_lock = None

        watcher._process_list_run_card(session.session_id, thread_ts)

        # PresentationContext에서 say 함수를 가져옴
        assert "presentation" in captured_pctx, "presentation이 claude_runner_factory에 전달되어야 함"
        say_fn = captured_pctx["presentation"].say

        # 핵심 테스트: send_long_message를 통해 호출했을 때 TypeError가 발생하지 않아야 함
        # send_long_message는 say(text=..., thread_ts=thread_ts)로 호출
        send_long_message(say_fn, "test message", "1234567890.999999")

        # 슬랙 메시지가 정상적으로 전송되었는지 확인
        calls = mock_slack.chat_postMessage.call_args_list
        # 마지막 호출이 send_long_message를 통한 것이어야 함
        last_call = calls[-1]
        assert last_call[1]["text"] == "test message"


class TestStaleTrackedCardCleanup:
    """방안 A: _poll() 시 만료된 _tracked 항목 자동 정리 테스트"""

    def test_stale_card_auto_untracked_after_timeout(self, tmp_path):
        """2시간 이상 경과 + To Go에 없는 카드는 자동 untrack"""
        mock_trello = MagicMock()
        mock_trello.get_cards_in_list.return_value = []
        mock_trello.get_lists.return_value = []

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            config={"watch_lists": {"to_go": "list_togo"}},
        )

        # 3시간 전에 추적 시작된 카드 (만료 기준 초과)
        stale_time = (datetime.now() - timedelta(hours=3)).isoformat()
        tracked = TrackedCard(
            card_id="stale_card",
            card_name="Stuck Card",
            card_url="https://trello.com/c/stale",
            list_id="list_togo",
            list_key="to_go",
            thread_ts="1111.2222",
            channel_id="C12345",
            detected_at=stale_time,
            session_id=None,  # 세션 없음
        )
        watcher._tracked["stale_card"] = tracked

        # 폴링 실행
        watcher._poll()

        # stale 카드가 untrack 되었어야 함
        assert "stale_card" not in watcher._tracked

    def test_recent_card_not_untracked(self, tmp_path):
        """30분 전 추적 시작된 카드는 아직 만료되지 않아 유지"""
        mock_trello = MagicMock()
        mock_trello.get_cards_in_list.return_value = []
        mock_trello.get_lists.return_value = []

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            config={"watch_lists": {"to_go": "list_togo"}},
        )

        # 30분 전 추적 시작 (만료 기준 미달)
        recent_time = (datetime.now() - timedelta(minutes=30)).isoformat()
        tracked = TrackedCard(
            card_id="recent_card",
            card_name="Recent Card",
            card_url="https://trello.com/c/recent",
            list_id="list_togo",
            list_key="to_go",
            thread_ts="3333.4444",
            channel_id="C12345",
            detected_at=recent_time,
        )
        watcher._tracked["recent_card"] = tracked

        watcher._poll()

        # 아직 유지되어야 함
        assert "recent_card" in watcher._tracked


class TestHandleNewCardFailureUntrack:
    """방안 B: _handle_new_card 실패 시 untrack 테스트"""

    def test_untrack_on_slack_message_failure(self, tmp_path):
        """Slack 메시지 전송 실패 시 카드가 _tracked에 남지 않아야 함"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard

        mock_trello = MagicMock()
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.side_effect = Exception("Slack API error")

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            config={"list_ids": {"in_progress": "list_inprogress"}},
        )

        card = TrelloCard(
            id="fail_card",
            name="Fail Card",
            desc="",
            url="https://trello.com/c/fail",
            list_id="list_togo",
            labels=[],
        )

        watcher._handle_new_card(card, "to_go")

        # Slack 메시지 실패 시 _tracked에 카드가 남지 않아야 함
        assert "fail_card" not in watcher._tracked


class TestToGoReturnRetrack:
    """방안 C: 카드가 To Go로 다시 돌아왔을 때 re-track 테스트"""

    def test_card_returned_to_togo_is_retracked(self, tmp_path):
        """이미 _tracked에 있는 카드가 다시 To Go에 나타나면 re-track"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard

        mock_trello = MagicMock()
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True
        mock_trello.get_lists.return_value = []

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "9999.0000"}

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            session_manager=MagicMock(create=MagicMock()),
            config={
                "watch_lists": {"to_go": "list_togo"},
                "list_ids": {"in_progress": "list_inprogress"},
            },
        )

        # stale tracked card (3시간 전)
        stale_time = (datetime.now() - timedelta(hours=3)).isoformat()
        old_tracked = TrackedCard(
            card_id="return_card",
            card_name="Return Card",
            card_url="https://trello.com/c/return",
            list_id="list_togo",
            list_key="to_go",
            thread_ts="old_thread",
            channel_id="C12345",
            detected_at=stale_time,
            session_id=None,
        )
        watcher._tracked["return_card"] = old_tracked

        # 이 카드가 다시 To Go에 있음
        card = TrelloCard(
            id="return_card",
            name="Return Card",
            desc="",
            url="https://trello.com/c/return",
            list_id="list_togo",
            labels=[],
        )
        mock_trello.get_cards_in_list.return_value = [card]

        watcher._poll()

        # stale 카드가 제거된 후 _handle_new_card로 다시 처리되어야 함
        # 또는 detected_at이 갱신되었어야 함
        # 핵심: 카드가 stuck 상태로 남지 않고 재처리됨
        assert "return_card" not in watcher._tracked or \
            watcher._tracked["return_card"].detected_at != stale_time


class TestPreemptiveCompact:
    """정주행 카드 완료 시 선제적 컨텍스트 컴팩트 테스트"""

    def test_compact_success_with_session_id(self, tmp_path):
        """세션 ID가 있을 때 compact_session 호출 성공"""
        from seosoyoung.slackbot.soulstream.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="test-session-abc123",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = _make_watcher(tmp_path, session_manager=mock_session_manager)

        # ClaudeRunner.compact_session을 mock
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.session_id = "test-session-abc123"  # 동일 session_id

        with patch("seosoyoung.rescue.claude.agent_runner.ClaudeRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.compact_session.return_value = mock_result
            mock_runner_instance.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # compact_session이 올바른 session_id로 호출되었는지 확인
            mock_runner_instance.compact_session.assert_called_once_with("test-session-abc123")

    def test_compact_skipped_without_session_id(self, tmp_path):
        """세션 ID가 없으면 compact를 스킵"""
        from seosoyoung.slackbot.soulstream.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id=None,
        )
        mock_session_manager.get.return_value = mock_session

        watcher = _make_watcher(tmp_path, session_manager=mock_session_manager)

        with patch("seosoyoung.rescue.claude.agent_runner.ClaudeRunner") as MockRunner:
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # Runner가 생성되지 않아야 함
            MockRunner.assert_not_called()

    def test_compact_failure_does_not_block_next_card(self, tmp_path):
        """compact 실패해도 예외가 전파되지 않아 다음 카드 처리를 막지 않음"""
        from seosoyoung.slackbot.soulstream.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="test-session-abc123",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = _make_watcher(tmp_path, session_manager=mock_session_manager)

        with patch("seosoyoung.rescue.claude.agent_runner.ClaudeRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            # compact_session이 예외를 발생시킴
            mock_runner_instance.run_sync.side_effect = RuntimeError("Connection failed")
            MockRunner.return_value = mock_runner_instance

            # 예외가 전파되지 않아야 함
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

    def test_compact_updates_session_id_when_changed(self, tmp_path):
        """compact 후 세션 ID가 변경되면 session_manager에 업데이트"""
        from seosoyoung.slackbot.soulstream.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="old-session-id",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = _make_watcher(tmp_path, session_manager=mock_session_manager)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.session_id = "new-session-id"  # 변경된 session_id

        with patch("seosoyoung.rescue.claude.agent_runner.ClaudeRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # session_manager.update_session_id가 새 ID로 호출되었는지 확인
            mock_session_manager.update_session_id.assert_called_once_with(
                "1234.5678", "new-session-id"
            )


class TestCheckRunListLabelsFiltering:
    """_check_run_list_labels 운영 리스트 필터링 및 가드 테스트"""

    def test_operational_lists_excluded(self, tmp_path):
        """운영 리스트(In Progress, Review, Done 등)는 정주행 대상에서 제외"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard

        mock_trello = MagicMock()

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            config={
                "watch_lists": {"to_go": "list_togo"},
                "list_ids": {
                    "review": "list_review",
                    "done": "list_done",
                    "in_progress": "list_inprogress",
                    "backlog": "list_backlog",
                    "blocked": "list_blocked",
                    "draft": "list_draft",
                },
            },
        )

        # 운영 리스트에 Run List 레이블이 있는 카드를 배치
        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card_in_progress = TrelloCard(
            id="card_ip", name="Card In Progress", desc="",
            url="", list_id="list_inprogress",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_inprogress", "name": "🔨 In Progress"},
            {"id": "list_review", "name": "👀 Review"},
            {"id": "list_togo", "name": "🚀 To Go"},
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card_in_progress]
        mock_trello.remove_label_from_card.return_value = True

        watcher._check_run_list_labels()

        # 운영 리스트가 아닌 list_plan만 카드 조회 대상이어야 함
        # get_cards_in_list는 list_plan에 대해서만 호출되어야 함
        call_args = [c[0][0] for c in mock_trello.get_cards_in_list.call_args_list]
        assert "list_inprogress" not in call_args
        assert "list_review" not in call_args
        assert "list_togo" not in call_args

    def test_label_removal_failure_skips_list_run(self, tmp_path):
        """레이블 제거 실패 시 정주행을 시작하지 않아야 함"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard

        mock_trello = MagicMock()

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            list_runner_ref=MagicMock(return_value=MagicMock()),
        )

        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card = TrelloCard(
            id="card_plan", name="Plan Card", desc="",
            url="", list_id="list_plan",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card]
        # 레이블 제거 실패
        mock_trello.remove_label_from_card.return_value = False

        with patch.object(watcher, "_start_list_run") as mock_start:
            watcher._check_run_list_labels()
            # _start_list_run이 호출되지 않아야 함
            mock_start.assert_not_called()

    def test_active_session_guard_prevents_duplicate(self, tmp_path):
        """동일 리스트에 활성 세션이 있으면 정주행 시작 안 함"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard

        mock_trello = MagicMock()

        mock_list_runner = MagicMock()
        active_session = MagicMock()
        active_session.list_id = "list_plan"
        mock_list_runner.get_active_sessions.return_value = [active_session]

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            list_runner_ref=lambda: mock_list_runner,
        )

        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card = TrelloCard(
            id="card_plan", name="Plan Card", desc="",
            url="", list_id="list_plan",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card]
        mock_trello.remove_label_from_card.return_value = True

        with patch.object(watcher, "_start_list_run") as mock_start:
            watcher._check_run_list_labels()
            mock_start.assert_not_called()


class TestProcessListRunCardTracked:
    """_process_list_run_card가 _tracked에 등록하는지 테스트"""

    def test_list_run_card_registered_in_tracked(self, tmp_path):
        """정주행 카드가 _tracked에 등록되어 To Go 감지와 중복 방지"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus

        mock_trello = MagicMock()
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        list_runner = ListRunner(data_dir=tmp_path)

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
        )

        # 세션 생성
        session = list_runner.create_session(
            list_id="list_123",
            list_name="Plan List",
            card_ids=["card_a"],
        )
        list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

        card = TrelloCard(
            id="card_a", name="Test Card", desc="",
            url="https://trello.com/c/abc", list_id="list_123",
            labels=[],
        )
        mock_trello.get_card.return_value = card

        # _process_list_run_card 호출 전 _tracked 확인
        assert "card_a" not in watcher._tracked

        # 세션 락 없이 실행
        watcher.get_session_lock = None
        watcher._process_list_run_card(session.session_id, "1234567890.123456")

        # 정주행 카드가 _tracked에 등록되어야 함
        assert "card_a" in watcher._tracked
        assert watcher._tracked["card_a"].list_key == "list_run"

    def test_list_run_first_card_not_redetected_by_poll(self, tmp_path):
        """정주행 첫 카드가 _tracked에 있으면 _poll에서 재감지되지 않음"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard

        mock_trello = MagicMock()
        mock_trello.get_lists.return_value = []

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            config={"watch_lists": {"to_go": "list_togo"}},
        )

        # 정주행으로 이미 _tracked에 등록된 카드
        tracked = TrackedCard(
            card_id="card_run_1",
            card_name="Run Card",
            card_url="https://trello.com/c/run1",
            list_id="list_plan",
            list_key="list_run",
            thread_ts="thread_123",
            channel_id="C12345",
            detected_at=datetime.now().isoformat(),
            has_execute=True,
        )
        watcher._tracked["card_run_1"] = tracked

        # 같은 카드가 To Go에도 나타남 (이론적으로 불가능하지만 방어적으로 테스트)
        card = TrelloCard(
            id="card_run_1", name="Run Card", desc="",
            url="https://trello.com/c/run1", list_id="list_togo",
            labels=[],
        )
        mock_trello.get_cards_in_list.return_value = [card]

        with patch.object(watcher, "_handle_new_card") as mock_handle:
            watcher._poll()
            # _tracked에 이미 있으므로 _handle_new_card가 호출되지 않아야 함
            mock_handle.assert_not_called()


class TestListRunDuplicatePrevention:
    """리스트 정주행 동시 실행 시 중복 방지 테스트"""

    def test_list_run_lock_serializes_concurrent_starts(self, tmp_path):
        """_list_run_lock이 동시 _check_run_list_labels 호출을 직렬화

        두 스레드가 동시에 _check_run_list_labels를 호출하면,
        첫 번째가 세션을 생성한 후 두 번째는 활성 세션을 발견하여 스킵해야 함.
        """
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner

        mock_trello = MagicMock()
        list_runner = ListRunner(data_dir=tmp_path)

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            list_runner_ref=lambda: list_runner,
        )

        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card = TrelloCard(
            id="card_plan", name="Plan Card", desc="",
            url="", list_id="list_plan",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card]
        mock_trello.remove_label_from_card.return_value = True

        start_call_count = 0

        def counting_start(*args, **kwargs):
            nonlocal start_call_count
            start_call_count += 1
            list_runner.create_session(args[0], args[1], [c.id for c in args[2]])

        with patch.object(watcher, "_start_list_run", side_effect=counting_start):
            barrier = threading.Barrier(2)
            results = []

            def run_check():
                barrier.wait()
                watcher._check_run_list_labels()
                results.append(True)

            t1 = threading.Thread(target=run_check)
            t2 = threading.Thread(target=run_check)
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        assert start_call_count <= 1, (
            f"_start_list_run이 {start_call_count}번 호출됨 (기대: ≤1)"
        )

    def test_tracked_card_skipped_in_list_run(self, tmp_path):
        """다른 세션에서 처리 중인 카드(다른 thread_ts)는 skipped_duplicate로 처리"""
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus

        mock_trello = MagicMock()
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "ts_123"}

        list_runner = ListRunner(data_dir=tmp_path)

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
        )

        session = list_runner.create_session(
            list_id="list_123",
            list_name="Plan List",
            card_ids=["card_a"],
        )
        list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

        tracked = TrackedCard(
            card_id="card_a",
            card_name="Card A",
            card_url="https://trello.com/c/a",
            list_id="list_123",
            list_key="list_run",
            thread_ts="other_thread",
            channel_id="C12345",
            detected_at=datetime.now().isoformat(),
            has_execute=True,
        )
        watcher._tracked["card_a"] = tracked

        watcher._process_list_run_card(session.session_id, "ts_123")

        updated_session = list_runner.get_session(session.session_id)
        assert "card_a" in updated_session.processed_cards
        assert updated_session.processed_cards["card_a"] == "skipped_duplicate"
        assert updated_session.status == SessionStatus.COMPLETED

    def test_watcher_has_list_run_lock(self, tmp_path):
        """TrelloWatcher가 _list_run_lock 속성을 가지고 있어야 함"""
        watcher = _make_watcher(tmp_path)
        assert hasattr(watcher, "_list_run_lock")
        assert isinstance(watcher._list_run_lock, type(threading.Lock()))


class TestGetOperationalListIds:
    """_get_operational_list_ids 테스트"""

    def test_collects_all_operational_ids(self, tmp_path):
        """모든 운영 리스트 ID가 수집됨"""
        watcher = _make_watcher(
            tmp_path,
            config={
                "watch_lists": {"to_go": "list_togo"},
                "list_ids": {
                    "review": "list_review",
                    "done": "list_done",
                    "in_progress": "list_ip",
                    "backlog": "list_bl",
                    "blocked": "list_blocked",
                    "draft": "list_draft",
                },
            },
        )

        ids = watcher._get_operational_list_ids()
        assert "list_togo" in ids
        assert "list_review" in ids
        assert "list_done" in ids
        assert "list_ip" in ids
        assert "list_bl" in ids
        assert "list_blocked" in ids
        assert "list_draft" in ids

    def test_empty_ids_excluded(self, tmp_path):
        """빈 문자열 ID는 제외됨"""
        watcher = _make_watcher(
            tmp_path,
            config={
                "watch_lists": {"to_go": "list_togo"},
                "list_ids": {
                    "review": "",
                    "done": None,
                    "in_progress": "list_ip",
                    "backlog": "",
                    "blocked": None,
                    "draft": "",
                },
            },
        )

        ids = watcher._get_operational_list_ids()
        assert "" not in ids
        assert None not in ids
        assert "list_togo" in ids
        assert "list_ip" in ids


class _SyncThread:
    """테스트용: threading.Thread를 동기적으로 실행하는 대체 클래스"""
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **extra):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        if self.target:
            self.target(*self.args, **self.kwargs)


class TestMultiCardChainingIntegration:
    """멀티 카드 체이닝 통합 테스트 (card1→card2→card3→COMPLETED)

    _spawn_claude_thread가 별도 스레드를 생성하므로, claude_runner_factory를
    동기적으로 완료하도록 모킹하여 체이닝 흐름을 검증합니다.
    on_success 내부의 threading.Thread도 동기화하여 전체 체인을 검증합니다.
    """

    @patch("seosoyoung.slackbot.plugins.trello.watcher.threading.Thread", _SyncThread)
    def test_three_card_chaining_completes(self, tmp_path):
        """3장의 카드가 순차적으로 처리되고 세션이 COMPLETED 상태가 됨"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus

        mock_trello = MagicMock()
        list_runner = ListRunner(data_dir=tmp_path)
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

        def sync_spawn(*, session, prompt, thread_ts, channel,
                       tracked, dm_channel_id=None, dm_thread_ts=None,
                       on_success=None, on_error=None, on_finally=None):
            if on_success:
                on_success()
            if on_finally:
                on_finally()

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
            config={"list_ids": {"in_progress": "list_inprogress"}},
        )
        watcher._spawn_claude_thread = sync_spawn
        watcher._preemptive_compact = MagicMock()

        cards_data = {
            "card_a": TrelloCard(
                id="card_a", name="Card A", desc="",
                url="https://trello.com/c/a", list_id="list_plan", labels=[],
            ),
            "card_b": TrelloCard(
                id="card_b", name="Card B", desc="",
                url="https://trello.com/c/b", list_id="list_plan", labels=[],
            ),
            "card_c": TrelloCard(
                id="card_c", name="Card C", desc="",
                url="https://trello.com/c/c", list_id="list_plan", labels=[],
            ),
        }
        mock_trello.get_card.side_effect = lambda cid: cards_data.get(cid)
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True

        session = list_runner.create_session(
            list_id="list_plan",
            list_name="Plan List",
            card_ids=["card_a", "card_b", "card_c"],
        )

        watcher._process_list_run_card(session.session_id, "thread_123")

        updated = list_runner.get_session(session.session_id)
        assert updated.status == SessionStatus.COMPLETED
        assert updated.current_index == 3
        assert updated.processed_cards == {
            "card_a": "completed",
            "card_b": "completed",
            "card_c": "completed",
        }

    @patch("seosoyoung.slackbot.plugins.trello.watcher.threading.Thread", _SyncThread)
    def test_chaining_continues_after_compact_failure(self, tmp_path):
        """_preemptive_compact 실패해도 체인이 끊기지 않음"""
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus

        mock_trello = MagicMock()
        list_runner = ListRunner(data_dir=tmp_path)
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

        def sync_spawn(*, session, prompt, thread_ts, channel,
                       tracked, dm_channel_id=None, dm_thread_ts=None,
                       on_success=None, on_error=None, on_finally=None):
            if on_success:
                on_success()
            if on_finally:
                on_finally()

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
            config={"list_ids": {"in_progress": "list_inprogress"}},
        )
        watcher._spawn_claude_thread = sync_spawn
        watcher._preemptive_compact = MagicMock(
            side_effect=RuntimeError("compact hang")
        )

        cards_data = {
            "card_a": TrelloCard(
                id="card_a", name="Card A", desc="",
                url="https://trello.com/c/a", list_id="list_plan", labels=[],
            ),
            "card_b": TrelloCard(
                id="card_b", name="Card B", desc="",
                url="https://trello.com/c/b", list_id="list_plan", labels=[],
            ),
        }
        mock_trello.get_card.side_effect = lambda cid: cards_data.get(cid)
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True

        session = list_runner.create_session(
            list_id="list_plan",
            list_name="Plan List",
            card_ids=["card_a", "card_b"],
        )

        watcher._process_list_run_card(session.session_id, "thread_123")

        updated = list_runner.get_session(session.session_id)
        assert updated.status == SessionStatus.COMPLETED
        assert updated.current_index == 2

    def test_on_success_exception_does_not_trigger_on_error(self, tmp_path):
        """on_success 예외가 on_error를 트리거하지 않음 (_spawn_claude_thread 격리 검증)"""
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

        watcher = _make_watcher(tmp_path, slack_client=mock_slack)

        tracked = TrackedCard(
            card_id="card_test",
            card_name="Test Card",
            card_url="",
            list_id="list_test",
            list_key="test",
            thread_ts="thread_123",
            channel_id="C12345",
            detected_at="2026-01-01T00:00:00",
        )

        on_error_called = []

        def failing_on_success():
            raise RuntimeError("on_success exploded")

        def tracking_on_error(e):
            on_error_called.append(e)

        # _spawn_claude_thread 직접 호출 후 스레드 완료 대기
        watcher.get_session_lock = None
        watcher._spawn_claude_thread(
            session=MagicMock(),
            prompt="test",
            thread_ts="thread_123",
            channel="C12345",
            tracked=tracked,
            on_success=failing_on_success,
            on_error=tracking_on_error,
        )

        # 스레드 완료 대기
        import time
        time.sleep(0.5)

        # on_error가 호출되지 않아야 함 (Claude 실행 자체는 성공)
        assert len(on_error_called) == 0

    def test_process_list_run_card_handles_trello_api_error(self, tmp_path):
        """_process_list_run_card에서 Trello API 오류 시 전역 try-except가 잡음"""
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus

        mock_trello = MagicMock()
        mock_trello.get_card.side_effect = ConnectionError("Trello API down")

        list_runner = ListRunner(data_dir=tmp_path)
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
            config={"list_ids": {"in_progress": "list_ip"}},
        )

        session = list_runner.create_session(
            list_id="list_plan",
            list_name="Plan",
            card_ids=["card_a"],
        )
        list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

        watcher._process_list_run_card(session.session_id, "thread_123")

        updated = list_runner.get_session(session.session_id)
        assert updated.status == SessionStatus.PAUSED

    def test_compact_timeout_does_not_block_chain(self, tmp_path):
        """_preemptive_compact 타임아웃 시 체인이 계속됨"""
        import concurrent.futures
        from seosoyoung.slackbot.soulstream.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="test-session",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = _make_watcher(tmp_path, session_manager=mock_session_manager)

        # future.result()가 TimeoutError를 raise하도록 mock 설정
        mock_future = MagicMock()
        mock_future.result.side_effect = concurrent.futures.TimeoutError()

        mock_pool = MagicMock()
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_pool.submit.return_value = mock_future

        with patch("seosoyoung.rescue.claude.agent_runner.ClaudeRunner") as MockRunner, \
             patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_pool):
            MockRunner.return_value = MagicMock()

            # TimeoutError가 발생해도 정상 반환 (예외 전파 없음)
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # submit이 호출되었는지 확인
            mock_pool.submit.assert_called_once()
            # future.result()에 timeout이 전달되었는지 확인
            mock_future.result.assert_called_once_with(
                timeout=watcher.COMPACT_TIMEOUT_SECONDS
            )


class TestSpawnClaudeThreadLockHandling:
    """_spawn_claude_thread 락 처리 버그 테스트

    버그 1·2: watcher가 직접 락을 acquire한 뒤 claude_runner_factory(executor.run)도
    같은 락을 acquire하여 이중 관리가 발생하는 문제.

    버그 3: on_success()가 락 해제 전에 호출되어 다음 스레드가 락 획득에 실패하는 문제.
    """

    def test_lock_released_before_on_success_next_thread_can_acquire(self, tmp_path):
        """on_success에서 시작한 새 스레드가 같은 thread_ts 락을 즉시 획득할 수 있어야 함

        버그 3 검증:
        - on_success()가 락 해제 전에 호출되면, on_success 내부의 새 스레드가
          락 획득을 시도할 때 여전히 watcher 스레드가 잡고 있어 blocking됨.
        - 수정 후: 락 해제 후에 on_success()가 호출되어야 함.
        - RLock은 스레드 소유권 기반이므로 다른 스레드에서 획득 시도해야 버그가 드러남.
        """
        lock = threading.RLock()
        other_thread_lock_try_result = []

        def get_session_lock(ts):
            return lock

        watcher = _make_watcher(tmp_path, get_session_lock=get_session_lock)

        tracked = TrackedCard(
            card_id="card_test",
            card_name="Test Card",
            card_url="",
            list_id="list_test",
            list_key="test",
            thread_ts="thread_lock_test",
            channel_id="C12345",
            detected_at="2026-01-01T00:00:00",
        )

        event = threading.Event()

        def on_success():
            # 이 시점에서 lock은 이미 해제되어 있어야 함 (수정 후)
            # 다른 스레드에서 non-blocking 획득 시도 → lock이 free해야 True
            result_holder = []
            def try_from_other_thread():
                acquired = lock.acquire(blocking=False)
                result_holder.append(acquired)
                if acquired:
                    lock.release()
            t = threading.Thread(target=try_from_other_thread)
            t.start()
            t.join(timeout=1.0)
            if result_holder:
                other_thread_lock_try_result.append(result_holder[0])
            event.set()

        watcher._spawn_claude_thread(
            session=MagicMock(),
            prompt="test",
            thread_ts="thread_lock_test",
            channel="C12345",
            tracked=tracked,
            on_success=on_success,
        )

        # 스레드 완료 대기
        event.wait(timeout=5.0)

        # on_success 호출 확인
        assert other_thread_lock_try_result, "on_success가 호출되지 않았습니다"
        # 수정 후: on_success 호출 시점에 다른 스레드가 락을 획득할 수 있어야 함
        assert other_thread_lock_try_result[0] is True, (
            "on_success 호출 시점에 다른 스레드가 lock을 획득할 수 없습니다 (버그 3)\n"
            "락 해제 후에 on_success()를 호출해야 합니다."
        )

    def test_watcher_does_not_double_manage_lock(self, tmp_path):
        """watcher가 락을 직접 관리하지 않아도 executor가 올바르게 처리함을 검증

        버그 1·2 검증:
        - watcher가 lock.acquire()를 하고 executor.run()도 acquire()를 하면
          같은 스레드에서 RLock count가 2가 됨.
          watcher finally + executor finally 두 번 release → count=0이지만,
          on_success 호출 시점(693~702행 사이)에는 count=1이 남아 있어
          다른 스레드가 lock을 획득할 수 없음.
        - 수정 후: watcher는 락을 직접 acquire/release하지 않음.
          executor.run()이 락의 단독 owner → on_finally 전에 executor가 release.
        """
        lock = threading.RLock()

        def get_session_lock(ts):
            return lock

        lock_free_in_on_finally = []

        watcher = _make_watcher(tmp_path, get_session_lock=get_session_lock)

        tracked = TrackedCard(
            card_id="card_double_lock",
            card_name="Double Lock Card",
            card_url="",
            list_id="list_test",
            list_key="test",
            thread_ts="thread_double_lock",
            channel_id="C12345",
            detected_at="2026-01-01T00:00:00",
        )

        done = threading.Event()

        def on_finally():
            # on_finally 호출 시점에 다른 스레드에서 락 획득 가능한지 확인
            # 수정 후에는 watcher가 락을 직접 잡지 않으므로
            # on_finally 이전에 이미 executor가 release했어야 함
            result_holder = []
            def try_acquire():
                acquired = lock.acquire(blocking=False)
                result_holder.append(acquired)
                if acquired:
                    lock.release()
            t = threading.Thread(target=try_acquire)
            t.start()
            t.join(timeout=1.0)
            if result_holder:
                lock_free_in_on_finally.append(result_holder[0])
            done.set()

        watcher._spawn_claude_thread(
            session=MagicMock(),
            prompt="test",
            thread_ts="thread_double_lock",
            channel="C12345",
            tracked=tracked,
            on_finally=on_finally,
        )

        done.wait(timeout=5.0)

        assert lock_free_in_on_finally, "on_finally가 호출되지 않았습니다"
        # 수정 후: on_finally 호출 전(혹은 시점)에 watcher가 락을 잡지 않아야 함
        # → 다른 스레드에서 락을 획득할 수 있어야 함
        assert lock_free_in_on_finally[0] is True, (
            "on_finally 호출 시점에 다른 스레드가 락을 획득할 수 없습니다 (버그 1·2)\n"
            "watcher가 락을 직접 acquire/release하면 executor와 이중 관리됩니다."
        )


class TestListRunOnSuccessLockOrder:
    """리스트 정주행에서 on_success 콜백과 락 해제 순서 테스트

    버그 3의 실제 발현 시나리오:
    - remote 모드에서 executor.run()이 락을 보유한 채로 완료
    - watcher도 락을 보유한 상태에서 on_success() 호출
    - on_success 내부의 새 스레드가 같은 락 획득 시도 → 블로킹
    """

    @patch("seosoyoung.slackbot.plugins.trello.watcher.threading.Thread", _SyncThread)
    def test_lock_state_after_on_success_with_real_lock(self, tmp_path):
        """실제 락과 _spawn_claude_thread를 사용할 때 on_success 시 락이 해제되어 있어야 함

        버그 3의 전체 시나리오:
        - _process_list_run_card → _spawn_claude_thread(on_success=...) 호출
        - _spawn_claude_thread 내부의 run_claude()가 lock.acquire()
        - on_success()가 lock.release() 전에 호출 → 버그
        - on_success 내부에서 새 스레드가 같은 thread_ts lock 획득 시도 → 실패
        """
        from seosoyoung.slackbot.plugins.trello.client import TrelloCard
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner, SessionStatus

        mock_trello = MagicMock()
        list_runner = ListRunner(data_dir=tmp_path)
        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

        real_lock = threading.RLock()
        other_thread_result_in_on_success = []

        def get_session_lock(ts):
            return real_lock

        watcher = _make_watcher(
            tmp_path,
            trello_client=mock_trello,
            slack_client=mock_slack,
            list_runner_ref=lambda: list_runner,
            get_session_lock=get_session_lock,
        )
        watcher._preemptive_compact = MagicMock()

        card = TrelloCard(
            id="card_a", name="Card A", desc="",
            url="https://trello.com/c/a", list_id="list_plan", labels=[],
        )
        mock_trello.get_card.return_value = card
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True

        session = list_runner.create_session(
            list_id="list_plan",
            list_name="Plan List",
            card_ids=["card_a"],
        )

        original_spawn = watcher._spawn_claude_thread

        def intercepting_spawn(*, session, prompt, thread_ts, channel,
                               tracked, dm_channel_id=None, dm_thread_ts=None,
                               on_success=None, on_error=None, on_finally=None):
            def wrapped_on_success():
                acquired_flag = [None]
                lock_checked = threading.Event()
                def check_from_real_thread():
                    acquired_flag[0] = real_lock.acquire(blocking=False)
                    if acquired_flag[0]:
                        real_lock.release()
                    lock_checked.set()
                t = threading.Thread(target=check_from_real_thread)
                t.start()
                lock_checked.wait(timeout=1.0)
                other_thread_result_in_on_success.append(acquired_flag[0])
                if on_success:
                    on_success()
            original_spawn(
                session=session,
                prompt=prompt,
                thread_ts=thread_ts,
                channel=channel,
                tracked=tracked,
                dm_channel_id=dm_channel_id,
                dm_thread_ts=dm_thread_ts,
                on_success=wrapped_on_success,
                on_error=on_error,
                on_finally=on_finally,
            )

        watcher._spawn_claude_thread = intercepting_spawn

        watcher._process_list_run_card(session.session_id, "thread_123")

        assert other_thread_result_in_on_success, \
            "_spawn_claude_thread에 on_success가 전달되지 않았습니다"
        assert other_thread_result_in_on_success[0] is True, (
            "on_success 호출 시점에 다른 스레드가 lock을 획득할 수 없습니다 (버그 3)\n"
            "락 해제 후에 on_success()를 호출해야 합니다."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
