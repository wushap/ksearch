"""kbase management with vector database support.

Supports two modes:
- Chroma (embedded): Default, zero external dependencies
- Qdrant (server): Production-grade, requires Docker service

Usage:
    kbase = KnowledgeBase(mode="chroma")  # Embedded mode
    kbase = KnowledgeBase(mode="qdrant", url="http://localhost:6333")  # Server mode

    # Ingest documents
    kbase.ingest_file("~/docs/note.md", metadata={"source": "logseq"})
    kbase.ingest_directory("~/notes/", glob_pattern="*.md")

    # Search
    results = kbase.search("python async", top_k=5)
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ksearch.config import expand_path
from ksearch.embeddings import simple_hash_embedding
from ksearch.knowledge.service import build_knowledge_service


@dataclass
class KnowledgeBaseEntry:
    """Knowledge base entry."""
    id: str
    content: str
    file_path: str
    title: Optional[str] = None
    source: Optional[str] = None  # logseq, affine, manual, web
    tags: list[str] = None
    created_at: Optional[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class KnowledgeBaseSearchResult:
    """Knowledge base search result."""
    id: str
    content: str
    file_path: str
    title: Optional[str] = None
    source: Optional[str] = None
    score: float = 0.0
    metadata: dict = None


class KnowledgeBase:
    """kbase with vector search support.

    Provides document ingestion, semantic search, and metadata filtering.
    """

    def __init__(
        self,
        mode: str = "chroma",
        persist_dir: str = "~/.ksearch/kbase",
        qdrant_url: Optional[str] = None,
        embedding_model: str = "nomic-embed-text",
        embedding_dimension: int = 768,
        ollama_url: str = "http://localhost:11434",
        reranker=None,
        use_hybrid: bool = True,
        use_rerank: bool = True,
    ):
        """Initialize knowledge base.

        Args:
            mode: "chroma" (embedded) or "qdrant" (server)
            persist_dir: Local directory for Chroma persistence
            qdrant_url: Qdrant server URL (required for qdrant mode)
            embedding_model: Ollama embedding model name
            embedding_dimension: Expected embedding vector size
            ollama_url: Ollama server URL for embeddings
            reranker: Optional ReRanker instance for cross-encoder re-ranking
            use_hybrid: Enable BM25 + vector hybrid retrieval
            use_rerank: Enable cross-encoder re-ranking
        """
        self.mode = mode
        self.persist_dir = expand_path(persist_dir)
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.ollama_url = ollama_url
        self.collection_name = "kbase"
        self.metadata_path = os.path.join(self.persist_dir, "_kbase_metadata.json")
        self.qdrant_url = qdrant_url
        self.reranker = reranker
        self.use_hybrid = use_hybrid
        self.use_rerank = use_rerank

        os.makedirs(self.persist_dir, exist_ok=True)

        if mode == "chroma":
            self._init_chroma()
        elif mode == "qdrant":
            if not qdrant_url:
                qdrant_url = "http://localhost:6333"
            self.qdrant_url = qdrant_url
            self._init_qdrant()
        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'chroma' or 'qdrant'")

        self._validate_or_initialize_metadata()

    def _init_chroma(self):
        """Initialize Chroma embedded mode."""
        self._service, self._vector_store = build_knowledge_service(
            mode="chroma",
            persist_dir=self.persist_dir,
            collection_name=self.collection_name,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            ollama_url=self.ollama_url,
            qdrant_url=None,
            id_generator=self._generate_id,
            entry_cls=KnowledgeBaseEntry,
            result_cls=KnowledgeBaseSearchResult,
            reranker=self.reranker,
            use_hybrid=self.use_hybrid,
            use_rerank=self.use_rerank,
        )
        self._client = self._vector_store.client
        self._collection = self._vector_store.collection

    def _init_qdrant(self):
        """Initialize Qdrant server mode."""
        self._service, self._vector_store = build_knowledge_service(
            mode="qdrant",
            persist_dir=self.persist_dir,
            collection_name=self.collection_name,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            ollama_url=self.ollama_url,
            qdrant_url=self.qdrant_url,
            id_generator=self._generate_id,
            entry_cls=KnowledgeBaseEntry,
            result_cls=KnowledgeBaseSearchResult,
            reranker=self.reranker,
            use_hybrid=self.use_hybrid,
            use_rerank=self.use_rerank,
        )
        self._client = self._vector_store.client

    def _expected_metadata(self) -> dict:
        """Return metadata describing the current kbase embedding configuration."""
        return {
            "mode": self.mode,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
        }

    def _load_metadata(self) -> Optional[dict]:
        """Load persisted kbase metadata when present."""
        if not os.path.exists(self.metadata_path):
            return None

        with open(self.metadata_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_metadata(self) -> None:
        """Persist kbase metadata for future compatibility checks."""
        with open(self.metadata_path, "w", encoding="utf-8") as handle:
            json.dump(self._expected_metadata(), handle, indent=2)

    def _validate_or_initialize_metadata(self) -> None:
        """Ensure the kbase matches the configured embedding settings."""
        metadata = self._load_metadata()
        if metadata is None:
            if self.count() > 0:
                raise ValueError(
                    "kbase metadata is missing for a non-empty knowledge base. "
                    "Reset the kbase before changing embedding settings."
                )
            self._write_metadata()
            return

        stored_mode = metadata.get("mode")
        stored_model = metadata.get("embedding_model")
        stored_dimension = metadata.get("embedding_dimension")

        if stored_mode and stored_mode != self.mode:
            raise ValueError(
                f"kbase mode mismatch: stored '{stored_mode}', requested '{self.mode}'. "
                "Reset the kbase before switching modes."
            )
        if stored_model and stored_model != self.embedding_model:
            raise ValueError(
                f"kbase embedding model mismatch: stored '{stored_model}', requested '{self.embedding_model}'. "
                "Reset the kbase before switching embedding model."
            )
        if stored_dimension and stored_dimension != self.embedding_dimension:
            raise ValueError(
                f"kbase embedding dimension mismatch: stored '{stored_dimension}', requested '{self.embedding_dimension}'. "
                "Reset the kbase before switching embedding dimension."
            )

        self._write_metadata()

    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding vector from Ollama or fallback."""
        return self._service.embed_text(text)

    def _simple_embedding(self, text: str) -> list[float]:
        """Simple embedding fallback when no ML models available.

        Uses word frequency hashing - NOT for production use.
        """
        return simple_hash_embedding(text, self.embedding_dimension)

    def _generate_id(self, file_path: str, content: str, chunk_index: int) -> str:
        """Generate unique ID for entry."""
        hash_input = f"{file_path}:{chunk_index}:{content[:100]}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def ingest_file(
        self,
        file_path: str,
        metadata: dict = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> int:
        """Ingest a single file into knowledge base.

        Args:
            file_path: Path to file
            metadata: Additional metadata (source, tags, etc.)
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks

        Returns:
            Number of chunks ingested
        """
        return self._service.ingest_file(
            file_path=file_path,
            metadata=metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunker=self._chunk_text,
            id_generator=self._generate_id,
            entry_storer=self._store_entries,
        )

    def ingest_directory(
        self,
        directory: str,
        glob_pattern: str = "*.md",
        metadata: dict = None,
        recursive: bool = True,
    ) -> int:
        """Ingest all matching files from directory.

        Args:
            directory: Directory path
            glob_pattern: File pattern to match
            metadata: Metadata for all files
            recursive: Search recursively

        Returns:
            Total chunks ingested
        """
        return self._service.ingest_directory(
            directory=directory,
            glob_pattern=glob_pattern,
            metadata=metadata,
            recursive=recursive,
            ingest_file_fn=self.ingest_file,
        )

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[str]:
        """Split text into overlapping chunks."""
        return self._service.chunk_text(
            text=text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _store_entries(self, entries: list[KnowledgeBaseEntry]):
        """Store entries in vector database."""
        self._service.store_entries(entries, embedding_fn=self._get_embedding)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_source: Optional[str] = None,
        filter_tags: Optional[list[str]] = None,
    ) -> list[KnowledgeBaseSearchResult]:
        """Semantic search in knowledge base.

        Args:
            query: Search query
            top_k: Number of results
            filter_source: Filter by source (logseq, affine, etc.)
            filter_tags: Filter by tags

        Returns:
            List of KnowledgeBaseSearchResult
        """
        return self._service.search(
            query=query,
            top_k=top_k,
            filter_source=filter_source,
            filter_tags=filter_tags,
            embedding_fn=self._get_embedding,
        )

    def delete_entry(self, entry_id: str):
        """Delete entry by ID."""
        self._vector_store.delete_entry(entry_id)

    def delete_by_file(self, file_path: str):
        """Delete all entries from a specific file."""
        file_path = expand_path(file_path)

        self._vector_store.delete_by_file(file_path)

    def count(self) -> int:
        """Get total number of entries."""
        return self._vector_store.count()

    def clear(self):
        """Clear all entries."""
        self._vector_store.clear()
        self._client = self._vector_store.client
        if self.mode == "chroma":
            self._collection = self._vector_store.collection
        self._write_metadata()

    def reset(self):
        """Reset kbase contents and refresh compatibility metadata."""
        self.clear()

    def list_sources(self) -> list[str]:
        """List all unique sources."""
        return self._vector_store.list_sources()

    def ingest_file_from_content(
        self,
        content: str,
        metadata: dict = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> int:
        """Ingest content directly into knowledge base (no file required).

        Args:
            content: Text content to ingest
            metadata: Additional metadata (source, url, title, etc.)
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks

        Returns:
            Number of chunks ingested
        """
        return self._service.ingest_content(
            content=content,
            metadata=metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunker=self._chunk_text,
            id_generator=self._generate_id,
            entry_storer=self._store_entries,
        )

    def stats(self) -> dict:
        """Summarize kbase entries, source files, content size, and source distribution."""
        metadatas = self._vector_store.all_metadatas()

        file_paths = set()
        sources: dict[str, int] = {}
        total_size_bytes = 0

        for meta in metadatas:
            source = meta.get("source") or "local"
            sources[source] = sources.get(source, 0) + 1

            file_path = meta.get("file_path")
            if file_path and file_path not in file_paths:
                file_paths.add(file_path)
                if os.path.exists(file_path):
                    total_size_bytes += os.path.getsize(file_path)

        return {
            "total_entries": len(metadatas),
            "source_file_count": len(file_paths),
            "total_size_bytes": total_size_bytes,
            "sources": dict(sorted(sources.items(), key=lambda item: (-item[1], item[0]))),
            "mode": self.mode,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
        }
