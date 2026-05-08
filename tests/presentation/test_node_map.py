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
        node = nm.add_thinking(event_id=1, msg_ts="1234.5678")
        assert node.event_id == 1
        assert node.node_type == "thinking"
        assert node.msg_ts == "1234.5678"

    def test_add_tool(self):
        nm = SlackNodeMap()
        node = nm.add_tool(event_id=2, msg_ts="1234.5679", tool_use_id="tu_123", tool_name="Bash")
        assert node.event_id == 2
        assert node.tool_use_id == "tu_123"
        assert node.tool_name == "Bash"

    def test_find_text_node(self):
        """add_text 후 활성 슬롯에서 노드를 찾는다"""
        nm = SlackNodeMap()
        nm.add_text(event_id=1, msg_ts="ts1")
        node = nm.find_text_node()
        assert node is not None
        assert node.event_id == 1

    def test_find_text_node_not_found(self):
        """활성 슬롯이 비어 있으면 None 반환"""
        nm = SlackNodeMap()
        node = nm.find_text_node()
        assert node is None

    def test_thinking_not_in_text_index(self):
        """add_thinking은 활성 텍스트 슬롯을 채우지 않는다"""
        nm = SlackNodeMap()
        nm.add_thinking(event_id=1, msg_ts="ts1")
        node = nm.find_text_node()
        assert node is None

    def test_find_tool_by_use_id(self):
        nm = SlackNodeMap()
        nm.add_tool(event_id=3, msg_ts="ts3", tool_use_id="tu_456")
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
        """독립 text 노드가 활성 슬롯에 등록되는지"""
        nm = SlackNodeMap()
        nm.add_text(event_id=10, msg_ts="ts10")
        node = nm.find_text_node()
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
        nm.add_text(event_id=1, msg_ts="ts1")
        nm.add_tool(event_id=2, msg_ts="ts2", tool_use_id="tu_1")
        nm.mark_completed(1)
        count = nm.clear_completed()
        assert count == 1
        assert nm.find_text_node() is None
        # tool은 아직 있어야 함
        assert nm.find_tool_by_use_id("tu_1") is not None

    def test_clear_completed_with_tools(self):
        nm = SlackNodeMap()
        nm.add_tool(event_id=3, msg_ts="ts3", tool_use_id="tu_2")
        nm.mark_completed(3)
        count = nm.clear_completed()
        assert count == 1
        assert nm.find_tool_by_use_id("tu_2") is None

    # --- 단일 활성 슬롯 모델 신규 케이스 ---

    def test_add_text_overwrites_active_slot(self):
        """새 add_text가 활성 슬롯을 덮어쓴다 (text_end 누락 fail-safe)"""
        nm = SlackNodeMap()
        nm.add_text(event_id=1, msg_ts="ts1")
        nm.add_text(event_id=2, msg_ts="ts2")
        node = nm.find_text_node()
        assert node is not None and node.event_id == 2

    def test_text_end_releases_active_slot(self):
        """mark_completed_and_remove가 활성 슬롯을 비운다"""
        nm = SlackNodeMap()
        nm.add_text(event_id=1, msg_ts="ts1")
        nm.mark_completed_and_remove(1)
        assert nm.find_text_node() is None

    def test_active_text_slot_isolation_per_instance(self):
        """🔵 #9 — 두 SlackNodeMap 인스턴스의 활성 슬롯이 격리됨"""
        nm_a = SlackNodeMap()
        nm_b = SlackNodeMap()
        nm_a.add_text(event_id=1, msg_ts="ts_a")
        nm_b.add_text(event_id=99, msg_ts="ts_b")
        assert nm_a.find_text_node().event_id == 1
        assert nm_b.find_text_node().event_id == 99

    def test_clear_completed_thinking_does_not_clear_active_text_slot(self):
        """node_type 가드 검증 — thinking 노드 정리가 활성 텍스트 슬롯을 건드리지 않는다.

        실제 운영에서는 SSE 스트림의 event_id가 단조증가라 충돌이 일어나지 않지만,
        invariant를 코드로 명시하기 위해 추가한 가드를 보호한다 (P1 #3).
        """
        nm = SlackNodeMap()
        nm.add_text(event_id=5, msg_ts="ts_text")
        # thinking 노드를 별도 event_id에 추가
        nm.add_thinking(event_id=99, msg_ts="ts_thinking")
        nm.mark_completed(99)
        nm.clear_completed()
        # 활성 텍스트 슬롯은 그대로
        node = nm.find_text_node()
        assert node is not None and node.event_id == 5

    def test_multiturn_text_serial_equivalence(self):
        """🔴 #5 — 멀티턴 시리얼 케이스에서 두 텍스트 노드가 정확히 격리된다.

        턴1 add_text → mark_completed_and_remove(slot 비움) → 턴2 add_text.
        이전 dict 모델과 행동 등가 (분석 캐시 §4.1).
        """
        nm = SlackNodeMap()
        # 턴 1
        nm.add_text(event_id=1, msg_ts="ts_turn1")
        node1 = nm.find_text_node()
        assert node1.event_id == 1
        nm.mark_completed_and_remove(1)
        assert nm.find_text_node() is None
        # 턴 2
        nm.add_text(event_id=2, msg_ts="ts_turn2")
        node2 = nm.find_text_node()
        assert node2.event_id == 2
        # 두 노드는 별개 (msg_ts 다름)
        assert node1.msg_ts != node2.msg_ts


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
        nm.add_thinking(event_id=1, msg_ts="ts-thinking")
        nm.add_input_request("req-1", "ts-ir", [])
        # 일반 노드 clear가 input_request에 영향 없음
        nm.mark_completed(1)
        nm.clear_completed()
        assert nm.find_input_request("req-1") is not None
