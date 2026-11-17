"""App Home 핸들러 테스트

소울스트림 세션 현황을 슬랙 앱 홈에 Block Kit으로 렌더링하는 기능을 검증한다.
"""

import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from seosoyoung.slackbot.handlers.home import (
    build_home_view,
    fetch_sessions,
    register_home_handlers,
    _build_slack_url,
    _build_session_block,
)
from seosoyoung.slackbot.soulstream.session import Session


DASHBOARD_BASE = "https://soul.eiaserinnys.me/#"
NODE_NAME = "eiaserinnys"

# 공통 build_home_view 호출 헬퍼
def _build_view(sessions, node_name=NODE_NAME, total=None, dashboard_base_url=DASHBOARD_BASE):
    if total is None:
        total = len(sessions)
    return build_home_view(sessions, node_name, total=total, dashboard_base_url=dashboard_base_url)


def _make_session(
    session_id: str = "sess-20260323-abcd1234",
    status: str = "running",
    display_name: str | None = None,
    last_message: dict | None = None,
    created_at: str = "2026-03-23T02:00:00Z",
    updated_at: str = "2026-03-23T02:30:00Z",
    node_id: str | None = "eiaserinnys",
) -> dict:
    """테스트용 세션 딕셔너리 생성"""
    return {
        "agent_session_id": session_id,
        "status": status,
        "display_name": display_name,
        "last_message": last_message,
        "created_at": created_at,
        "updated_at": updated_at,
        "prompt": "test prompt",
        "pid": 1234,
        "session_type": "claude",
        "node_id": node_id,
    }


