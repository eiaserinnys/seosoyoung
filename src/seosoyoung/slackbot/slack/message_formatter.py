"""슬랙 메시지 → 프롬프트 주입 포맷터

모든 슬랙 메시지를 Claude 프롬프트에 주입할 때 사용하는 통일된 포맷터입니다.
채널:ts 메타데이터, Block Kit 리치 텍스트, 첨부 파일, unfurl, 리액션 등을 포함합니다.
"""


def format_slack_message(
    msg: dict,
    channel: str = "",
    include_meta: bool = True,
) -> str:
    """슬랙 메시지를 프롬프트 주입용 텍스트로 포맷합니다.

    Args:
        msg: 슬랙 메시지 dict (conversations.history 등에서 반환되는 형태)
        channel: 슬랙 채널 ID
        include_meta: True면 [channel:ts] 메타데이터 프리픽스 부착

    Returns:
        포맷된 문자열
    """
    user = msg.get("user", "unknown")
    text = msg.get("text", "")
    ts = msg.get("ts", "")

    # 메타데이터 프리픽스
    prefix = ""
    if include_meta and ts:
        if channel:
            prefix = f"[{channel}:{ts}] "
        else:
            prefix = f"[ts:{ts}] "

    line = f"{prefix}<{user}>: {text}"

    # Block Kit 리치 텍스트
    line += _format_blocks(msg.get("blocks", []))

    # 첨부 파일
    for f in msg.get("files", []):
        name = f.get("name", "file")
        mimetype = f.get("mimetype", "")
        size = f.get("size", 0)
        line += f"\n  [첨부: {name} ({mimetype}, {size}B)]"

    # Attachments (unfurl, 봇 카드)
    for att in msg.get("attachments", []):
        title = att.get("title", att.get("fallback", ""))
        att_text = att.get("text", "")
        if title:
            line += f"\n  [링크: {title}]"
        for field in att.get("fields", []):
            ftitle = field.get("title", "")
            fvalue = field.get("value", "")
            line += f"\n    {ftitle}: {fvalue}"
        if att_text and not title:
            line += f"\n  [봇 메시지: {att_text[:200]}]"

    # 리액션
    reactions = msg.get("reactions", [])
    if reactions:
        rxn_str = ", ".join(
            f":{r['name']}: x{r['count']}" for r in reactions
        )
        line += f"\n  [리액션: {rxn_str}]"

    # linked_message_ts (hybrid 세션용)
    linked = msg.get("linked_message_ts", "")
    if linked:
        line += f" [linked:{linked}]"

    # 봇 발신 여부
    if msg.get("bot_id"):
        bot_name = msg.get("bot_profile", {}).get("name", msg.get("bot_id"))
        line = line.replace(f"<{user}>:", f"<bot:{bot_name}>:", 1)

    return line


def _format_blocks(blocks: list[dict]) -> str:
    """Block Kit rich_text 요소를 텍스트로 변환"""
    result = ""
    for block in blocks:
        if block.get("type") != "rich_text":
            continue
        for elem in block.get("elements", []):
            etype = elem.get("type", "")
            if etype == "rich_text_preformatted":
                pre_text = "".join(
                    e.get("text", "") for e in elem.get("elements", [])
                )
                result += f"\n```\n{pre_text}\n```"
            elif etype == "rich_text_list":
                style = elem.get("style", "bullet")
                for i, item in enumerate(elem.get("elements", []), 1):
                    item_text = "".join(
                        e.get("text", "") for e in item.get("elements", [])
                    )
                    marker = f"{i}." if style == "ordered" else "-"
                    result += f"\n  {marker} {item_text}"
            elif etype == "rich_text_quote":
                quote_text = "".join(
                    e.get("text", "") for e in elem.get("elements", [])
                )
                result += f"\n> {quote_text}"
    return result
