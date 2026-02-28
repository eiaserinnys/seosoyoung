"""rescue-bot용 슬랙 메시지 포맷팅 헬퍼

slackbot.slack.formatting에서 이관된 경량 유틸리티.
"""

from typing import Optional


def build_section_blocks(text: str) -> list[dict]:
    """mrkdwn section block 리스트 생성"""
    return [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": text}
    }]


def update_message(
    client,
    channel: str,
    ts: str,
    text: str,
    *,
    blocks: Optional[list[dict]] = None,
) -> None:
    """슬랙 메시지를 업데이트합니다.

    blocks를 생략하면 text를 mrkdwn section block으로 자동 감싸서 전달합니다.
    """
    if blocks is None:
        blocks = build_section_blocks(text)
    client.chat_update(
        channel=channel,
        ts=ts,
        text=text,
        blocks=blocks,
    )
