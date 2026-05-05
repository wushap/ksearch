"""Vector store adapter for kbase backends."""

from __future__ import annotations

from typing import Optional


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
        self._init_store()

    def _init_store(self) -> None:
        if self.mode == "chroma":
            self._init_chroma()
        elif self.mode == "qdrant":
            self._init_qdrant()
        else:
            raise ValueError(f"Unknown mode: {self.mode}. Use 'chroma' or 'qdrant'")

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

    def delete_entry(self, entry_id: str) -> None:
        if self.mode == "chroma":
            self.collection.delete(ids=[entry_id])
            return

        try:
            int_id = int(entry_id, 16) % (2**63)
            self.client.delete(collection_name=self.collection_name, points_selector=[int_id])
        except ValueError:
            pass

    def delete_by_file(self, file_path: str) -> None:
        if self.mode == "chroma":
            self.collection.delete(where={"file_path": file_path})
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
            return

        self.client.delete_collection(collection_name=self.collection_name)
        self._init_qdrant()

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
