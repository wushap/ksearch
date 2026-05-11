"""Vector store adapter for kbase backends."""

from __future__ import annotations

from typing import Optional

from ksearch.debug_logging import log_event
from ksearch.knowledge.bm25_index import BM25Index


class KnowledgeVectorStore:
    """Compatibility wrapper over Chroma and Qdrant operations."""

    def __init__(
        self,
        *,
        mode: str,
        persist_dir: str,
        collection_name: str,
        embedding_dimension: int,
        qdrant_url: Optional[str] = None,
    ):
        self.mode = mode
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_dimension = embedding_dimension
        self.qdrant_url = qdrant_url
        self.client = None
        self.collection = None
        self.bm25 = BM25Index()
        self._init_store()
        self._build_bm25_index()

    def _init_store(self) -> None:
        if self.mode == "chroma":
            self._init_chroma()
        elif self.mode == "qdrant":
            self._init_qdrant()
        else:
            raise ValueError(f"Unknown mode: {self.mode}. Use 'chroma' or 'qdrant'")

    def _build_bm25_index(self) -> None:
        """Build BM25 index from all stored documents."""
        metadatas = self.all_metadatas()
        if not metadatas:
            self.bm25.clear()
            return
        ids = []
        documents = []
        filtered_metas = []
        for i, meta in enumerate(metadatas):
            content = meta.get("content", "")
            doc_id = meta.get("id", str(i))
            if content:
                ids.append(doc_id)
                documents.append(content)
                filtered_metas.append(meta)
        self.bm25.build(ids, documents, filtered_metas)

    def _init_chroma(self) -> None:
        try:
            import chromadb
        except ImportError:
            raise ImportError("chromadb not installed. Run: pip install chromadb")

        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _init_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError:
            raise ImportError("qdrant-client not installed. Run: pip install qdrant-client")

        self.client = QdrantClient(url=self.qdrant_url)
        collections = self.client.get_collections().collections
        if self.collection_name not in [c.name for c in collections]:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dimension,
                    distance=Distance.Cosine,
                ),
            )

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        if self.mode == "chroma":
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            self._rebuild_bm25()
            return

        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=int(entry_id, 16) % (2**63),
                vector=embedding,
                payload=metadata,
            )
            for entry_id, embedding, metadata in zip(ids, embeddings, metadatas)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

        self._rebuild_bm25()

    def query(
        self,
        *,
        embedding: list[float],
        top_k: int,
        filter_source: Optional[str] = None,
    ):
        if self.mode == "chroma":
            where = None
            if filter_source:
                where = {"source": filter_source}
            return self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where,
            )

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        filter_obj = None
        if filter_source:
            filter_obj = Filter(
                must=[
                    FieldCondition(
                        key="source",
                        value=MatchValue(value=filter_source),
                    )
                ]
            )

        return self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            limit=top_k,
            query_filter=filter_obj,
        )

    def _rebuild_bm25(self) -> None:
        """Rebuild BM25 index from current stored documents."""
        self._build_bm25_index()

    def delete_entry(self, entry_id: str) -> None:
        if self.mode == "chroma":
            self.collection.delete(ids=[entry_id])
            self._rebuild_bm25()
            return

        try:
            int_id = int(entry_id, 16) % (2**63)
            self.client.delete(collection_name=self.collection_name, points_selector=[int_id])
        except ValueError:
            pass
        self._rebuild_bm25()

    def delete_by_file(self, file_path: str) -> None:
        if self.mode == "chroma":
            self.collection.delete(where={"file_path": file_path})
            self._rebuild_bm25()
            return

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="file_path",
                        value=MatchValue(value=file_path),
                    )
                ]
            ),
        )
        self._rebuild_bm25()

    def count(self) -> int:
        if self.mode == "chroma":
            return self.collection.count()
        info = self.client.get_collection(collection_name=self.collection_name)
        return info.points_count or 0

    def clear(self) -> None:
        if self.mode == "chroma":
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self.bm25.clear()
            return

        self.client.delete_collection(collection_name=self.collection_name)
        self._init_qdrant()
        self.bm25.clear()

    def list_sources(self) -> list[str]:
        if self.mode == "chroma":
            results = self.collection.get()
            sources = set()
            for meta in results["metadatas"]:
                if "source" in meta:
                    sources.add(meta["source"])
            return list(sources)

        sources = set()
        offset = None
        while True:
            batch, offset = self.client.scroll(
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

    def all_metadatas(self) -> list[dict]:
        if self.mode == "chroma":
            results = self.collection.get(include=["metadatas"])
            return results.get("metadatas", [])

        metadatas = []
        offset = None
        while True:
            batch, offset = self.client.scroll(
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
        return metadatas

    def hybrid_query(
        self,
        *,
        query: str,
        embedding: list[float],
        top_k: int,
        bm25_top_k: int = 20,
        vector_top_k: int = 20,
        rrf_k: int = 60,
        filter_source: Optional[str] = None,
    ) -> list[dict]:
        """Run BM25 + vector search, merge with RRF, return *top_k* results.

        Returns a list of dicts with keys: ``id``, ``content``, ``score``,
        ``file_path``, ``title``, ``source``, ``metadata``.
        Each dict also carries the original ``bm25_score`` and ``vector_score``
        for downstream inspection.
        """
        # 1. BM25 retrieval
        bm25_hits = self.bm25.query(query, top_k=bm25_top_k)
        log_event(
            "ksearch.knowledge.vector_store",
            "bm25_hits_ready",
            {"count": len(bm25_hits)},
        )

        # 2. Vector retrieval
        vector_raw = self.query(
            embedding=embedding, top_k=vector_top_k, filter_source=filter_source
        )
        vector_hits = self._normalize_vector_results(vector_raw)
        log_event(
            "ksearch.knowledge.vector_store",
            "vector_hits_ready",
            {"count": len(vector_hits)},
        )

        # 3. RRF merge
        scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}

        for rank, hit in enumerate(bm25_hits):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (rrf_k + rank + 1)
            if hit.id not in doc_map:
                doc_map[hit.id] = {
                    "id": hit.id,
                    "content": hit.content,
                    "score": 0.0,
                    "file_path": hit.metadata.get("file_path", ""),
                    "title": hit.metadata.get("title"),
                    "source": hit.metadata.get("source"),
                    "metadata": hit.metadata,
                    "bm25_score": hit.score,
                    "vector_score": 0.0,
                }

        for rank, hit in enumerate(vector_hits):
            doc_id = hit["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank + 1)
            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "id": hit["id"],
                    "content": hit.get("content", ""),
                    "score": 0.0,
                    "file_path": hit.get("file_path", ""),
                    "title": hit.get("title"),
                    "source": hit.get("source"),
                    "metadata": hit.get("metadata", {}),
                    "bm25_score": 0.0,
                    "vector_score": hit.get("score", 0.0),
                }
            else:
                doc_map[doc_id]["vector_score"] = hit.get("score", 0.0)

        # 4. Sort by RRF score, take top_k
        for doc_id, rrf_score in scores.items():
            doc_map[doc_id]["score"] = rrf_score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        log_event(
            "ksearch.knowledge.vector_store",
            "hybrid_ranked",
            {"count": len(ranked), "rrf_k": rrf_k},
        )
        return [doc_map[doc_id] for doc_id, _ in ranked]

    def _normalize_vector_results(self, raw_results) -> list[dict]:
        """Convert backend-specific vector results into a uniform dict list."""
        if self.mode == "chroma":
            if not raw_results or not raw_results.get("ids") or not raw_results["ids"][0]:
                return []
            results = []
            for i, doc_id in enumerate(raw_results["ids"][0]):
                meta = raw_results["metadatas"][0][i] if raw_results.get("metadatas") else {}
                distance = raw_results["distances"][0][i] if raw_results.get("distances") else 0.0
                results.append({
                    "id": doc_id,
                    "content": raw_results["documents"][0][i] if raw_results.get("documents") else "",
                    "score": 1.0 - distance,
                    "file_path": meta.get("file_path", ""),
                    "title": meta.get("title"),
                    "source": meta.get("source"),
                    "metadata": meta,
                })
            return results

        # Qdrant
        results = []
        for hit in (raw_results or []):
            payload = hit.payload or {}
            doc_id = payload.get("id", str(hit.id))
            results.append({
                "id": doc_id,
                "content": payload.get("content", ""),
                "score": hit.score,
                "file_path": payload.get("file_path", ""),
                "title": payload.get("title"),
                "source": payload.get("source"),
                "metadata": payload,
            })
        return results
