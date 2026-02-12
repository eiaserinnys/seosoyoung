"""슬랙 리액션 관리

트렐로 모드에서 메시지에 이모지 리액션을 추가/제거하는 기능을 제공합니다.
"""

import logging

from seosoyoung.config import Config

logger = logging.getLogger(__name__)


# 트렐로 모드 이모지 리액션 매핑
TRELLO_REACTIONS = {
    "planning": Config.EMOJI_PLANNING,
    "executing": Config.EMOJI_EXECUTING,
    "success": Config.EMOJI_SUCCESS,
    "error": Config.EMOJI_ERROR,
}

# 인터벤션 이모지
INTERVENTION_EMOJI = Config.EMOJI_INTERVENTION_WAITING
INTERVENTION_ACCEPTED_EMOJI = Config.EMOJI_INTERVENTION_ACCEPTED


def add_reaction(client, channel: str, ts: str, emoji: str) -> bool:
    """슬랙 메시지에 이모지 리액션 추가

    Args:
        client: Slack client
        channel: 채널 ID
        ts: 메시지 타임스탬프
        emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

    Returns:
        성공 여부
    """
    try:
        client.reactions_add(channel=channel, timestamp=ts, name=emoji)
        return True
    except Exception as e:
        logger.debug(f"이모지 리액션 추가 실패 ({emoji}): {e}")
        return False


def remove_reaction(client, channel: str, ts: str, emoji: str) -> bool:
    """슬랙 메시지에서 이모지 리액션 제거

    Args:
        client: Slack client
        channel: 채널 ID
        ts: 메시지 타임스탬프
        emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

    Returns:
        성공 여부
    """
    try:
        client.reactions_remove(channel=channel, timestamp=ts, name=emoji)
        return True
    except Exception as e:
        logger.debug(f"이모지 리액션 제거 실패 ({emoji}): {e}")
        return False
