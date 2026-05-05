"""Knowledge collaborators used by ksearch.kbase compatibility API."""

from ksearch.knowledge.chunking import chunk_text
from ksearch.knowledge.service import KnowledgeService, build_knowledge_service
from ksearch.knowledge.vector_store import KnowledgeVectorStore

__all__ = [
    "chunk_text",
    "KnowledgeService",
    "KnowledgeVectorStore",
    "build_knowledge_service",
]
