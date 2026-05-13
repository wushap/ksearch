"""Tests for hybrid query (BM25 + vector RRF merge) integration."""

import tempfile
import pytest
from unittest.mock import Mock, patch

from ksearch.knowledge.service import KnowledgeService
from ksearch.knowledge.vector_store import KnowledgeVectorStore
from ksearch.knowledge.bm25_index import BM25Index


class TestRRFMerge:
    """Test the RRF merge logic in hybrid_query using a real Chroma store."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = KnowledgeVectorStore(
                mode="chroma",
                persist_dir=tmpdir,
                collection_name="test",
                embedding_dimension=8,
            )
            yield s

    def _make_embedding(self, seed: int) -> list[float]:
        """Simple deterministic embedding for testing."""
        vec = [float((seed * (i + 1)) % 10) / 10.0 for i in range(8)]
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm if norm else 0.0 for v in vec]

    def test_hybrid_returns_results(self, store):
        docs = ["Python asyncio programming", "Rust ownership model", "JavaScript web framework"]
        ids = ["1", "2", "3"]
        embeddings = [self._make_embedding(i) for i in range(3)]
        metadatas = [
            {"id": ids[0], "content": docs[0], "file_path": "/a", "title": "A", "source": "s1"},
            {"id": ids[1], "content": docs[1], "file_path": "/b", "title": "B", "source": "s2"},
            {"id": ids[2], "content": docs[2], "file_path": "/c", "title": "C", "source": "s3"},
        ]

        store.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

        results = store.hybrid_query(
            query="Python programming",
            embedding=embeddings[0],
            top_k=3,
        )
        assert len(results) > 0
        assert "score" in results[0]
        assert "bm25_score" in results[0]
        assert "vector_score" in results[0]
        assert isinstance(results[0]["bm25_score"], float)
        assert isinstance(results[0]["vector_score"], float)

    def test_hybrid_with_filter_source(self, store):
        docs = ["Python asyncio", "Rust async"]
        ids = ["1", "2"]
        embeddings = [self._make_embedding(i) for i in range(2)]
        metadatas = [
            {"id": ids[0], "content": docs[0], "file_path": "/a", "source": "manual"},
            {"id": ids[1], "content": docs[1], "file_path": "/b", "source": "web"},
        ]

        store.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

        results = store.hybrid_query(
            query="async",
            embedding=embeddings[0],
            top_k=5,
            filter_source="manual",
        )
        for r in results:
            assert r.get("source") == "manual" or r.get("source") is None

    def test_hybrid_empty_store(self, store):
        results = store.hybrid_query(
            query="anything",
            embedding=[0.1] * 8,
            top_k=5,
        )
        assert results == []

    def test_hybrid_rrf_combines_scores(self, store):
        """Documents found by both BM25 and vector should rank higher."""
        docs = [
            "Python async programming guide for beginners",
            "Rust systems programming with ownership",
            "Python web scraping tutorial",
        ]
        ids = ["1", "2", "3"]
        embeddings = [self._make_embedding(i + 1) for i in range(3)]
        metadatas = [
            {"id": ids[0], "content": docs[0], "file_path": "/a"},
            {"id": ids[1], "content": docs[1], "file_path": "/b"},
            {"id": ids[2], "content": docs[2], "file_path": "/c"},
        ]

        store.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

        results = store.hybrid_query(
            query="Python programming",
            embedding=embeddings[0],
            top_k=3,
        )
        assert len(results) >= 1
        # First result should have the highest RRF score
        assert results[0]["score"] >= results[-1]["score"]

    def test_hybrid_top_k_limit(self, store):
        docs = [f"document number {i} about topic {i}" for i in range(10)]
        ids = [str(i) for i in range(10)]
        embeddings = [self._make_embedding(i) for i in range(10)]
        metadatas = [{"id": str(i), "content": docs[i], "file_path": f"/{i}"} for i in range(10)]

        store.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

        results = store.hybrid_query(
            query="document topic",
            embedding=embeddings[0],
            top_k=3,
        )
        assert len(results) <= 3


class TestNormalizeVectorResults:
    """Test _normalize_vector_results for Chroma backend."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = KnowledgeVectorStore(
                mode="chroma",
                persist_dir=tmpdir,
                collection_name="test_norm",
                embedding_dimension=8,
            )
            yield s

    def test_normalize_chroma_empty(self, store):
        assert store._normalize_vector_results({}) == []
        assert store._normalize_vector_results({"ids": [[]]}) == []

    def test_normalize_chroma_results(self, store):
        raw = {
            "ids": [["id1"]],
            "documents": [["content1"]],
            "metadatas": [[{"file_path": "/a", "title": "T", "source": "s"}]],
            "distances": [[0.3]],
        }
        results = store._normalize_vector_results(raw)
        assert len(results) == 1
        assert results[0]["id"] == "id1"
        assert results[0]["content"] == "content1"
        assert abs(results[0]["score"] - 0.7) < 1e-9


