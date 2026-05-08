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
    - _active_text_event_id: text_start ~ text_end 사이의 활성 text 노드 단일 슬롯.
      한 시점에 활성 text 블록은 1개라는 invariant에 기반 (Anthropic Messages API
      스트리밍에서 text 블록은 시리얼). 이전 모델(`_last_text_by_parent` dict)이
      `parent_event_id` 키에 의존했던 것을, wire 평탄화 후에도 동작하도록 단순화.
    """

    def __init__(self):
        self._nodes: dict[int, SlackNode] = {}
        self._tool_use_index: dict[str, int] = {}
        self._active_text_event_id: Optional[int] = None
        self._input_requests: dict[str, InputRequestNode] = {}  # request_id -> InputRequestNode

    def add_thinking(
        self,
        event_id: int,
        msg_ts: str,
    ) -> SlackNode:
        """thinking 이벤트에 대응하는 노드 등록"""
        node = SlackNode(
            event_id=event_id,
            node_type="thinking",
            msg_ts=msg_ts,
        )
        self._nodes[event_id] = node
        return node

    def add_text(
        self,
        event_id: int,
        msg_ts: str,
    ) -> SlackNode:
        """text 노드 등록.

        활성 슬롯을 새 event_id로 갱신. 이전 활성 노드가 있으면 슬롯에서 *덮어쓴다*
        (text_end 누락 fail-safe — 이전 dict 모델에서 같은 키로 덮어쓰던 동작과 등가).
        """
        node = SlackNode(
            event_id=event_id,
            node_type="text",
            msg_ts=msg_ts,
        )
        self._nodes[event_id] = node
        self._active_text_event_id = event_id
        return node

    def add_tool(
        self,
        event_id: int,
        msg_ts: str,
        tool_use_id: str,
        tool_name: Optional[str] = None,
    ) -> SlackNode:
        """tool_start 이벤트에 대응하는 노드 등록"""
        node = SlackNode(
            event_id=event_id,
            node_type="tool",
            msg_ts=msg_ts,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
        )
        self._nodes[event_id] = node
        if tool_use_id:
            self._tool_use_index[tool_use_id] = event_id
        return node

    def find_text_node(self) -> Optional[SlackNode]:
        """현재 활성 text 노드 반환 (없으면 None).

        text_start에서 등록한 text 노드를 text_delta/text_end가 찾는다.
        text_end 처리 후 슬롯이 비워지므로 text 블록의 lifecycle을 정확히 따른다.
        """
        if self._active_text_event_id is None:
            return None
        return self._nodes.get(self._active_text_event_id)

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
        """완료된 노드를 룩업 인덱스에서 제거 (노드 자체는 _nodes에 유지).

        node_type == "text" 가드: 활성 텍스트 슬롯은 *text 노드만* 사용한다.
        thinking/tool 노드의 event_id가 우연히 활성 슬롯 값과 같더라도(운영 환경에서
        event_id는 SSE 스트림 내 단조증가라 충돌 0%이지만), invariant를 코드로 명시하여
        후임이 추측하지 않도록 한다.
        """
        if node.node_type == "text" and self._active_text_event_id == node.event_id:
            self._active_text_event_id = None
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
