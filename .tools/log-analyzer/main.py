"""로그 분석 CLI — seosoyoung/soulstream 런타임 로그를 체계적으로 탐색한다.

사용법:
    python .tools/log-analyzer/main.py locate [--component COMP] [--runtime RT]
    python .tools/log-analyzer/main.py segments --component COMP [--last N]
    python .tools/log-analyzer/main.py search --start DT --end DT [--level LVL] [--pattern PAT] [--component COMP] [--tail N]
    python .tools/log-analyzer/main.py search --last-hours N [--level LVL] [--component COMP]
    python .tools/log-analyzer/main.py context THREAD_TS [--window MIN] [--component COMP]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta

from context import search_context
from formatter import format_entries, format_locate, format_segments
from scanner import scan_logs
from searcher import search_file
from segments import find_segments


def cmd_locate(args: argparse.Namespace) -> None:
    """전체 로그 파일 목록/크기/수정시각을 표시한다."""
    files = scan_logs(component=args.component, runtime=args.runtime)
    print(format_locate(files))


def cmd_segments(args: argparse.Namespace) -> None:
    """세션 시작/종료 경계를 탐색한다."""
    # 해당 컴포넌트의 로그 파일 찾기
    files = scan_logs(component=args.component)
    if not files:
        print(f"'{args.component}' 컴포넌트의 로그 파일을 찾지 못했습니다.")
        return

    all_segments = []
    for lf in files:
        segs = find_segments(lf.path, lf.component, last=None)
        all_segments.extend(segs)

    # 시간순 정렬
    all_segments.sort(key=lambda s: s.start_time)

    if args.last:
        all_segments = all_segments[-args.last:]

    print(format_segments(all_segments))


def cmd_search(args: argparse.Namespace) -> None:
    """시간 범위/레벨/패턴 기반으로 로그를 검색한다."""
    # 시간 범위 결정
    start_time = None
    end_time = None

    if args.last_hours:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=args.last_hours)
    else:
        if args.start:
            start_time = _parse_datetime(args.start)
        if args.end:
            end_time = _parse_datetime(args.end)

    if not start_time and not end_time:
        print("--start/--end 또는 --last-hours를 지정해주세요.")
        sys.exit(1)

    compiled_pattern = re.compile(args.pattern) if args.pattern else None

    files = scan_logs(component=args.component, runtime=args.runtime)
    if not files:
        print("해당 조건의 로그 파일을 찾지 못했습니다.")
        return

    all_entries = []
    for lf in files:
        # 날짜 힌트가 있으면 범위 밖 파일 스킵
        if lf.date_hint:
            if start_time and lf.date_hint < start_time.date():
                continue
            if end_time and lf.date_hint > end_time.date():
                continue

        if lf.size_bytes == 0:
            continue

        entries = search_file(
            lf.path,
            lf.component,
            start_time=start_time,
            end_time=end_time,
            level=args.level,
            pattern=compiled_pattern,
            tail=args.tail if not args.component else None,  # 파일별 tail은 전체 결합 시 부정확
        )
        all_entries.extend(entries)

    # 시간순 정렬
    all_entries.sort(key=lambda e: (e.timestamp or datetime.min, e.line_number))

    if args.tail:
        all_entries = all_entries[-args.tail:]

    show_component = args.component is None
    print(format_entries(all_entries, show_component=show_component))


def cmd_context(args: argparse.Namespace) -> None:
    """슬랙 thread_ts 기반으로 로그 상관관계를 조회한다."""
    # 입력 검증 (시스템 경계)
    try:
        float(args.thread_ts)
    except ValueError:
        print(f"thread_ts 형식이 올바르지 않습니다: {args.thread_ts}")
        print("예시: 1772584610.882089")
        sys.exit(1)

    result = search_context(
        args.thread_ts,
        window_minutes=args.window,
        component=args.component,
        level=args.level,
        pattern=args.pattern,
    )

    print(f"슬랙 스레드 시각: {result.thread_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(
        f"검색 범위: {result.start_time.strftime('%H:%M:%S')} ~ "
        f"{result.end_time.strftime('%H:%M:%S')} (±{args.window}분)"
    )

    if result.session_file:
        print(f"세션 파일: {result.session_file}")

    print()
    print(format_entries(result.entries))


def _parse_datetime(value: str) -> datetime:
    """다양한 날짜/시간 형식을 파싱한다."""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"날짜 형식을 인식할 수 없습니다: {value}")


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        prog="log-analyzer",
        description="seosoyoung/soulstream 런타임 로그 분석 도구",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # locate
    p_locate = subparsers.add_parser("locate", help="로그 파일 목록 표시")
    p_locate.add_argument("--component", "-c", help="컴포넌트 필터 (부분 매칭)")
    p_locate.add_argument("--runtime", "-r", choices=["seosoyoung", "soulstream"])

    # segments
    p_segments = subparsers.add_parser("segments", help="세션 경계 탐색")
    p_segments.add_argument("--component", "-c", required=True, help="컴포넌트 이름")
    p_segments.add_argument("--last", "-n", type=int, help="최근 N개만 표시")

    # search
    p_search = subparsers.add_parser("search", help="시간/레벨/패턴 기반 검색")
    p_search.add_argument("--start", "-s", help="시작 시각 (YYYY-MM-DD HH:MM:SS)")
    p_search.add_argument("--end", "-e", help="종료 시각")
    p_search.add_argument("--last-hours", type=float, help="최근 N시간 내 검색")
    p_search.add_argument("--level", "-l", help="최소 로그 레벨 (DEBUG/INFO/WARNING/ERROR/CRITICAL)")
    p_search.add_argument("--pattern", "-p", help="메시지 정규식 패턴")
    p_search.add_argument("--component", "-c", help="컴포넌트 필터")
    p_search.add_argument("--runtime", "-r", choices=["seosoyoung", "soulstream"])
    p_search.add_argument("--tail", "-t", type=int, help="마지막 N건만 표시")

    # context
    p_context = subparsers.add_parser("context", help="슬랙 thread_ts 기반 상관관계")
    p_context.add_argument("thread_ts", help="슬랙 thread_ts (예: 1772584610.882089)")
    p_context.add_argument("--window", "-w", type=int, default=5, help="검색 윈도우 (분, 기본 5)")
    p_context.add_argument("--component", "-c", help="컴포넌트 필터")
    p_context.add_argument("--level", "-l", help="최소 로그 레벨")
    p_context.add_argument("--pattern", "-p", help="메시지 정규식 패턴")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "locate": cmd_locate,
        "segments": cmd_segments,
        "search": cmd_search,
        "context": cmd_context,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