class TestBuildHomeView:
    """build_home_view 단위 테스트"""

    def test_normal_response_with_running_and_completed(self):
        """정상 응답: 실행 중 2개 + 완료 7개 → 실행 중 2개 + 완료 5개 표시"""
        running = [
            _make_session(f"sess-run-{i}", "running", f"작업 {i}")
            for i in range(2)
        ]
        completed = [
            _make_session(
                f"sess-done-{i}",
                "completed",
                f"완료 작업 {i}",
                updated_at=f"2026-03-23T0{i}:00:00Z",
            )
            for i in range(7)
        ]
        sessions = running + completed

        view = _build_view(sessions, total=9)

        # 타입과 기본 구조 검증
        assert view["type"] == "home"
        blocks = view["blocks"]

        # 헤더에 노드 이름 포함
        header = blocks[0]
        assert header["type"] == "header"
        assert NODE_NAME in header["text"]["text"]

        # 실행 중 세션 블록이 존재하는지
        block_texts = [
            b.get("text", {}).get("text", "")
            for b in blocks
            if b["type"] == "section"
        ]
        running_blocks = [t for t in block_texts if "작업 0" in t or "작업 1" in t]
        assert len(running_blocks) == 2

        # 완료 세션은 최대 5개
        completed_blocks = [t for t in block_texts if "완료 작업" in t]
        assert len(completed_blocks) == 5

    def test_no_running_sessions(self):
        """실행 중 세션 0개 → 안내 메시지 표시"""
        completed = [
            _make_session("sess-done-1", "completed", "완료 작업")
        ]

        view = _build_view(completed, total=1)
        blocks = view["blocks"]

        # "현재 실행 중인 세션이 없습니다" 안내 존재
        context_texts = []
        for b in blocks:
            if b["type"] == "context":
                for elem in b.get("elements", []):
                    context_texts.append(elem.get("text", ""))

        assert any("실행 중인 세션이 없습니다" in t for t in context_texts)

    def test_display_name_fallback_to_last_message(self):
        """display_name 없으면 last_message preview 표시"""
        session = _make_session(
            "sess-test-12345678",
            "running",
            display_name=None,
            last_message={"type": "assistant", "preview": "검색 중입니다...", "timestamp": "2026-03-23T02:00:00Z"},
        )

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        assert any("검색 중입니다..." in t for t in section_texts)

    def test_display_name_and_last_message_both_none(self):
        """display_name과 last_message 모두 없으면 세션 ID 뒷자리 표시"""
        session = _make_session(
            "sess-20260323-abcd1234",
            "running",
            display_name=None,
            last_message=None,
        )

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        assert any("abcd1234" in t for t in section_texts)

    def test_error_interrupted_sessions_in_finished_section(self):
        """error/interrupted 세션은 🔴 아이콘으로 최근 종료 섹션에 표시"""
        error_session = _make_session("sess-err-1", "error", "에러 세션")
        interrupted_session = _make_session("sess-int-1", "interrupted", "중단 세션")

        view = _build_view([error_session, interrupted_session], total=2)
        blocks = view["blocks"]

        # "실행 중인 세션이 없습니다" 안내가 표시되어야 함 (running이 없으므로)
        context_texts = []
        for b in blocks:
            if b["type"] == "context":
                for elem in b.get("elements", []):
                    context_texts.append(elem.get("text", ""))
        assert any("실행 중인 세션이 없습니다" in t for t in context_texts)

        # error/interrupted는 최근 종료 섹션에 🔴로 표시
        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        error_texts = [t for t in section_texts if "에러 세션" in t]
        assert len(error_texts) == 1
        assert "🔴" in error_texts[0]

        interrupted_texts = [t for t in section_texts if "중단 세션" in t]
        assert len(interrupted_texts) == 1
        assert "🔴" in interrupted_texts[0]

    def test_dashboard_link_buttons(self):
        """각 세션에 대시보드 링크 버튼이 포함됨"""
        session = _make_session("sess-20260323-link1234", "running", "테스트 세션")

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        # accessory 버튼의 url 검증
        buttons = []
        for b in blocks:
            acc = b.get("accessory", {})
            if acc.get("type") == "button" and "url" in acc:
                buttons.append(acc)

        assert len(buttons) >= 1
        assert buttons[0]["url"] == f"{DASHBOARD_BASE}sess-20260323-link1234"

    def test_dashboard_link_url_without_hash_suffix(self):
        """base URL에 # 없으면 /#를 붙여서 올바른 fragment URL 생성"""
        session = _make_session("sess-20260323-abcd5678", "running", "테스트 세션")

        view = build_home_view(
            [session],
            NODE_NAME,
            total=1,
            dashboard_base_url="http://localhost:4105",
        )
        blocks = view["blocks"]

        buttons = []
        for b in blocks:
            acc = b.get("accessory", {})
            if acc.get("type") == "button" and "url" in acc:
                buttons.append(acc)

        assert len(buttons) >= 1
        assert buttons[0]["url"] == "http://localhost:4105/#sess-20260323-abcd5678"

    def test_dashboard_link_url_with_hash_suffix(self):
        """base URL이 이미 #으로 끝나면 그대로 사용"""
        session = _make_session("sess-20260323-link1234", "running", "테스트 세션")

        view = build_home_view(
            [session],
            NODE_NAME,
            total=1,
            dashboard_base_url="https://soul.eiaserinnys.me/#",
        )
        blocks = view["blocks"]

        buttons = []
        for b in blocks:
            acc = b.get("accessory", {})
            if acc.get("type") == "button" and "url" in acc:
                buttons.append(acc)

        assert len(buttons) >= 1
        assert buttons[0]["url"] == "https://soul.eiaserinnys.me/#sess-20260323-link1234"

    def test_soulstream_button_text(self):
        """accessory 버튼 텍스트가 '소울스트림에서 보기'로 변경됨"""
        session = _make_session("sess-20260323-abcd1234", "running", "테스트 세션")

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        buttons = []
        for b in blocks:
            acc = b.get("accessory", {})
            if acc.get("type") == "button":
                buttons.append(acc)

        assert len(buttons) >= 1
        assert buttons[0]["text"]["text"] == "소울스트림에서 보기"

    def test_slack_button_shown_when_session_map_provided(self):
        """slack_session_map 제공 시 actions 블록에 두 버튼 표시"""
        session_id = "sess-20260323-abcd1234"
        session = _make_session(session_id, "running", "테스트 세션")
        slack_session = Session(
            thread_ts="1234567890.000001",
            channel_id="C12345",
            session_id=session_id,
            last_seen_ts="1234567890.000099",
        )

        view = build_home_view(
            [session],
            NODE_NAME,
            total=1,
            dashboard_base_url=DASHBOARD_BASE,
            slack_session_map={session_id: slack_session},
            slack_workspace_url="https://test.slack.com",
        )
        blocks = view["blocks"]

        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(actions_blocks) == 1
        elements = actions_blocks[0]["elements"]
        assert len(elements) == 2
        button_texts = [e["text"]["text"] for e in elements]
        assert "소울스트림에서 보기" in button_texts
        assert "슬랙에서 보기" in button_texts

    def test_slack_url_with_last_seen_ts(self):
        """last_seen_ts가 있으면 p{msg_ts_nodot}?thread_ts=...&cid=... 형태"""
        url = _build_slack_url(
            workspace_url="https://test.slack.com",
            channel_id="C12345",
            thread_ts="1234567890.000001",
            last_seen_ts="1234567890.000099",
        )
        assert url == "https://test.slack.com/archives/C12345/p1234567890000099?thread_ts=1234567890.000001&cid=C12345"

    def test_slack_url_without_last_seen_ts(self):
        """last_seen_ts가 없으면 p{thread_ts_nodot} 형태 (thread 파라미터 없음)"""
        url = _build_slack_url(
            workspace_url="https://test.slack.com",
            channel_id="C12345",
            thread_ts="1234567890.000001",
            last_seen_ts="",
        )
        assert url == "https://test.slack.com/archives/C12345/p1234567890000001"

    def test_no_slack_button_when_session_map_empty(self):
        """session_map 미제공 시 accessory 1-버튼만 표시"""
        session = _make_session("sess-20260323-abcd1234", "running", "테스트 세션")

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        # actions 블록 없음
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(actions_blocks) == 0

        # accessory 버튼 1개
        buttons = [b.get("accessory") for b in blocks if b.get("accessory")]
        assert len(buttons) == 1

    def test_completed_sessions_sorted_by_updated_at(self):
        """완료 세션은 updated_at 기준 최신순 정렬"""
        sessions = [
            _make_session("sess-old", "completed", "오래된", updated_at="2026-03-23T01:00:00Z"),
            _make_session("sess-new", "completed", "최신", updated_at="2026-03-23T03:00:00Z"),
            _make_session("sess-mid", "completed", "중간", updated_at="2026-03-23T02:00:00Z"),
        ]

        view = _build_view(sessions, total=3)
        blocks = view["blocks"]

        completed_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        # 최신이 먼저
        newest_idx = next(i for i, t in enumerate(completed_texts) if "최신" in t)
        oldest_idx = next(i for i, t in enumerate(completed_texts) if "오래된" in t)
        assert newest_idx < oldest_idx


