"""Whoosh schema definition for dialogue search."""

from whoosh.fields import Schema, TEXT, ID, KEYWORD, STORED
from whoosh.analysis import NgramTokenizer, LowercaseFilter, StandardAnalyzer


# 한글용 분석기 (2-4 ngram)
# 한글은 형태소 분석 없이 N-gram 방식으로 처리
korean_analyzer = NgramTokenizer(minsize=2, maxsize=4) | LowercaseFilter()

# 영어용 분석기 (표준)
english_analyzer = StandardAnalyzer()

# 대사 인덱스 스키마 v2 (확장 필드 포함)
dialogue_schema = Schema(
    # 기본 식별자
    dlgId=ID(stored=True, unique=True),

    # 화자
    speaker=KEYWORD(stored=True, scorable=True),

    # 대사 텍스트 (검색 대상)
    text_kr=TEXT(stored=True, analyzer=korean_analyzer),
    text_en=TEXT(stored=True, analyzer=english_analyzer),

    # 메타데이터
    hash=STORED(),
    source_file=STORED(),

    # 확장 필드 - 대화 구조에서 역참조
    labels=KEYWORD(stored=True, commas=True, scorable=True),  # 레이블 목록 (콤마 구분)
    revision=KEYWORD(stored=True, scorable=True),              # _rev1 / _rev2
    acts=KEYWORD(stored=True, commas=True, scorable=True),     # act0, act1, ... (콤마 구분)
    trigger=KEYWORD(stored=True, scorable=True)                # 트리거 이름 (bk_idle, bk_wave 등)
)
