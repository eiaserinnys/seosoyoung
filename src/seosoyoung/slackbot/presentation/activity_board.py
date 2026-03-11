"""ActivityBoard: 플레이스홀더 B 항목 관리

클린 모드에서 thinking/tool/compact 이벤트를 단일 슬랙 메시지의
갱신으로 처리하여 알림 과다 문제를 해결합니다.
"""

from dataclasses import dataclass
import asyncio
import logging

from seosoyoung.slackbot.slack.formatting import update_message

logger = logging.getLogger(__name__)

BOARD_EMPTY_TEXT = "> ..."  # 항목이 없을 때 표시


@dataclass
class ActivityItem:
    item_id: str
    content: str  # 이미 포맷된 슬랙 mrkdwn 텍스트


class ActivityBoard:
    """플레이스홀더 B의 항목 리스트를 관리하고 슬랙 메시지를 갱신"""

    def __init__(self, client, channel: str, msg_ts: str):
        self._client = client
        self._channel = channel
        self._msg_ts = msg_ts
        self._items: list[ActivityItem] = []
        self._removal_tasks: dict[str, asyncio.Task] = {}

    @property
    def msg_ts(self) -> str:
        return self._msg_ts

    def add(self, item_id: str, content: str) -> None:
        """항목 추가 후 B 메시지 갱신"""
        self._items.append(ActivityItem(item_id=item_id, content=content))
        self._sync()

    def update(self, item_id: str, content: str) -> None:
        """항목 내용 교체 후 B 메시지 갱신. item_id가 없으면 sync를 건너뜀."""
        for item in self._items:
            if item.item_id == item_id:
                item.content = content
                self._sync()
                return
        logger.debug(f"ActivityBoard.update: item_id={item_id} not found, skipping sync")

    def remove(self, item_id: str) -> None:
        """항목 제거 후 B 메시지 갱신"""
        self._items = [i for i in self._items if i.item_id != item_id]
        self._removal_tasks.pop(item_id, None)
        self._sync()

    def schedule_remove(self, item_id: str, delay: float) -> None:
        """지정 시간 후 항목 제거를 예약"""
        async def _delayed_remove():
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                self.remove(item_id)
            except asyncio.CancelledError:
                pass  # 정상적인 취소

        # 기존 예약이 있으면 취소
        old_task = self._removal_tasks.pop(item_id, None)
        if old_task and not old_task.done():
            old_task.cancel()
        task = asyncio.create_task(_delayed_remove())
        self._removal_tasks[item_id] = task

    def cancel_all_pending(self) -> None:
        """모든 대기 중인 제거 태스크를 취소 (cleanup 시 호출)"""
        for task in self._removal_tasks.values():
            if not task.done():
                task.cancel()
        self._removal_tasks.clear()

    def _render(self) -> str:
        """모든 항목을 하나의 텍스트로 합성"""
        if not self._items:
            return BOARD_EMPTY_TEXT
        return "\n\n".join(item.content for item in self._items)

    def _sync(self) -> None:
        """B 메시지를 현재 상태로 갱신"""
        text = self._render()
        try:
            update_message(self._client, self._channel, self._msg_ts, text)
        except Exception as e:
            logger.warning(f"ActivityBoard 갱신 실패: {e}")
