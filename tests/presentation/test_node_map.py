"""SlackNodeMap 단위 테스트"""

import pytest
from seosoyoung.slackbot.presentation.node_map import (
    InputRequestNode,
    SlackNode,
    SlackNodeMap,
)


class TestSlackNodeMap:
    def test_add_thinking(self):
        nm = SlackNodeMap()
        node = nm.add_thinking(event_id=1, msg_ts="1234.5678", parent_event_id=None)
        assert node.event_id == 1
        assert node.node_type == "thinking"
        assert node.msg_ts == "1234.5678"

    def test_add_tool(self):
        nm = SlackNodeMap()
        node = nm.add_tool(event_id=2, msg_ts="1234.5679", tool_use_id="tu_123", parent_event_id=1, tool_name="Bash")
        assert node.event_id == 2
        assert node.tool_use_id == "tu_123"
        assert node.tool_name == "Bash"

    def test_find_text_node(self):
        nm = SlackNodeMap()
        nm.add_text(event_id=1, msg_ts="ts1", parent_event_id=100)
        node = nm.find_text_node(parent_event_id=100)
        assert node is not None
        assert node.event_id == 1

    def test_find_text_node_not_found(self):
        nm = SlackNodeMap()
        node = nm.find_text_node(parent_event_id=999)
        assert node is None

    def test_thinking_not_in_text_index(self):
        """Phase 3: add_thinking은 _last_text_by_parent에 등록하지 않는다"""
        nm = SlackNodeMap()
        nm.add_thinking(event_id=1, msg_ts="ts1", parent_event_id=100)
        node = nm.find_text_node(parent_event_id=100)
        assert node is None

    def test_find_tool_by_use_id(self):
        nm = SlackNodeMap()
        nm.add_tool(event_id=3, msg_ts="ts3", tool_use_id="tu_456", parent_event_id=1)
        node = nm.find_tool_by_use_id("tu_456")
        assert node is not None
        assert node.event_id == 3

    def test_find_tool_by_use_id_not_found(self):
        nm = SlackNodeMap()
        node = nm.find_tool_by_use_id("nonexistent")
        assert node is None

    def test_mark_completed(self):
        nm = SlackNodeMap()
        nm.add_thinking(event_id=1, msg_ts="ts1")
        node = nm.mark_completed(1)
        assert node is not None
        assert node.completed is True

    def test_mark_completed_nonexistent(self):
        nm = SlackNodeMap()
        node = nm.mark_completed(999)
        assert node is None

    def test_add_text_independent(self):
        """독립 text 노드가 _last_text_by_parent에 등록되는지 (S6)"""
        nm = SlackNodeMap()
        nm.add_text(event_id=10, msg_ts="ts10", parent_event_id=5)
        node = nm.find_text_node(parent_event_id=5)
        assert node is not None
        assert node.event_id == 10
        assert node.node_type == "text"

    def test_text_buffer_accumulation(self):
        """text_buffer 누적 테스트 (S7)"""
        nm = SlackNodeMap()
        node = nm.add_thinking(event_id=1, msg_ts="ts1")
        node.text_buffer = ""
        node.text_buffer += "Hello "
        node.text_buffer += "World"
        assert node.text_buffer == "Hello World"

    def test_clear_completed(self):
        """완료된 노드 정리 (C1 수정)"""
        nm = SlackNodeMap()
        nm.add_text(event_id=1, msg_ts="ts1", parent_event_id=100)
        nm.add_tool(event_id=2, msg_ts="ts2", tool_use_id="tu_1", parent_event_id=100)
        nm.mark_completed(1)
        count = nm.clear_completed()
        assert count == 1
        assert nm.find_text_node(parent_event_id=100) is None
        # tool은 아직 있어야 함
        assert nm.find_tool_by_use_id("tu_1") is not None

    def test_clear_completed_with_tools(self):
        nm = SlackNodeMap()
        nm.add_tool(event_id=3, msg_ts="ts3", tool_use_id="tu_2")
        nm.mark_completed(3)
        count = nm.clear_completed()
        assert count == 1
        assert nm.find_tool_by_use_id("tu_2") is None


class TestInputRequestNode:
    """InputRequestNode 관련 SlackNodeMap 메서드 테스트"""

    def test_add_input_request(self):
        nm = SlackNodeMap()
        questions = [{"question": "Q1", "options": [{"label": "A"}]}]
        node = nm.add_input_request(
            request_id="req-1", msg_ts="ts-ir-1",
            questions=questions, agent_session_id="sess-001",
        )
        assert isinstance(node, InputRequestNode)
        assert node.request_id == "req-1"
        assert node.msg_ts == "ts-ir-1"
        assert node.questions == questions
        assert node.agent_session_id == "sess-001"
        assert node.answered is False

    def test_find_input_request(self):
        nm = SlackNodeMap()
        nm.add_input_request("req-1", "ts-1", [])
        found = nm.find_input_request("req-1")
        assert found is not None
        assert found.request_id == "req-1"

    def test_find_input_request_not_found(self):
        nm = SlackNodeMap()
        assert nm.find_input_request("nonexistent") is None

    def test_mark_input_request_answered(self):
        nm = SlackNodeMap()
        nm.add_input_request("req-1", "ts-1", [])
        node = nm.mark_input_request_answered("req-1")
        assert node is not None
        assert node.answered is True

    def test_mark_input_request_answered_not_found(self):
        nm = SlackNodeMap()
        assert nm.mark_input_request_answered("nonexistent") is None

    def test_multiple_input_requests(self):
        nm = SlackNodeMap()
        nm.add_input_request("req-1", "ts-1", [{"question": "Q1"}])
        nm.add_input_request("req-2", "ts-2", [{"question": "Q2"}])
        assert nm.find_input_request("req-1").msg_ts == "ts-1"
        assert nm.find_input_request("req-2").msg_ts == "ts-2"

    def test_input_request_independent_from_regular_nodes(self):
        """input_request 노드는 일반 SlackNode와 독립적"""
        nm = SlackNodeMap()
        nm.add_thinking(event_id=1, msg_ts="ts-thinking", parent_event_id=None)
        nm.add_input_request("req-1", "ts-ir", [])
        # 일반 노드 clear가 input_request에 영향 없음
        nm.mark_completed(1)
        nm.clear_completed()
        assert nm.find_input_request("req-1") is not None
