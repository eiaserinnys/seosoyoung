"""Search module — dialogue and lore indexing/searching."""

from .schema import dialogue_schema, lore_schema
from .searcher import DialogueSearcher, get_default_index_path
from .indexer import DialogueIndexer, DialogueReferenceMap, DialogueMetadata

__all__ = [
    "dialogue_schema",
    "lore_schema",
    "DialogueSearcher",
    "get_default_index_path",
    "DialogueIndexer",
    "DialogueReferenceMap",
    "DialogueMetadata",
]