class TestFetchSessions:
    """오케스트레이터 응답과 요청 계약."""

    def test_fetch_sessions_success(self):
        running = {
            "agentSessionId": "run-1", "status": "running", "displayName": "작업",
            "nodeId": "wsl", "createdAt": "2026-11-17T09:57:33.376Z",
            "updatedAt": "2026-11-17T10:00:44.665Z",
            "lastMessage": {"type": "user_message", "preview": "안녕",
                            "timestamp": "2026-11-17T10:00:44.665Z", "eventId": 81},
        }
        finished = {**running, "agentSessionId": "done-1", "status": "completed"}
        responses = [MagicMock(), MagicMock()]
        responses[0].json.return_value = {"sessions": [running], "total": 1}
        responses[1].json.return_value = {"sessions": [finished], "total": 3}
        with patch("seosoyoung.slackbot.handlers.home.requests.get", side_effect=responses):
            result = fetch_sessions("https://orch.example", "token")
        assert result["total"] == 1
        assert result["sessions"] == [
            {"agent_session_id": "run-1", "status": "running", "display_name": "작업",
             "node_id": "wsl", "created_at": "2026-11-17T09:57:33.376Z",
             "updated_at": "2026-11-17T10:00:44.665Z",
             "last_message": {"type": "user_message", "preview": "안녕",
                              "timestamp": "2026-11-17T10:00:44.665Z", "event_id": 81}},
            {"agent_session_id": "done-1", "status": "completed", "display_name": "작업",
             "node_id": "wsl", "created_at": "2026-11-17T09:57:33.376Z",
             "updated_at": "2026-11-17T10:00:44.665Z",
             "last_message": {"type": "user_message", "preview": "안녕",
                              "timestamp": "2026-11-17T10:00:44.665Z", "event_id": 81}},
        ]

    @pytest.mark.parametrize("node_id", [None, "eias-linegames-wsl"])
    def test_fetch_sessions_calls_correct_urls(self, node_id):
        response = MagicMock()
        response.json.return_value = {"sessions": [], "total": 0}
        with patch("seosoyoung.slackbot.handlers.home.requests.get", return_value=response) as get:
            fetch_sessions("https://orch.example", "token", node_id)
        node = {"node_id": node_id} if node_id else {}
        assert get.call_args_list == [
            (("https://orch.example/api/sessions",), {"headers": {"Authorization": "Bearer token"},
             "params": {"status": "running", **node}, "timeout": 5}),
            (("https://orch.example/api/sessions",), {"headers": {"Authorization": "Bearer token"},
             "params": {"status": "completed,error", "limit": 5, **node}, "timeout": 5}),
        ]

    def test_fetch_sessions_api_failure(self):
        import requests
        with patch("seosoyoung.slackbot.handlers.home.requests.get",
                   side_effect=requests.ConnectionError("Connection refused")):
            with pytest.raises(requests.ConnectionError):
                fetch_sessions("https://orch.example", "token")


