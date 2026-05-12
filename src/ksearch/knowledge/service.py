"""Knowledge service assembled from chunking and vector store collaborators."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from ksearch.config import expand_path
from ksearch.debug_logging import log_event
from ksearch.embeddings import build_kbase_embedding_function
from ksearch.knowledge.chunking import chunk_text
from ksearch.knowledge.vector_store import KnowledgeVectorStore


class KnowledgeService:
    """Core ingest and query behavior behind KnowledgeBase compatibility API."""

    def __init__(
        self,
        *,
        mode: str,
        vector_store: KnowledgeVectorStore,
        embed_text: Callable[[str], list[float]],
        id_generator: Callable[[str, str, int], str],
        entry_cls,
        result_cls,
        reranker=None,
        use_hybrid: bool = True,
        use_rerank: bool = True,
    ):
        self.mode = mode
        self.vector_store = vector_store
        self.embed_text = embed_text
        self.id_generator = id_generator
        self.entry_cls = entry_cls
        self.result_cls = result_cls
        self.reranker = reranker
        self.use_hybrid = use_hybrid
        self.use_rerank = use_rerank

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[str]:
        return chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def ingest_file(
        self,
        file_path: str,
        metadata: dict = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        chunker: Optional[Callable[[str, int, int], list[str]]] = None,
        id_generator: Optional[Callable[[str, str, int], str]] = None,
        entry_storer: Optional[Callable[[list], None]] = None,
    ) -> int:
        file_path = expand_path(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        lines = content.split("\n")
        title = None
        if lines and lines[0].startswith("#"):
            title = lines[0].lstrip("#").strip()
        if not title:
            title = Path(file_path).stem

        chunk_fn = chunker or self.chunk_text
        id_fn = id_generator or self.id_generator
        store_fn = entry_storer or self.store_entries

        chunks = chunk_fn(content, chunk_size, chunk_overlap)
        entries = []
        for i, chunk in enumerate(chunks):
            entry_id = id_fn(file_path, chunk, i)
            entry = self.entry_cls(
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

        store_fn(entries)
        return len(entries)

    def ingest_directory(
        self,
        directory: str,
        glob_pattern: str = "*.md",
        metadata: dict = None,
        recursive: bool = True,
        ingest_file_fn: Optional[Callable[..., int]] = None,
    ) -> int:
        directory = expand_path(directory)
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"Not a directory: {directory}")

        pattern = "**/" + glob_pattern if recursive else glob_pattern
        files = list(Path(directory).glob(pattern))

        ingest_fn = ingest_file_fn or self.ingest_file
        total_chunks = 0
        for file_path in files:
            try:
                chunks = ingest_fn(
                    str(file_path),
                    metadata={
                        **(metadata or {}),
                        "directory": directory,
                    },
                )
                total_chunks += chunks
            except Exception as e:
                print(f"Warning: Failed to ingest {file_path}: {e}")

        return total_chunks

    def ingest_content(
        self,
        content: str,
        metadata: dict = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        chunker: Optional[Callable[[str, int, int], list[str]]] = None,
        id_generator: Optional[Callable[[str, str, int], str]] = None,
        entry_storer: Optional[Callable[[list], None]] = None,
    ) -> int:
        if not content:
            return 0

        source = metadata.get("source", "web") if metadata else "web"
        url = metadata.get("url", "") if metadata else ""
        title = metadata.get("title", "Untitled") if metadata else "Untitled"
        provided_file_path = metadata.get("file_path") if metadata else None

        if provided_file_path:
            file_path = provided_file_path
        elif url:
            file_path = f"web:{url}"
        else:
            import hashlib

            file_path = f"content:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

        chunk_fn = chunker or self.chunk_text
        id_fn = id_generator or self.id_generator
        store_fn = entry_storer or self.store_entries

        chunks = chunk_fn(content, chunk_size, chunk_overlap)
        entries = []
        for i, chunk in enumerate(chunks):
            entry_id = id_fn(file_path, chunk, i)
            entry = self.entry_cls(
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

        store_fn(entries)
        return len(entries)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_source: Optional[str] = None,
        filter_tags: Optional[list[str]] = None,
        embedding_fn: Optional[Callable[[str], list[float]]] = None,
    ) -> list:
        del filter_tags  # Reserved for compatibility.
        embed_fn = embedding_fn or self.embed_text
        embedding = embed_fn(query)
        log_event(
            "ksearch.knowledge.service",
            "query_embedding_ready",
            {"query": query, "top_k": top_k},
        )

        # Stage 1: Retrieval
        if self.use_hybrid and self.vector_store.bm25.size > 0:
            log_event(
                "ksearch.knowledge.service",
                "hybrid_retrieval_selected",
                {"bm25_size": self.vector_store.bm25.size},
            )
            candidate_dicts = self.vector_store.hybrid_query(
                query=query,
                embedding=embedding,
                top_k=top_k * 4,
                filter_source=filter_source,
            )
        else:
            log_event(
                "ksearch.knowledge.service",
                "vector_retrieval_selected",
                {"top_k": top_k * 4},
            )
            raw_results = self.vector_store.query(
                embedding=embedding,
                top_k=top_k * 4,
                filter_source=filter_source,
            )
            candidate_dicts = self._format_raw_results(raw_results)
        log_event(
            "ksearch.knowledge.service",
            "candidate_dicts_ready",
            {"count": len(candidate_dicts), "use_rerank": self.use_rerank},
        )

        # Stage 2: Re-ranking
        if self.use_rerank and self.reranker and candidate_dicts:
            candidate_dicts = self.reranker.rerank(query, candidate_dicts, top_k=top_k)

        candidate_dicts = candidate_dicts[:top_k]

        # Convert dicts to result objects
        search_results = []
        for doc in candidate_dicts:
            search_results.append(
                self.result_cls(
                    id=doc.get("id", ""),
                    content=doc.get("content", ""),
                    file_path=doc.get("file_path", ""),
                    title=doc.get("title"),
                    source=doc.get("source"),
                    score=doc.get("score", 0.0),
                    metadata=doc.get("metadata", {}),
                )
            )
        return search_results

    def _format_raw_results(self, results) -> list[dict]:
        """Convert backend-specific raw results into uniform dict list."""
        if self.mode == "chroma":
            if not results or not results.get("ids") or not results["ids"][0]:
                return []
            formatted = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 0.0
                formatted.append({
                    "id": doc_id,
                    "content": results["documents"][0][i] if results.get("documents") else "",
                    "score": 1.0 - distance,
                    "file_path": meta.get("file_path", ""),
                    "title": meta.get("title"),
                    "source": meta.get("source"),
                    "metadata": meta,
                })
            return formatted

        # Qdrant
        formatted = []
        for hit in (results or []):
            payload = hit.payload or {}
            doc_id = payload.get("id", str(hit.id))
            formatted.append({
                "id": doc_id,
                "content": payload.get("content", ""),
                "score": hit.score,
                "file_path": payload.get("file_path", ""),
                "title": payload.get("title"),
                "source": payload.get("source"),
                "metadata": payload,
            })
        return formatted

    def store_entries(
        self,
        entries: list,
        embedding_fn: Optional[Callable[[str], list[float]]] = None,
    ) -> None:
        if not entries:
            return

        ids = [e.id for e in entries]
        documents = [e.content for e in entries]
        metadatas = [self._entry_metadata(e) for e in entries]
        embed_fn = embedding_fn or self.embed_text
        embeddings = [embed_fn(d) for d in documents]

        self.vector_store.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    @staticmethod
    def _entry_metadata(entry) -> dict:
        meta = asdict(entry)
        filtered_meta = {}
        for key, value in meta.items():
            if value is None:
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            if key == "metadata" and isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if nested_value is not None and not (
                        isinstance(nested_value, list) and len(nested_value) == 0
                    ):
                        filtered_meta[nested_key] = nested_value
            else:
                filtered_meta[key] = value
        return filtered_meta


def build_knowledge_service(
    *,
    mode: str,
    persist_dir: str,
    collection_name: str,
    embedding_mode: str,
    embedding_model: str,
    embedding_dimension: int,
    ollama_url: str,
    qdrant_url: Optional[str],
    id_generator: Callable[[str, str, int], str],
    entry_cls,
    result_cls,
    allow_embedding_fallback: bool = False,
    reranker=None,
    use_hybrid: bool = True,
    use_rerank: bool = True,
) -> tuple[KnowledgeService, KnowledgeVectorStore]:
    """Assemble knowledge collaborators for compatibility KnowledgeBase."""
    vector_store = KnowledgeVectorStore(
        mode=mode,
        persist_dir=persist_dir,
        collection_name=collection_name,
        embedding_dimension=embedding_dimension,
        qdrant_url=qdrant_url,
    )
    embed_text = build_kbase_embedding_function(
        embedding_mode=embedding_mode,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
        allow_embedding_fallback=allow_embedding_fallback,
    )
    service = KnowledgeService(
        mode=mode,
        vector_store=vector_store,
        embed_text=embed_text,
        id_generator=id_generator,
        entry_cls=entry_cls,
        result_cls=result_cls,
        reranker=reranker,
        use_hybrid=use_hybrid,
        use_rerank=use_rerank,
    )
    return service, vector_store
