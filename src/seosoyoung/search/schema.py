"""Whoosh schema definitions for search indices."""

from whoosh.fields import Schema, TEXT, ID, KEYWORD, STORED
from whoosh.analysis import NgramTokenizer, LowercaseFilter, StandardAnalyzer


# 한글용 분석기 (2-4 ngram)
# 한글은 형태소 분석 없이 N-gram 방식으로 처리
korean_analyzer = NgramTokenizer(minsize=2, maxsize=4) | LowercaseFilter()

# 영어용 분석기 (표준)
english_analyzer = StandardAnalyzer()

# 대사 인덱스 스키마
dialogue_schema = Schema(
    dlgId=ID(stored=True, unique=True),
    speaker=KEYWORD(stored=True, scorable=True),
    text_kr=TEXT(stored=True, analyzer=korean_analyzer),
    text_en=TEXT(stored=True, analyzer=english_analyzer),
    hash=STORED(),
    source_file=STORED(),
    labels=KEYWORD(stored=True, commas=True, scorable=True),
    revision=KEYWORD(stored=True, scorable=True),
    acts=KEYWORD(stored=True, commas=True, scorable=True),
    trigger=KEYWORD(stored=True, scorable=True),
)

# 로어 인덱스 스키마
lore_schema = Schema(
    # 청크 ID: char:fx:basic_info, glossary:main_characters:fenrix 등
    chunk_id=ID(stored=True, unique=True),
    # 소스 타입: character, glossary, place, synopsis
    source_type=KEYWORD(stored=True, scorable=True),
    # 소스 ID: fx, sanctuary, overview 등
    source_id=KEYWORD(stored=True, scorable=True),
    # 섹션명: basic_info, background 등
    section=KEYWORD(stored=True, scorable=True),
    # 이름 (검색 보조)
    name_kr=TEXT(stored=True, analyzer=korean_analyzer),
    name_en=TEXT(stored=True, analyzer=english_analyzer),
    # 본문 텍스트
    text_kr=TEXT(stored=True, analyzer=korean_analyzer),
    text_en=TEXT(stored=True, analyzer=english_analyzer),
    # 원본 파일 경로
    source_file=STORED(),
)
