"""이벤트 노드 <-> 슬랙 메시지 매핑

소울스트림의 세분화 이벤트(thinking, tool_start 등)에 대응하는
슬랙 스레드 메시지 ts를 추적하는 자료구조입니다.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SlackNode:
    """이벤트 노드에 대응하는 슬랙 메시지"""
    event_id: int
    node_type: str           # "thinking" | "tool" | "text"
    msg_ts: str              # 슬랙 메시지 timestamp
    parent_event_id: Optional[int] = None
    tool_use_id: Optional[str] = None
    tool_name: Optional[str] = None
    completed: bool = False
    text_buffer: str = ""    # text_delta 누적 버퍼 (S7)


class SlackNodeMap:
    """이벤트 노드 <-> 슬랙 메시지 ts 매핑

    대시보드의 ProcessingContext를 슬랙에 맞게 번안.
    - _nodes: event_id -> SlackNode
    - _tool_use_index: tool_use_id -> event_id (tool_result 매칭용)
    - _last_thinking_by_parent: parent_event_id -> event_id (text가 병합할 대상)
    """

    def __init__(self):
        self._nodes: dict[int, SlackNode] = {}
        self._tool_use_index: dict[str, int] = {}
        self._last_thinking_by_parent: dict[Optional[int], int] = {}

    def add_thinking(
        self,
        event_id: int,
        msg_ts: str,
        parent_event_id: Optional[int] = None,
    ) -> SlackNode:
        """thinking 이벤트에 대응하는 노드 등록"""
        node = SlackNode(
            event_id=event_id,
            node_type="thinking",
            msg_ts=msg_ts,
            parent_event_id=parent_event_id,
        )
        self._nodes[event_id] = node
        self._last_thinking_by_parent[parent_event_id] = event_id
        return node

    def add_text(
        self,
        event_id: int,
        msg_ts: str,
        parent_event_id: Optional[int] = None,
    ) -> SlackNode:
        """독립 text 노드 등록 (thinking 없이 text_start가 도착한 경우, S6)

        _last_thinking_by_parent에 등록하여 find_thinking_for_text가
        thinking과 독립 text를 동일하게 찾도록 한다.
        """
        node = SlackNode(
            event_id=event_id,
            node_type="text",
            msg_ts=msg_ts,
            parent_event_id=parent_event_id,
        )
        self._nodes[event_id] = node
        self._last_thinking_by_parent[parent_event_id] = event_id
        return node

    def add_tool(
        self,
        event_id: int,
        msg_ts: str,
        tool_use_id: str,
        parent_event_id: Optional[int] = None,
        tool_name: Optional[str] = None,
    ) -> SlackNode:
        """tool_start 이벤트에 대응하는 노드 등록"""
        node = SlackNode(
            event_id=event_id,
            node_type="tool",
            msg_ts=msg_ts,
            parent_event_id=parent_event_id,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
        )
        self._nodes[event_id] = node
        if tool_use_id:
            self._tool_use_index[tool_use_id] = event_id
        return node

    def find_thinking_for_text(
        self,
        parent_event_id: Optional[int],
    ) -> Optional[SlackNode]:
        """text 이벤트가 병합할 대상 노드 검색

        thinking 노드와 독립 text 노드 모두 동일하게 찾는다 (S6).
        """
        event_id = self._last_thinking_by_parent.get(parent_event_id)
        if event_id is None:
            return None
        return self._nodes.get(event_id)

    def find_tool_by_use_id(
        self,
        tool_use_id: str,
    ) -> Optional[SlackNode]:
        """tool_use_id로 tool 노드 검색"""
        event_id = self._tool_use_index.get(tool_use_id)
        if event_id is None:
            return None
        return self._nodes.get(event_id)

    def mark_completed(self, event_id: int) -> Optional[SlackNode]:
        """노드를 완료 상태로 마킹"""
        node = self._nodes.get(event_id)
        if node:
            node.completed = True
        return node

    def clear_completed(self) -> int:
        """완료된 노드를 정리. 정리된 노드 수를 반환."""
        completed_ids = [eid for eid, node in self._nodes.items() if node.completed]
        for eid in completed_ids:
            node = self._nodes.pop(eid)
            if node.tool_use_id:
                self._tool_use_index.pop(node.tool_use_id, None)
            parent = node.parent_event_id
            if self._last_thinking_by_parent.get(parent) == eid:
                del self._last_thinking_by_parent[parent]
        return len(completed_ids)
