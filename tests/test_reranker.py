"""Tests for cross-encoder re-ranker module."""

import pytest

from ksearch.knowledge.reranker import ReRanker


class TestReRanker:
    def test_rerank_empty_documents(self):
        reranker = ReRanker()
        results = reranker.rerank("test query", [], top_k=5)
        assert results == []

    def test_rerank_fallback_without_model(self):
        """When model is unavailable, returns docs unchanged."""
        reranker = ReRanker(model_name="nonexistent-model-that-wont-load")

        docs = [
            {"id": "1", "content": "Python async programming", "score": 0.9},
            {"id": "2", "content": "Rust ownership model", "score": 0.8},
        ]
        results = reranker.rerank("python async", docs, top_k=5)
        assert len(results) == 2
        # Fallback returns docs in original order
        assert results[0]["id"] == "1"

    def test_rerank_truncates_content(self):
        """Content is truncated to max_content_length for scoring."""
        reranker = ReRanker(max_content_length=100)
        long_content = "word " * 1000
        docs = [{"id": "1", "content": long_content, "score": 0.5}]
        # Should not raise, content is truncated internally
        results = reranker.rerank("test", docs, top_k=1)
        assert len(results) == 1

    def test_rerank_preserves_original_fields(self):
        """Re-ranking should not remove original document fields."""
        reranker = ReRanker()
        docs = [
            {"id": "1", "content": "test", "score": 0.5, "extra": "value"},
        ]
        results = reranker.rerank("test", docs, top_k=1)
        assert results[0]["id"] == "1"
        assert results[0]["extra"] == "value"

    def test_rerank_respects_top_k(self):
        """Should return at most top_k results."""
        reranker = ReRanker()
        docs = [{"id": str(i), "content": f"doc {i}", "score": 0.5} for i in range(20)]
        results = reranker.rerank("test", docs, top_k=3)
        assert len(results) <= 3

    def test_rerank_handles_missing_content(self):
        """Should not crash on docs without content key."""
        reranker = ReRanker()
        docs = [{"id": "1", "score": 0.5}]
        results = reranker.rerank("test", docs, top_k=1)
        assert len(results) == 1
