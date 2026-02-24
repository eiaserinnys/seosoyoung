"""트렐로 카드 포맷팅 유틸리티

체크리스트, 코멘트를 프롬프트용 문자열로 변환하는 순수 함수들을 제공합니다.
"""


def format_checklists(checklists: list[dict]) -> str:
    """체크리스트를 프롬프트용 문자열로 포맷

    Args:
        checklists: Trello API에서 반환된 체크리스트 목록

    Returns:
        마크다운 형식의 체크리스트 문자열
    """
    if not checklists:
        return "(체크리스트 없음)"

    lines = []
    for cl in checklists:
        lines.append(f"### {cl['name']}")
        for item in cl.get("items", []):
            mark = "x" if item["state"] == "complete" else " "
            lines.append(f"- [{mark}] {item['name']}")
    return "\n".join(lines)


def format_comments(comments: list[dict]) -> str:
    """코멘트를 프롬프트용 문자열로 포맷

    Args:
        comments: Trello API에서 반환된 코멘트 목록

    Returns:
        마크다운 형식의 코멘트 문자열
    """
    if not comments:
        return "(코멘트 없음)"

    lines = []
    for c in comments:
        # 날짜에서 분까지 추출 (2026-01-27T05:10:41.387Z -> 2026-01-27 05:10)
        date_str = c.get("date", "")[:16].replace("T", " ") if c.get("date") else ""
        author = c.get("author", "Unknown")
        text = c.get("text", "").strip()
        # 첫 3줄만 미리보기
        preview = "\n".join(text.split("\n")[:3])
        if len(text.split("\n")) > 3:
            preview += "\n..."
        lines.append(f"**[{date_str}] {author}**\n{preview}")
    return "\n\n".join(lines)
