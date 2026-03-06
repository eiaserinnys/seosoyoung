# presentation/node_map.py

> 경로: `seosoyoung/slackbot/presentation/node_map.py`

## 개요

이벤트 노드 <-> 슬랙 메시지 매핑

소울스트림의 세분화 이벤트(thinking, tool_start 등)에 대응하는
슬랙 스레드 메시지 ts를 추적하는 자료구조입니다.

## 클래스

### `SlackNode`
- 위치: 줄 12
- 설명: 이벤트 노드에 대응하는 슬랙 메시지

### `SlackNodeMap`
- 위치: 줄 24
- 설명: 이벤트 노드 <-> 슬랙 메시지 ts 매핑

대시보드의 ProcessingContext를 슬랙에 맞게 번안.
- _nodes: event_id -> SlackNode
- _tool_use_index: tool_use_id -> event_id (tool_result 매칭용)
- _last_thinking_by_parent: parent_event_id -> event_id (text가 병합할 대상)

#### 메서드

- `__init__(self)` (줄 33): 
- `add_thinking(self, event_id, msg_ts, parent_event_id)` (줄 38): thinking 이벤트에 대응하는 노드 등록
- `add_text(self, event_id, msg_ts, parent_event_id)` (줄 55): 독립 text 노드 등록 (thinking 없이 text_start가 도착한 경우, S6)
- `add_tool(self, event_id, msg_ts, tool_use_id, parent_event_id, tool_name)` (줄 76): tool_start 이벤트에 대응하는 노드 등록
- `find_thinking_for_text(self, parent_event_id)` (줄 98): text 이벤트가 병합할 대상 노드 검색
- `find_tool_by_use_id(self, tool_use_id)` (줄 111): tool_use_id로 tool 노드 검색
- `mark_completed(self, event_id)` (줄 121): 노드를 완료 상태로 마킹
- `clear_completed(self)` (줄 128): 완료된 노드를 정리. 정리된 노드 수를 반환.
