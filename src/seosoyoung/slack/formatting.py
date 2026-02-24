"""슬랙 메시지 포맷팅 헬퍼

chat_update(channel, ts, text, blocks=[section]) 패턴을 캡슐화합니다.
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

    Args:
        client: Slack WebClient
        channel: 채널 ID
        ts: 메시지 타임스탬프
        text: 메시지 텍스트
        blocks: 커스텀 blocks (생략 시 text로 자동 생성)
    """
    if blocks is None:
        blocks = build_section_blocks(text)
    client.chat_update(
        channel=channel,
        ts=ts,
        text=text,
        blocks=blocks,
    )