class TestHandleAppHomeOpened:
    """등록된 이벤트 핸들러를 직접 실행한다."""

    def setup_method(self):
        app = MagicMock()
        self.client = MagicMock()
        self.logger = MagicMock()
        self.session_manager = MagicMock()
        self.session_manager.find_all_by_session_id.return_value = {}
        self.orchestrator = SimpleNamespace(url="https://orch.example", token="token", preferred_node="wsl")
        register_home_handlers(app, {
            "orchestrator": self.orchestrator, "dashboard_url": DASHBOARD_BASE,
            "session_manager": self.session_manager,
        })
        self.handle = app.event.return_value.call_args.args[0]

    def test_success_publishes_view(self):
        data = {"sessions": [_make_session("sess-test-11111111", "running", "테스트")], "total": 1}
        self.orchestrator.preferred_node = "eias-linegames"
        with patch("seosoyoung.slackbot.handlers.home.fetch_sessions", return_value=data) as fetch:
            self.handle({"user": "U123"}, self.client, self.logger)
        fetch.assert_called_once_with("https://orch.example", "token", "eias-linegames")
        self.session_manager.find_all_by_session_id.assert_called_once()
        self.client.views_publish.assert_called_once()
        assert self.client.views_publish.call_args.kwargs["view"]["type"] == "home"

    def test_api_failure_shows_error_view(self):
        with patch("seosoyoung.slackbot.handlers.home.fetch_sessions", side_effect=Exception("실패")):
            self.handle({"user": "U123", "tab": "home"}, self.client, self.logger)
        view = self.client.views_publish.call_args.kwargs["view"]
        assert "서버 연결 실패" in str(view)

    def test_messages_tab_does_not_fetch_or_publish(self):
        with patch("seosoyoung.slackbot.handlers.home.fetch_sessions") as fetch:
            self.handle({"user": "U123", "tab": "messages"}, self.client, self.logger)
        fetch.assert_not_called()
        self.client.views_publish.assert_not_called()

    @pytest.mark.parametrize("missing", ["url", "token"])
    def test_missing_orchestrator_settings_shows_error(self, missing):
        setattr(self.orchestrator, missing, "")
        with patch("seosoyoung.slackbot.handlers.home.requests.get") as get:
            self.handle({"user": "U123", "tab": "home"}, self.client, self.logger)
        get.assert_not_called()
        assert "서버 연결 실패" in str(self.client.views_publish.call_args.kwargs["view"])
