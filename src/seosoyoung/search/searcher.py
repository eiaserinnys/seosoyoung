"""Whoosh searcher for dialogue data."""

import json
import sys
from pathlib import Path
from typing import Optional

from whoosh.index import open_dir, exists_in
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.query import Term, And, Every, Or, FuzzyTerm
from whoosh.highlight import Highlighter, HtmlFormatter, ContextFragmenter


class DialogueSearcher:
    """대사 검색 API."""

    def __init__(self, index_path: str | Path):
        """
        Args:
            index_path: 인덱스 경로
        """
        self.index_path = Path(index_path)

        if not exists_in(str(self.index_path)):
            raise FileNotFoundError(
                f"Index not found at {self.index_path}. "
                "Run indexer first to build the index."
            )

        self.ix = open_dir(str(self.index_path))

    def search(
        self,
        query_text: Optional[str] = None,
        speaker: Optional[str] = None,
        label: Optional[str] = None,
        revision: Optional[str] = None,
        act: Optional[str] = None,
        trigger: Optional[str] = None,
        fuzzy: bool = False,
        highlight: bool = False,
        limit: int = 20
    ) -> list[dict]:
        """대사 검색.

        Args:
            query_text: 검색어 (한글/영어)
            speaker: 화자 코드 필터 (fx, ar, kl 등)
            label: 레이블 필터
            revision: 리비전 필터 (_rev1, _rev2). None이면 rev2 우선, 없으면 rev1 fallback
            act: 액트 필터 (act0, act1, ...)
            trigger: 트리거 필터 (bk_idle, bk_wave, ...)
            fuzzy: 퍼지 검색 활성화 (오타 허용)
            highlight: 하이라이팅 활성화
            limit: 최대 결과 수

        Returns:
            검색 결과 리스트
        """
        with self.ix.searcher() as searcher:
            queries = []

            if query_text:
                if fuzzy:
                    # 퍼지 검색: 텍스트 필드에 FuzzyTerm 사용
                    # 각 단어에 대해 퍼지 매칭
                    fuzzy_queries = []
                    for word in query_text.split():
                        fuzzy_queries.append(
                            Or([
                                FuzzyTerm("text_kr", word, maxdist=1),
                                FuzzyTerm("text_en", word, maxdist=1)
                            ])
                        )
                    if fuzzy_queries:
                        queries.append(And(fuzzy_queries) if len(fuzzy_queries) > 1 else fuzzy_queries[0])
                else:
                    # 일반 검색: 한글/영어 동시 검색
                    mparser = MultifieldParser(
                        ["text_kr", "text_en"],
                        self.ix.schema
                    )
                    queries.append(mparser.parse(query_text))

            if speaker:
                queries.append(Term("speaker", speaker.lower()))

            if label:
                queries.append(Term("labels", label.lower()))

            # revision 처리: 명시되면 해당 revision만, 아니면 rev2 우선 + fallback
            use_revision_fallback = revision is None

            if revision:
                queries.append(Term("revision", revision.lower()))

            if act:
                queries.append(Term("acts", act.lower()))

            if trigger:
                queries.append(Term("trigger", trigger.lower()))

            if not queries:
                # 검색 조건 없으면 전체 조회
                final_query = Every()
            elif len(queries) == 1:
                final_query = queries[0]
            else:
                final_query = And(queries)

            # revision fallback 로직: rev2 먼저 시도, 결과 없으면 rev1
            if use_revision_fallback:
                # rev2 우선 검색
                rev2_query = And([final_query, Term("revision", "_rev2")]) if queries else Term("revision", "_rev2")
                results = searcher.search(rev2_query, limit=limit)

                if len(results) == 0:
                    # rev2에 결과 없으면 rev1 검색
                    rev1_query = And([final_query, Term("revision", "_rev1")]) if queries else Term("revision", "_rev1")
                    results = searcher.search(rev1_query, limit=limit)
            else:
                results = searcher.search(final_query, limit=limit)

            # 하이라이터 설정
            highlighter = None
            if highlight and query_text:
                highlighter = Highlighter(
                    formatter=HtmlFormatter(tagname="mark"),
                    fragmenter=ContextFragmenter(maxchars=200, surround=50)
                )

            output = []
            for r in results:
                item = {
                    "dlgId": r["dlgId"],
                    "speaker": r["speaker"],
                    "text_kr": r["text_kr"],
                    "text_en": r["text_en"],
                    "hash": r.get("hash", ""),
                    "source_file": r.get("source_file", ""),
                    "labels": r.get("labels", ""),
                    "revision": r.get("revision", ""),
                    "acts": r.get("acts", ""),
                    "trigger": r.get("trigger", ""),
                    "score": r.score
                }

                # 하이라이팅 적용
                if highlighter and query_text:
                    text_kr_hl = r.highlights("text_kr", top=1)
                    text_en_hl = r.highlights("text_en", top=1)
                    if text_kr_hl:
                        item["text_kr_highlighted"] = text_kr_hl
                    if text_en_hl:
                        item["text_en_highlighted"] = text_en_hl

                output.append(item)

            return output

    def search_by_dlgid(self, dlgId: str) -> Optional[dict]:
        """dlgId로 정확히 검색.

        Args:
            dlgId: 대사 ID (예: fx-008V57I1)

        Returns:
            대사 정보 또는 None
        """
        with self.ix.searcher() as searcher:
            results = searcher.search(Term("dlgId", dlgId), limit=1)
            if results:
                r = results[0]
                return {
                    "dlgId": r["dlgId"],
                    "speaker": r["speaker"],
                    "text_kr": r["text_kr"],
                    "text_en": r["text_en"],
                    "hash": r.get("hash", ""),
                    "source_file": r.get("source_file", ""),
                    "labels": r.get("labels", ""),
                    "revision": r.get("revision", ""),
                    "acts": r.get("acts", ""),
                    "trigger": r.get("trigger", "")
                }
            return None

    def get_stats(self) -> dict:
        """인덱스 통계 조회."""
        with self.ix.searcher() as searcher:
            return {
                "total_docs": searcher.doc_count(),
                "index_path": str(self.index_path)
            }


