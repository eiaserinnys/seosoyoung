"""Dialogue search module using Whoosh."""

from .schema import dialogue_schema
from .indexer import DialogueIndexer, build_index, get_default_paths
from .searcher import DialogueSearcher, get_default_index_path

__all__ = [
    "dialogue_schema",
    "DialogueIndexer",
    "DialogueSearcher",
    "build_index",
    "get_default_paths",
    "get_default_index_path",
]
