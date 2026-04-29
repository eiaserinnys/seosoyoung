"""노드 라우팅 명령 핸들러 테스트

순수 로직 테스트:
- _build_node_blocks: 슬랙 블록 구성 (preferred_node 기반)
- _relative_time: 상대 시간 포맷
- _update_preferred_node: 메모리 + .env 갱신
- _fetch_orch_nodes: HTTP 조회

통합 테스트:
- handle_node: 미설정/권한/정상 플로우
- register_node_handlers: 액션 핸들러 등록 및 동작
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ── 테스트 데이터 ───────────────────────────────────────────────


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


# ── _build_node_blocks ──────────────────────────────────────────


class TestBuildNodeBlocks:
    def test_preferred_node_has_primary_style(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(2)
        blocks = _build_node_blocks(nodes, "node-1")

        # 노드 섹션의 버튼 추출 (자동 버튼 제외)
        node_buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select"
        ]
        assert len(node_buttons) == 2
        # node-0은 style 없음, node-1은 primary
        assert "style" not in node_buttons[0]
        assert node_buttons[1].get("style") == "primary"

    def test_auto_routing_primary_when_no_preferred(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(2)
        blocks = _build_node_blocks(nodes, None)

        # 자동 버튼이 primary여야 함
        auto_buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select_auto"
        ]
        assert len(auto_buttons) == 1
        assert auto_buttons[0].get("style") == "primary"

        # 노드 버튼은 style 없어야 함
        node_buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select"
        ]
        for btn in node_buttons:
            assert "style" not in btn

    def test_no_current_node_no_primary_on_nodes(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(2)
        blocks = _build_node_blocks(nodes, None)

        node_buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select"
        ]
        for btn in node_buttons:
            assert "style" not in btn

    def test_empty_nodes_has_auto_button_only(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        blocks = _build_node_blocks([], None)
        node_sections = [
            b for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select"
        ]
        assert len(node_sections) == 0
        # 자 버튼은 있어야 함
        auto_sections = [
            b for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select_auto"
        ]
        assert len(auto_sections) == 1

    def test_context_block_shows_fixed_routing(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        blocks = _build_node_blocks(_make_nodes(1), "node-0")
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        text_element = context_blocks[0]["elements"][0]["text"]
        assert "node-0" in text_element
        assert "고정" in text_element

    def test_context_block_shows_auto_routing(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        blocks = _build_node_blocks(_make_nodes(1), None)
        context_blocks = [b for b in blocks if b.get("type") == "context"]
        assert len(context_blocks) == 1
        text_element = context_blocks[0]["elements"][0]["text"]
        assert "자동" in text_element
        assert "최소 세션 노드" in text_element

    def test_button_value_is_node_id(self):
        from seosoyoung.slackbot.handlers.node import _build_node_blocks

        nodes = _make_nodes(1)
        blocks = _build_node_blocks(nodes, None)
        node_buttons = [
            b["accessory"]
            for b in blocks
            if b.get("type") == "section"
            and "accessory" in b
            and b["accessory"].get("action_id") == "node_select"
        ]
        assert len(node_buttons) == 1
        assert node_buttons[0]["value"] == "node-0"


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


# ── _update_preferred_node ─────────────────────────────────────


class TestUpdatePreferredNode:
    def test_updates_memory(self):
        from seosoyoung.slackbot.handlers.node import _update_preferred_node
        from seosoyoung.slackbot.config import Config

        original = Config.orchestrator.preferred_node
        try:
            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=""):
                _update_preferred_node("my-node")
            assert Config.orchestrator.preferred_node == "my-node"
            assert os.environ["SOULSTREAM_PREFERRED_NODE"] == "my-node"
        finally:
            Config.orchestrator.preferred_node = original
            os.environ["SOULSTREAM_PREFERRED_NODE"] = original

    def test_none_clears_preferred_node(self):
        from seosoyoung.slackbot.handlers.node import _update_preferred_node
        from seosoyoung.slackbot.config import Config

        original = Config.orchestrator.preferred_node
        try:
            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=""):
                _update_preferred_node("my-node")
                _update_preferred_node(None)
            assert Config.orchestrator.preferred_node == ""
            assert os.environ["SOULSTREAM_PREFERRED_NODE"] == ""
        finally:
            Config.orchestrator.preferred_node = original
            os.environ["SOULSTREAM_PREFERRED_NODE"] = original

    def test_returns_false_when_no_dotenv(self):
        from seosoyoung.slackbot.handlers.node import _update_preferred_node
        from seosoyoung.slackbot.config import Config

        original = Config.orchestrator.preferred_node
        try:
            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=""):
                result = _update_preferred_node("x")
            assert result is False
        finally:
            Config.orchestrator.preferred_node = original
            os.environ["SOULSTREAM_PREFERRED_NODE"] = original

    def test_writes_to_dotenv_file(self):
        from seosoyoung.slackbot.handlers.node import _update_preferred_node
        from seosoyoung.slackbot.config import Config

        original = Config.orchestrator.preferred_node
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
                f.write("SOULSTREAM_PREFERRED_NODE=\n")
                env_path = f.name

            with patch("seosoyoung.slackbot.handlers.node.find_dotenv", return_value=env_path):
                result = _update_preferred_node("node-42")

            assert result is True
            with open(env_path) as f:
                content = f.read()
            assert "node-42" in content
            os.unlink(env_path)
        finally:
            Config.orchestrator.preferred_node = original
            os.environ["SOULSTREAM_PREFERRED_NODE"] = original


# ── _fetch_orch_nodes ───────────────────────────────────────────


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


# ── handle_node 통 테스트 ─────────────────────────────────────


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


# ── mention.py 통합: "노드" 명령어 라팅 ───────────────────────


class TestNodeCommandRouting:
    def test_node_in_admin_commands(self):
        from seosoyoung.slackbot.handlers.mention import _ADMIN_COMMANDS
        assert "노드" in _ADMIN_COMMANDS

    def test_node_in_command_dispatch(self):
        from seosoyoung.slackbot.handlers.mention import _COMMAND_DISPATCH
        from seosoyoung.slackbot.handlers.node import handle_node
        assert _COMMAND_DISPATCH.get("노드") is handle_node
