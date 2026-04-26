"""Knowledge base management with vector database support.

Supports two modes:
- Chroma (embedded): Default, zero external dependencies
- Qdrant (server): Production-grade, requires Docker service

Usage:
    kb = KnowledgeBase(mode="chroma")  # Embedded mode
    kb = KnowledgeBase(mode="qdrant", url="http://localhost:6333")  # Server mode

    # Ingest documents
    kb.ingest_file("~/docs/note.md", metadata={"source": "logseq"})
    kb.ingest_directory("~/notes/", glob_pattern="*.md")

    # Search
    results = kb.search("python async", top_k=5)
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
class KBEntry:
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
class KBSearchResult:
    """Knowledge base search result."""
    id: str
    content: str
    file_path: str
    title: Optional[str] = None
    source: Optional[str] = None
    score: float = 0.0
    metadata: dict = None


class KnowledgeBase:
    """Knowledge base with vector search support.

    Provides document ingestion, semantic search, and metadata filtering.
    """

    def __init__(
        self,
        mode: str = "chroma",
        persist_dir: str = "~/.ksearch/kb",
        qdrant_url: Optional[str] = None,
        embedding_model: str = "nomic-embed-text",
        ollama_url: str = "http://localhost:11434",
    ):
        """Initialize knowledge base.

        Args:
            mode: "chroma" (embedded) or "qdrant" (server)
            persist_dir: Local directory for Chroma persistence
            qdrant_url: Qdrant server URL (required for qdrant mode)
            embedding_model: Ollama embedding model name
            ollama_url: Ollama server URL for embeddings
        """
        self.mode = mode
        self.persist_dir = expand_path(persist_dir)
        self.embedding_model = embedding_model
        self.ollama_url = ollama_url

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
            name="knowledge_base",
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
        collection_name = "knowledge_base"
        if collection_name not in [c.name for c in collections]:
            # Default embedding dimension for nomic-embed-text: 768
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=768,
                    distance=Distance.Cosine
                )
            )

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
                return response.json()["embedding"]
        except Exception:
            pass  # Fallback to local

        # Fallback: Use sentence-transformers if available
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model.encode(text).tolist()
        except ImportError:
            # Last resort: Simple TF-IDF based hashing (not recommended)
            # This provides very basic semantic matching
            return self._simple_embedding(text)

    def _simple_embedding(self, text: str) -> list[float]:
        """Simple embedding fallback when no ML models available.

        Uses word frequency hashing - NOT for production use.
        """
        words = text.lower().split()
        vec = [0.0] * 768
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
            idx = hash_val % 768
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
            entry = KBEntry(
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
            start = end - chunk_overlap

        return [c for c in chunks if c]

    def _store_entries(self, entries: list[KBEntry]):
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
            self._client.upsert(collection_name="knowledge_base", points=points)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_source: Optional[str] = None,
        filter_tags: Optional[list[str]] = None,
    ) -> list[KBSearchResult]:
        """Semantic search in knowledge base.

        Args:
            query: Search query
            top_k: Number of results
            filter_source: Filter by source (logseq, affine, etc.)
            filter_tags: Filter by tags

        Returns:
            List of KBSearchResult
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

                search_results.append(KBSearchResult(
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
                collection_name="knowledge_base",
                query_vector=embedding,
                limit=top_k,
                query_filter=filter_obj,
            )

            search_results = []
            for hit in results:
                search_results.append(KBSearchResult(
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
                self._client.delete(collection_name="knowledge_base", points_selector=[int_id])
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
                collection_name="knowledge_base",
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
            info = self._client.get_collection(collection_name="knowledge_base")
            return info.points_count

    def clear(self):
        """Clear all entries."""
        if self.mode == "chroma":
            self._client.delete_collection(name="knowledge_base")
            self._collection = self._client.create_collection(
                name="knowledge_base",
                metadata={"hnsw:space": "cosine"}
            )
        elif self.mode == "qdrant":
            self._client.delete_collection(collection_name="knowledge_base")
            self._init_qdrant()
            self._client.delete_collection(collection_name="knowledge_base")
            self._init_qdrant()

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
                    collection_name="knowledge_base",
                    limit=100,
                    offset=offset,
                )
                for point in batch:
                    if "source" in point.payload:
                        sources.add(point.payload["source"])
                if offset is None:
                    break
            return list(sources)