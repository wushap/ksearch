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
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from ksearch.config import expand_path


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
    ):
        """Initialize knowledge base.

        Args:
            mode: "chroma" (embedded) or "qdrant" (server)
            persist_dir: Local directory for Chroma persistence
            qdrant_url: Qdrant server URL (required for qdrant mode)
            embedding_model: Ollama embedding model name
            embedding_dimension: Expected embedding vector size
            ollama_url: Ollama server URL for embeddings
        """
        self.mode = mode
        self.persist_dir = expand_path(persist_dir)
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.ollama_url = ollama_url
        self.collection_name = "kbase"
        self.metadata_path = os.path.join(self.persist_dir, "_kbase_metadata.json")

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
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb not installed. Run: pip install chromadb"
            )

        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def _init_qdrant(self):
        """Initialize Qdrant server mode."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError:
            raise ImportError(
                "qdrant-client not installed. Run: pip install qdrant-client"
            )

        self._client = QdrantClient(url=self.qdrant_url)

        # Create collection if not exists
        collections = self._client.get_collections().collections
        collection_name = self.collection_name
        if collection_name not in [c.name for c in collections]:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dimension,
                    distance=Distance.Cosine
                )
            )

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
        # Try Ollama first
        try:
            import requests
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.embedding_model, "prompt": text},
                timeout=30
            )
            if response.status_code == 200:
                embedding = response.json()["embedding"]
                if len(embedding) != self.embedding_dimension:
                    raise ValueError(
                        f"Embedding dimension mismatch for model '{self.embedding_model}': "
                        f"expected {self.embedding_dimension}, got {len(embedding)}"
                    )
                return embedding
        except Exception:
            pass  # Fallback to local

        # Fallback: Use sentence-transformers if available
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedding = model.encode(text).tolist()
            if len(embedding) == self.embedding_dimension:
                return embedding
        except ImportError:
            pass

        # Last resort: Simple TF-IDF based hashing (not recommended)
        # This provides very basic semantic matching
        return self._simple_embedding(text)

    def _simple_embedding(self, text: str) -> list[float]:
        """Simple embedding fallback when no ML models available.

        Uses word frequency hashing - NOT for production use.
        """
        words = text.lower().split()
        vec = [0.0] * self.embedding_dimension
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
            idx = hash_val % self.embedding_dimension
            vec[idx] += 1.0
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def _generate_id(self, file_path: str, content: str) -> str:
        """Generate unique ID for entry."""
        hash_input = f"{file_path}:{content[:100]}"
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
        file_path = expand_path(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract title from first line or filename
        lines = content.split("\n")
        title = None
        if lines and lines[0].startswith("#"):
            title = lines[0].lstrip("#").strip()
        if not title:
            title = Path(file_path).stem

        # Chunk content
        chunks = self._chunk_text(content, chunk_size, chunk_overlap)

        entries = []
        for i, chunk in enumerate(chunks):
            entry_id = self._generate_id(file_path, chunk)
            entry = KnowledgeBaseEntry(
                id=entry_id,
                content=chunk,
                file_path=file_path,
                title=title,
                metadata={
                    **(metadata or {}),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            )
            entries.append(entry)

        # Store in vector DB
        self._store_entries(entries)
        return len(entries)

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
        directory = expand_path(directory)
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        pattern = "**/" + glob_pattern if recursive else glob_pattern
        files = list(Path(directory).glob(pattern))

        total_chunks = 0
        for file_path in files:
            try:
                chunks = self.ingest_file(
                    str(file_path),
                    metadata={
                        **(metadata or {}),
                        "directory": directory,
                    }
                )
                total_chunks += chunks
            except Exception as e:
                # Log error but continue
                print(f"Warning: Failed to ingest {file_path}: {e}")

        return total_chunks

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        effective_overlap = min(chunk_overlap, max(chunk_size - 1, 0))
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind(".")
                last_newline = chunk.rfind("\n")
                break_point = max(last_period, last_newline)
                if break_point > chunk_size * 0.5:
                    chunk = text[start:start + break_point + 1]
                    end = start + break_point + 1

            chunks.append(chunk.strip())
            next_start = end - effective_overlap
            if next_start <= start:
                next_start = end
            start = next_start

        return [c for c in chunks if c]

    def _store_entries(self, entries: list[KnowledgeBaseEntry]):
        """Store entries in vector database."""
        if not entries:
            return

        ids = [e.id for e in entries]
        documents = [e.content for e in entries]
        metadatas = []

        for e in entries:
            meta = asdict(e)
            # Chroma doesn't like empty lists in metadata
            # Filter out empty lists and None values
            filtered_meta = {}
            for k, v in meta.items():
                if v is None:
                    continue
                if isinstance(v, list) and len(v) == 0:
                    continue
                if k == "metadata" and isinstance(v, dict):
                    # Flatten nested metadata
                    for mk, mv in v.items():
                        if mv is not None and not (isinstance(mv, list) and len(mv) == 0):
                            filtered_meta[mk] = mv
                else:
                    filtered_meta[k] = v
            metadatas.append(filtered_meta)

        # Get embeddings
        embeddings = [self._get_embedding(d) for d in documents]

        if self.mode == "chroma":
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        elif self.mode == "qdrant":
            from qdrant_client.models import PointStruct
            points = [
                PointStruct(
                    id=int(e.id, 16) % (2**63),  # Convert to int
                    vector=emb,
                    payload=meta,
                )
                for e, emb, meta in zip(entries, embeddings, metadatas)
            ]
            self._client.upsert(collection_name=self.collection_name, points=points)

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
        embedding = self._get_embedding(query)

        if self.mode == "chroma":
            where = None
            if filter_source:
                where = {"source": filter_source}

            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where,
            )

            search_results = []
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i]
                distance = results["distances"][0][i]
                score = 1.0 - distance  # Cosine similarity

                search_results.append(KnowledgeBaseSearchResult(
                    id=results["ids"][0][i],
                    content=doc,
                    file_path=meta.get("file_path", ""),
                    title=meta.get("title"),
                    source=meta.get("source"),
                    score=score,
                    metadata=meta,
                ))
            return search_results

        elif self.mode == "qdrant":
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            filter_obj = None
            if filter_source:
                filter_obj = Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            value=MatchValue(value=filter_source)
                        )
                    ]
                )

            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=embedding,
                limit=top_k,
                query_filter=filter_obj,
            )

            search_results = []
            for hit in results:
                search_results.append(KnowledgeBaseSearchResult(
                    id=str(hit.id),
                    content=hit.payload.get("content", ""),
                    file_path=hit.payload.get("file_path", ""),
                    title=hit.payload.get("title"),
                    source=hit.payload.get("source"),
                    score=hit.score,
                    metadata=hit.payload,
                ))
            return search_results

    def delete_entry(self, entry_id: str):
        """Delete entry by ID."""
        if self.mode == "chroma":
            self._collection.delete(ids=[entry_id])
        elif self.mode == "qdrant":
            try:
                int_id = int(entry_id, 16) % (2**63)
                self._client.delete(collection_name=self.collection_name, points_selector=[int_id])
            except ValueError:
                pass

    def delete_by_file(self, file_path: str):
        """Delete all entries from a specific file."""
        file_path = expand_path(file_path)

        if self.mode == "chroma":
            self._collection.delete(
                where={"file_path": file_path}
            )
        elif self.mode == "qdrant":
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="file_path",
                            value=MatchValue(value=file_path)
                        )
                    ]
                )
            )

    def count(self) -> int:
        """Get total number of entries."""
        if self.mode == "chroma":
            return self._collection.count()
        elif self.mode == "qdrant":
            info = self._client.get_collection(collection_name=self.collection_name)
            return info.points_count

    def clear(self):
        """Clear all entries."""
        if self.mode == "chroma":
            self._client.delete_collection(name=self.collection_name)
            self._collection = self._client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        elif self.mode == "qdrant":
            self._client.delete_collection(collection_name=self.collection_name)
            self._init_qdrant()
        self._write_metadata()

    def reset(self):
        """Reset kbase contents and refresh compatibility metadata."""
        self.clear()

    def list_sources(self) -> list[str]:
        """List all unique sources."""
        if self.mode == "chroma":
            # Chroma doesn't have built-in aggregation
            results = self._collection.get()
            sources = set()
            for meta in results["metadatas"]:
                if "source" in meta:
                    sources.add(meta["source"])
            return list(sources)
        elif self.mode == "qdrant":
            # Scroll through collection
            sources = set()
            offset = None
            while True:
                batch, offset = self._client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                )
                for point in batch:
                    if "source" in point.payload:
                        sources.add(point.payload["source"])
                if offset is None:
                    break
            return list(sources)

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
        if not content:
            return 0

        # Reuse persisted cache path when available; otherwise synthesize one.
        source = metadata.get("source", "web") if metadata else "web"
        url = metadata.get("url", "") if metadata else ""
        title = metadata.get("title", "Untitled") if metadata else "Untitled"
        provided_file_path = metadata.get("file_path") if metadata else None

        # Use provided cache path when available, otherwise use URL or content hash.
        if provided_file_path:
            file_path = provided_file_path
        elif url:
            file_path = f"web:{url}"
        else:
            file_path = f"content:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

        # Chunk content
        chunks = self._chunk_text(content, chunk_size, chunk_overlap)

        entries = []
        for i, chunk in enumerate(chunks):
            entry_id = self._generate_id(file_path, chunk)
            entry = KnowledgeBaseEntry(
                id=entry_id,
                content=chunk,
                file_path=file_path,
                title=title,
                source=source,
                metadata={
                    **(metadata or {}),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            )
            entries.append(entry)

        # Store in vector DB
        self._store_entries(entries)
        return len(entries)

    def stats(self) -> dict:
        """Summarize kbase entries, source files, content size, and source distribution."""
        if self.mode == "chroma":
            results = self._collection.get(include=["metadatas"])
            metadatas = results.get("metadatas", [])
        elif self.mode == "qdrant":
            metadatas = []
            offset = None
            while True:
                batch, offset = self._client.scroll(
                    collection_name=self.collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in batch:
                    metadatas.append(point.payload or {})
                if offset is None:
                    break
        else:
            metadatas = []

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
