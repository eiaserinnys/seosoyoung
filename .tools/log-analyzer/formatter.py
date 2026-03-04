"""출력 포맷팅 — CLI 결과를 읽기 좋은 텍스트로 변환한다."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scanner import LogFile
    from parsers import LogEntry
    from segments import SessionSegment


def _human_size(size_bytes: int) -> str:
    """바이트를 사람이 읽기 좋은 단위로 변환한다."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def format_locate(files: list[LogFile]) -> str:
    """locate 명령의 결과를 포맷한다."""
    if not files:
        return "로그 파일을 찾지 못했습니다."

    lines: list[str] = []
    lines.append(f"{'파일명':<50} {'컴포넌트':<25} {'런타임':<14} {'크기':>10}  {'수정시각'}")
    lines.append("-" * 120)

    total_size = 0
    for f in files:
        name = f.path.name
        if len(name) > 48:
            name = name[:45] + "..."
        mod = f.last_modified.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{name:<50} {f.component:<25} {f.runtime:<14} {_human_size(f.size_bytes):>10}  {mod}"
        )
        total_size += f.size_bytes

    lines.append("-" * 120)
    lines.append(f"총 {len(files)}개 파일, {_human_size(total_size)}")
    return "\n".join(lines)


def format_entries(entries: list[LogEntry], *, show_component: bool = True) -> str:
    """로그 엔트리 목록을 포맷한다."""
    if not entries:
        return "해당 조건에 맞는 로그가 없습니다."

    lines: list[str] = []
    for e in entries:
        ts_str = e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "                   "
        if show_component:
            lines.append(f"[{ts_str}] [{e.level:<8}] [{e.component}] {e.message}")
        else:
            lines.append(f"[{ts_str}] [{e.level:<8}] {e.message}")

    lines.append(f"\n총 {len(entries)}건")
    return "\n".join(lines)


def format_segments(segments: list[SessionSegment]) -> str:
    """세션 세그먼트 목록을 포맷한다."""
    if not segments:
        return "세션 경계를 찾지 못했습니다."

    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        start = seg.start_time.strftime("%Y-%m-%d %H:%M:%S")
        end = seg.end_time.strftime("%Y-%m-%d %H:%M:%S") if seg.end_time else "(진행 중)"
        duration = ""
        if seg.end_time:
            delta = seg.end_time - seg.start_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                duration = f" ({hours}h {minutes}m)"
            elif minutes > 0:
                duration = f" ({minutes}m {seconds}s)"
            else:
                duration = f" ({seconds}s)"

        exit_info = f", exit={seg.exit_code}" if seg.exit_code is not None else ""
        lines.append(f"  #{i}: {start} ~ {end}{duration}")
        lines.append(f"       시작: {seg.start_marker}")
        if seg.end_marker:
            lines.append(f"       종료: {seg.end_marker}{exit_info}")

    lines.insert(0, f"총 {len(segments)}개 세션:")
    return "\n".join(lines)
