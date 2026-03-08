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


@dataclass
class InputRequestNode:
    """AskUserQuestion 이벤트에 대응하는 슬랙 메시지"""
    request_id: str
    msg_ts: str
    questions: list = field(default_factory=list)
    agent_session_id: str = ""
    answered: bool = False


class SlackNodeMap:
    """이벤트 노드 <-> 슬랙 메시지 ts 매핑

    대시보드의 ProcessingContext를 슬랙에 맞게 번안.
    - _nodes: event_id -> SlackNode
    - _tool_use_index: tool_use_id -> event_id (tool_result 매칭용)
    - _last_text_by_parent: parent_event_id -> event_id (text_delta/text_end가 찾을 대상)
    """

    def __init__(self):
        self._nodes: dict[int, SlackNode] = {}
        self._tool_use_index: dict[str, int] = {}
        self._last_text_by_parent: dict[Optional[int], int] = {}
        self._input_requests: dict[str, InputRequestNode] = {}  # request_id -> InputRequestNode

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
        return node

    def add_text(
        self,
        event_id: int,
        msg_ts: str,
        parent_event_id: Optional[int] = None,
    ) -> SlackNode:
        """text 노드 등록

        _last_text_by_parent에 등록하여 find_text_node가
        text_delta/text_end에서 대상 노드를 찾도록 한다.
        """
        node = SlackNode(
            event_id=event_id,
            node_type="text",
            msg_ts=msg_ts,
            parent_event_id=parent_event_id,
        )
        self._nodes[event_id] = node
        self._last_text_by_parent[parent_event_id] = event_id
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

    def find_text_node(
        self,
        parent_event_id: Optional[int],
    ) -> Optional[SlackNode]:
        """parent_event_id에 대응하는 text 노드 검색

        text_start에서 등록한 text 노드를 text_delta/text_end에서 찾는다.
        """
        event_id = self._last_text_by_parent.get(parent_event_id)
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

    def _remove_from_indexes(self, node: SlackNode) -> None:
        """완료된 노드를 룩업 인덱스에서 제거 (노드 자체는 _nodes에 유지)"""
        parent = node.parent_event_id
        if self._last_text_by_parent.get(parent) == node.event_id:
            del self._last_text_by_parent[parent]
        if node.tool_use_id:
            self._tool_use_index.pop(node.tool_use_id, None)

    def mark_completed(self, event_id: int) -> Optional[SlackNode]:
        """노드를 완료 상태로 마킹"""
        node = self._nodes.get(event_id)
        if node:
            node.completed = True
        return node

    def mark_completed_and_remove(self, event_id: int) -> Optional[SlackNode]:
        """노드를 완료 상태로 마킹하고 룩업 인덱스에서 즉시 제거

        SSE 재연결 시 이미 처리한 이벤트가 재생되는 경우,
        룩업 인덱스에 노드가 남아 있으면 중복 삭제 시도가 발생합니다.
        완료 즉시 인덱스에서 제거하여 find_text_node, find_tool_by_use_id가
        이미 처리된 노드를 반환하지 않도록 합니다.
        """
        node = self._nodes.get(event_id)
        if not node:
            return None
        node.completed = True
        self._remove_from_indexes(node)
        return node

    def clear_completed(self) -> int:
        """완료된 노드를 정리. 정리된 노드 수를 반환."""
        completed_ids = [eid for eid, node in self._nodes.items() if node.completed]
        for eid in completed_ids:
            node = self._nodes.pop(eid)
            self._remove_from_indexes(node)
        return len(completed_ids)

    # --- Input Request (AskUserQuestion) ---

    def add_input_request(
        self,
        request_id: str,
        msg_ts: str,
        questions: list,
        agent_session_id: str = "",
    ) -> InputRequestNode:
        """input_request 이벤트에 대응하는 노드 등록"""
        node = InputRequestNode(
            request_id=request_id,
            msg_ts=msg_ts,
            questions=questions,
            agent_session_id=agent_session_id,
        )
        self._input_requests[request_id] = node
        return node

    def find_input_request(self, request_id: str) -> Optional[InputRequestNode]:
        """request_id로 input_request 노드 검색"""
        return self._input_requests.get(request_id)

    def mark_input_request_answered(self, request_id: str) -> Optional[InputRequestNode]:
        """input_request를 응답 완료 상태로 마킹"""
        node = self._input_requests.get(request_id)
        if node:
            node.answered = True
        return node
