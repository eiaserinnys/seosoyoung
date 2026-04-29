"""노드 라우팅 명령 핸들러 테스트

순수 로직 테스트:
- _find_current_node_id: 현재 노드 매칭
- _build_node_blocks: 슬랙 블록 구성
- _relative_time: 상대 시간 포맷
- _update_soul_url: 메모리 + .env 갱신
- _fetch_orch_nodes: HTTP 조회

통합 테스트:
- handle_node: 미설정/권한/정상 플로우
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── 테스트 데이터 ────────────────────────────────────────────────


def _make_nodes(count=2):
    """테스트용 노드 목록 생성"""
    nodes = []
    for i in range(count):
        nodes.append({
            "nodeId": f"node-{i}",
            "host": f"host-{i}.example.com",
            "port": 4105 + i,
            "sessionCount": i * 3,
            "connectedAt": (
                datetime.now(timezone.utc) - timedelta(hours=i + 1)
            ).isoformat(),
            "status": "connected",
        })
    return nodes


# ── _find_current_node_id ────────────────────────────────────────


class TestFindCurrentNodeId:
    def test_exact_match(self):
        from seosoyoung.slackbot.handlers.node import _find_current_node_id

        nodes = _make_nodes(2)
        url = f"http://{nodes[1]['host']}:{nodes[1]['port']}"
        assert _find_current_node_id(nodes, url) == "node-1"

    def test_localhost_fallback_single_candidate(self):
        from seosoyoung.slackbot.handlers.node import _find_current_node_id

        nodes = [
            {"nodeId": "local-1", "host": "myhost", "port": 4105},
            {"nodeId": "remote-1", "host": "remote.example.com", "port": 4200},
        ]
        # localhost URL, port 4105 매칭 → 후보 1개이므로 반환
        assert _find_current_node_id(nodes, "http://localhost:4105") == "local-1"

    def test_localhost_fallback_multiple_same_port_returns_none(self):
        from seosoyoung.slackbot.handlers.node import _find_current_node_id

        nodes = [
            {"nodeId": "a", "host": "host-a", "port": 4105},
            {"nodeId": "b", "host": "host-b", "port": 4105},
        ]
        # localhost:4105 → 포트가 같은 후보 2개 → 모호 → None
        assert _find_current_node_id(nodes, "http://127.0.0.1:4105") is None

    def test_no_match_returns_none(self):
        from seosoyoung.slackbot.handlers.node import _find_current_node_id

        nodes = _make_nodes(2)
        assert _find_current_node_id(nodes, "http://unknown.host:9999") is None

    def test_127_0_0_1_treated_as_localhost(self):
        from seosoyoung.slackbot.handlers.node import _find_current_node_id

        nodes = [{"nodeId": "n1", "host": "server", "port": 5000}]
        assert _find_current_node_id(nodes, "http://127.0.0.1:5000") == "n1"


# ── _build_node_blocks ───────────────────────────────────────────


class TestBuildNodeBlocks:
    def test_current_node_has_primary_style(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(2)
        current_url = f"http://{nodes[0]['host']}:{nodes[0]['port']}"
        blocks = _build_node_blocks(nodes, current_url)

        # 헤더 + 노드 섹션 2개 + 컨텍스트
        buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section" and "accessory" in b
        ]
        assert len(buttons) == 2
        # 첫 번째 노드(현재)는 primary
        assert buttons[0].get("style") == "primary"
        # 두 번째 노드는 style 없음
        assert "style" not in buttons[1]

    def test_no_current_node_no_primary(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(2)
        blocks = _build_node_blocks(nodes, "http://unknown:9999")

        buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section" and "accessory" in b
        ]
        for btn in buttons:
            assert "style" not in btn

    def test_empty_nodes(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        blocks = _build_node_blocks([], "http://x:1")
        # 헤더 + 컨텍스트만 있어야 함
        section_blocks = [b for b in blocks if b.get("type") == "section"]
        assert len(section_blocks) == 0

    def test_context_block_shows_current_url(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        blocks = _build_node_blocks(_make_nodes(1), "http://my-server:4105")
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        text_element = context_blocks[0]["elements"][0]["text"]
        assert "http://my-server:4105" in text_element

    def test_button_value_contains_node_info(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(1)
        blocks = _build_node_blocks(nodes, "")
        buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section" and "accessory" in b
        ]
        value = json.loads(buttons[0]["value"])
        assert value["nodeId"] == "node-0"
        assert value["host"] == nodes[0]["host"]
        assert value["port"] == nodes[0]["port"]


# ── _relative_time ───────────────────────────────────────────────


class TestRelativeTime:
    def test_just_now(self):
        from seosoyoung.slackbot.handlers.node import _relative_time

        now = datetime.now(timezone.utc).isoformat()
        assert _relative_time(now) == "방금 전"

    def test_minutes(self):
        from seosoyoung.slackbot.handlers.node import _relative_time

        t = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert _relative_time(t) == "5분 전"

    def test_hours(self):
        from seosoyoung.slackbot.handlers.node import _relative_time

        t = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        assert _relative_time(t) == "2시간 전"

    def test_days(self):
        from seosoyoung.slackbot.handlers.node import _relative_time

        t = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        assert _relative_time(t) == "3일 전"

    def test_1_minute(self):
        from seosoyoung.slackbot.handlers.node import _relative_time

        t = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
        assert _relative_time(t) == "1분 전"


# ── _update_soul_url ─────────────────────────────────────────────


class TestUpdateSoulUrl:
    def test_updates_memory(self):
        from seosoyoung.slackbot.handlers.node import _update_soul_url

        original = os.environ.get("SEOSOYOUNG_SOUL_URL", "")
        try:
            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=""):
                _update_soul_url("http://new-host:4105")
            from seosoyoung.slackbot.config import Config
            assert Config.claude.soul_url == "http://new-host:4105"
            assert os.environ["SEOSOYOUNG_SOUL_URL"] == "http://new-host:4105"
        finally:
            os.environ["SEOSOYOUNG_SOUL_URL"] = original
            Config.claude.soul_url = original

    def test_returns_false_when_no_dotenv(self):
        from seosoyoung.slackbot.handlers.node import _update_soul_url

        original = os.environ.get("SEOSOYOUNG_SOUL_URL", "")
        try:
            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=""):
                result = _update_soul_url("http://x:1")
            assert result is False
        finally:
            os.environ["SEOSOYOUNG_SOUL_URL"] = original
            from seosoyoung.slackbot.config import Config
            Config.claude.soul_url = original

    def test_writes_to_dotenv_file(self):
        from seosoyoung.slackbot.handlers.node import _update_soul_url

        original = os.environ.get("SEOSOYOUNG_SOUL_URL", "")
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
                f.write("SEOSOYOUNG_SOUL_URL=http://old:4105\n")
                env_path = f.name

            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=env_path):
                result = _update_soul_url("http://new:5000")

            assert result is True
            with open(env_path) as f:
                content = f.read()
            assert "http://new:5000" in content
            os.unlink(env_path)
        finally:
            os.environ["SEOSOYOUNG_SOUL_URL"] = original
            from seosoyoung.slackbot.config import Config
            Config.claude.soul_url = original


# ── _fetch_orch_nodes ────────────────────────────────────────────


class TestFetchOrchNodes:
    def test_success(self):
        from seosoyoung.slackbot.handlers.node import _fetch_orch_nodes

        nodes_data = _make_nodes(2)
        response_body = json.dumps({"nodes": nodes_data}).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            result = _fetch_orch_nodes("http://orch:5200", "my-token")

        assert len(result) == 2
        assert result[0]["nodeId"] == "node-0"
        # Bearer 토큰 헤더 확인
        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer my-token"

    def test_empty_token_no_auth_header(self):
        from seosoyoung.slackbot.handlers.node import _fetch_orch_nodes

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"nodes": []}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            _fetch_orch_nodes("http://orch:5200", "")

        req = mock_open.call_args[0][0]
        assert not req.has_header("Authorization")

    def test_connection_error_propagates(self):
        from seosoyoung.slackbot.handlers.node import _fetch_orch_nodes
        from urllib.error import URLError

        with patch("urllib.request.urlopen", side_effect=URLError("refused")):
            with pytest.raises(URLError):
                _fetch_orch_nodes("http://orch:5200", "tok")


# ── handle_node 통합 테스트 ──────────────────────────────────────


class TestHandleNode:
    def test_no_permission(self):
        from seosoyoung.slackbot.handlers.node import handle_node

        say = MagicMock()
        handle_node(
            say=say, ts="123", thread_ts=None, user_id="U999",
            client=MagicMock(), check_permission=lambda uid, c: False,
        )
        say.assert_called_once()
        assert "관리자 권한" in say.call_args[1]["text"]

    def test_orchestrator_not_configured(self):
        from seosoyoung.slackbot.handlers.node import handle_node
        from seosoyoung.slackbot.config import Config

        original = Config.orchestrator.url
        try:
            Config.orchestrator.url = ""
            say = MagicMock()
            handle_node(
                say=say, ts="123", thread_ts=None, user_id="U1",
                client=MagicMock(), check_permission=lambda uid, c: True,
            )
            say.assert_called_once()
            assert "SOULSTREAM_ORCH_URL" in say.call_args[1]["text"]
        finally:
            Config.orchestrator.url = original

    def test_connection_error(self):
        from seosoyoung.slackbot.handlers.node import handle_node
        from seosoyoung.slackbot.config import Config

        original_url = Config.orchestrator.url
        try:
            Config.orchestrator.url = "http://orch:5200"
            say = MagicMock()

            with patch(
                "seosoyoung.slackbot.handlers.node._fetch_orch_nodes",
                side_effect=Exception("timeout"),
            ):
                handle_node(
                    say=say, ts="123", thread_ts=None, user_id="U1",
                    client=MagicMock(), check_permission=lambda uid, c: True,
                )
            assert "연결할 수 없습니다" in say.call_args[1]["text"]
        finally:
            Config.orchestrator.url = original_url

    def test_empty_nodes(self):
        from seosoyoung.slackbot.handlers.node import handle_node
        from seosoyoung.slackbot.config import Config

        original_url = Config.orchestrator.url
        try:
            Config.orchestrator.url = "http://orch:5200"
            say = MagicMock()

            with patch(
                "seosoyoung.slackbot.handlers.node._fetch_orch_nodes",
                return_value=[],
            ):
                handle_node(
                    say=say, ts="123", thread_ts=None, user_id="U1",
                    client=MagicMock(), check_permission=lambda uid, c: True,
                )
            assert "연결된 노드가 없습니다" in say.call_args[1]["text"]
        finally:
            Config.orchestrator.url = original_url

    def test_success_shows_blocks(self):
        from seosoyoung.slackbot.handlers.node import handle_node
        from seosoyoung.slackbot.config import Config

        original_url = Config.orchestrator.url
        try:
            Config.orchestrator.url = "http://orch:5200"
            say = MagicMock()

            with patch(
                "seosoyoung.slackbot.handlers.node._fetch_orch_nodes",
                return_value=_make_nodes(2),
            ):
                handle_node(
                    say=say, ts="123", thread_ts="456", user_id="U1",
                    client=MagicMock(), check_permission=lambda uid, c: True,
                )
            call_kwargs = say.call_args[1]
            assert "blocks" in call_kwargs
            assert call_kwargs["thread_ts"] == "456"
        finally:
            Config.orchestrator.url = original_url


# ── mention.py 통합: "노드" 명령어 라우팅 ────────────────────────


class TestNodeCommandRouting:
    def test_node_in_admin_commands(self):
        from seosoyoung.slackbot.handlers.mention import _ADMIN_COMMANDS
        assert "노드" in _ADMIN_COMMANDS

    def test_node_in_command_dispatch(self):
        from seosoyoung.slackbot.handlers.mention import _COMMAND_DISPATCH
        from seosoyoung.slackbot.handlers.node import handle_node
        assert _COMMAND_DISPATCH.get("노드") is handle_node
