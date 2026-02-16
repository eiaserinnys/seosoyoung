"""Search module — dialogue and lore indexing/searching."""

from .schema import dialogue_schema, lore_schema
from .searcher import DialogueSearcher, get_default_index_path
from .indexer import DialogueIndexer, DialogueReferenceMap, DialogueMetadata
from .embedding_index import (
    EmbeddingIndexBuilder,
    cosine_similarity_search,
    load_embedding_index,
)
from .build import build_all, build_whoosh, build_embeddings

__all__ = [
    "dialogue_schema",
    "lore_schema",
    "DialogueSearcher",
    "get_default_index_path",
    "DialogueIndexer",
    "DialogueReferenceMap",
    "DialogueMetadata",
    "EmbeddingIndexBuilder",
    "cosine_similarity_search",
    "load_embedding_index",
    "build_all",
    "build_whoosh",
    "build_embeddings",
]
