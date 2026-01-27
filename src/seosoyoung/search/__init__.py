"""Dialogue search module using Whoosh."""

from .schema import dialogue_schema
from .searcher import DialogueSearcher, get_default_index_path

__all__ = [
    "dialogue_schema",
    "DialogueSearcher",
    "get_default_index_path",
]