def get_default_index_path() -> Path:
    """기본 인덱스 경로 반환."""
    return Path.cwd() / "internal" / "index" / "dialogues"


def format_results(results: list[dict], format_type: str = "json") -> str:
    """결과 포맷팅.

    Args:
        results: 검색 결과
        format_type: json 또는 brief
    """
    if format_type == "json":
        return json.dumps(results, ensure_ascii=False, indent=2)
    elif format_type == "brief":
        lines = []
        for r in results:
            speaker = r["speaker"].upper()
            text_kr = r["text_kr"].strip().replace("\n", " ")[:50]
            lines.append(f"[{speaker}] {r['dlgId']}: {text_kr}...")
        return "\n".join(lines)
    else:
        return json.dumps(results, ensure_ascii=False, indent=2)


def main():
    """CLI 진입점."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Search dialogues using Whoosh index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 한글 텍스트 검색
  python -m seosoyoung.search.searcher -q "악마 사냥"

  # 화자 + 텍스트 검색
  python -m seosoyoung.search.searcher -q "천사" -s fx --limit 10

  # 레이블로 검색
  python -m seosoyoung.search.searcher --label prologue_a_1

  # 액트로 필터링
  python -m seosoyoung.search.searcher -q "루미" --act act1

  # 트리거로 검색
  python -m seosoyoung.search.searcher --trigger bk_idle --limit 50

  # 리비전으로 필터링
  python -m seosoyoung.search.searcher -q "천사" --revision _rev2

  # 퍼지 검색 (오타 허용)
  python -m seosoyoung.search.searcher -q "악아" --fuzzy

  # 하이라이팅 출력
  python -m seosoyoung.search.searcher -q "악마" --highlight
"""
    )
    parser.add_argument("--index-path", help="Index path")

    # 기본 검색 옵션
    parser.add_argument("-q", "--query", help="Search query (Korean/English)")
    parser.add_argument("-s", "--speaker", help="Speaker code filter (fx, ar, kl, etc.)")
    parser.add_argument("--id", help="Search by exact dlgId")

    # 확장 필터 옵션
    parser.add_argument("--label", help="Label filter (dialogue label name)")
    parser.add_argument("--revision", help="Revision filter (_rev1, _rev2)")
    parser.add_argument("--act", help="Act filter (act0, act1, act2, ...)")
    parser.add_argument("--trigger", help="Trigger filter (bk_idle, bk_wave, ...)")

    # 검색 모드 옵션
    parser.add_argument("--fuzzy", action="store_true", help="Enable fuzzy search (typo tolerance)")
    parser.add_argument("--highlight", action="store_true", help="Enable search term highlighting")

    # 출력 옵션
    parser.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    parser.add_argument("--format", choices=["json", "brief"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--stats", action="store_true", help="Show index statistics")

    args = parser.parse_args()

    # 인덱스 경로 결정
    index_path = Path(args.index_path) if args.index_path else get_default_index_path()

    try:
        searcher = DialogueSearcher(index_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 통계 조회
    if args.stats:
        stats = searcher.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    # dlgId로 검색
    if args.id:
        result = searcher.search_by_dlgid(args.id)
        if result:
            print(format_results([result], args.format))
        else:
            print(f"Not found: {args.id}", file=sys.stderr)
            sys.exit(1)
        return

    # 검색 조건 확인 (최소 하나의 필터 필요)
    has_filter = any([
        args.query, args.speaker, args.label,
        args.revision, args.act, args.trigger
    ])
    if not has_filter:
        parser.print_help()
        sys.exit(1)

    results = searcher.search(
        query_text=args.query,
        speaker=args.speaker,
        label=args.label,
        revision=args.revision,
        act=args.act,
        trigger=args.trigger,
        fuzzy=args.fuzzy,
        highlight=args.highlight,
        limit=args.limit
    )

    print(format_results(results, args.format))


if __name__ == "__main__":
    main()