class TestBM25Lifecycle:
    """Test BM25 index stays in sync with vector store mutations."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            s = KnowledgeVectorStore(
                mode="chroma",
                persist_dir=tmpdir,
                collection_name="test_lifecycle",
                embedding_dimension=8,
            )
            yield s

    def _make_embedding(self, seed: int) -> list[float]:
        vec = [float((seed * (i + 1)) % 10) / 10.0 for i in range(8)]
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm if norm else 0.0 for v in vec]

    def test_bm25_built_on_init(self, store):
        assert store.bm25.size == 0

    def test_bm25_updated_after_add(self, store):
        store.add(
            ids=["1"],
            documents=["test content"],
            embeddings=[self._make_embedding(1)],
            metadatas=[{"id": "1", "content": "test content", "file_path": "/a"}],
        )
        assert store.bm25.size == 1

    def test_bm25_cleared_on_clear(self, store):
        store.add(
            ids=["1"],
            documents=["test content"],
            embeddings=[self._make_embedding(1)],
            metadatas=[{"id": "1", "content": "test content", "file_path": "/a"}],
        )
        assert store.bm25.size == 1
        store.clear()
        assert store.bm25.size == 0

    def test_bm25_updated_after_delete_entry(self, store):
        store.add(
            ids=["1", "2"],
            documents=["doc one", "doc two"],
            embeddings=[self._make_embedding(1), self._make_embedding(2)],
            metadatas=[
                {"id": "1", "content": "doc one", "file_path": "/a"},
                {"id": "2", "content": "doc two", "file_path": "/b"},
            ],
        )
        assert store.bm25.size == 2
        store.delete_entry("1")
        assert store.bm25.size == 1


def test_knowledge_service_logs_hybrid_candidate_counts():
    vector_store = Mock()
    vector_store.bm25.size = 3
    vector_store.hybrid_query.return_value = [
        {
            "id": "a",
            "content": "asyncio cancellation propagation",
            "score": 0.8,
            "file_path": "/tmp/a.md",
            "title": "A",
            "source": "manual",
            "metadata": {},
        }
    ]

    service = KnowledgeService(
        mode="chroma",
        vector_store=vector_store,
        embed_text=lambda text: [0.1, 0.2],
        id_generator=lambda file_path, content, chunk_index: "id",
        entry_cls=dict,
        result_cls=lambda **kwargs: kwargs,
        reranker=None,
        use_hybrid=True,
        use_rerank=False,
    )

    with patch("ksearch.knowledge.service.log_event") as log_event:
        service.search("asyncio cancellation", top_k=1, embedding_fn=lambda text: [0.1, 0.2])

    names = [call.args[1] for call in log_event.call_args_list]
    assert "hybrid_retrieval_selected" in names
    assert "candidate_dicts_ready" in names


def test_knowledge_service_preserves_relevance_signals_in_result_metadata():
    vector_store = Mock()
    vector_store.bm25.size = 3
    vector_store.hybrid_query.return_value = [
        {
            "id": "a",
            "content": "asyncio cancellation propagation",
            "score": 0.024,
            "vector_score": 0.61,
            "bm25_score": 4.2,
            "rerank_score": 0.82,
            "file_path": "/tmp/a.md",
            "title": "A",
            "source": "manual",
            "metadata": {"existing": "value"},
        }
    ]

    service = KnowledgeService(
        mode="chroma",
        vector_store=vector_store,
        embed_text=lambda text: [0.1, 0.2],
        id_generator=lambda file_path, content, chunk_index: "id",
        entry_cls=dict,
        result_cls=lambda **kwargs: kwargs,
        reranker=None,
        use_hybrid=True,
        use_rerank=False,
    )

    results = service.search("asyncio cancellation", top_k=1, embedding_fn=lambda text: [0.1, 0.2])

    assert results[0]["metadata"]["existing"] == "value"
    assert results[0]["metadata"]["retrieval_score"] == pytest.approx(0.024)
    assert results[0]["metadata"]["vector_score"] == pytest.approx(0.61)
    assert results[0]["metadata"]["bm25_score"] == pytest.approx(4.2)
    assert results[0]["metadata"]["rerank_score"] == pytest.approx(0.82)


def test_hybrid_query_logs_bm25_and_vector_counts():
    def make_embedding(seed: int) -> list[float]:
        vec = [float((seed * (i + 1)) % 10) / 10.0 for i in range(8)]
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm if norm else 0.0 for v in vec]

    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeVectorStore(
            mode="chroma",
            persist_dir=tmpdir,
            collection_name="test_events",
            embedding_dimension=8,
        )
        docs = ["Python asyncio programming", "Rust ownership model"]
        ids = ["1", "2"]
        embeddings = [make_embedding(i + 1) for i in range(2)]
        metadatas = [
            {"id": ids[0], "content": docs[0], "file_path": "/a", "title": "A", "source": "s1"},
            {"id": ids[1], "content": docs[1], "file_path": "/b", "title": "B", "source": "s2"},
        ]
        store.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

        with patch("ksearch.knowledge.vector_store.log_event") as log_event:
            store.hybrid_query(query="Python programming", embedding=embeddings[0], top_k=2)

    names = [call.args[1] for call in log_event.call_args_list]
    assert "bm25_hits_ready" in names
    assert "vector_hits_ready" in names
    assert "hybrid_ranked" in names
