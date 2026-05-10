"""Tests for Ollama-backed re-ranker module."""

from unittest.mock import MagicMock, patch

import pytest

from ksearch.knowledge.reranker import ReRanker


class TestReRanker:
    def test_default_model_uses_ollama_reranker(self):
        reranker = ReRanker()
        assert reranker.model_name == "gemma4:e2b"

    def test_rerank_empty_documents(self):
        reranker = ReRanker()
        results = reranker.rerank("test query", [], top_k=5)
        assert results == []

    def test_rerank_fallback_when_ollama_unavailable(self):
        """When Ollama reranking fails, returns docs unchanged."""
        reranker = ReRanker(model_name="gemma4:e2b", ollama_url="http://localhost:11434")

        docs = [
            {"id": "1", "content": "Python async programming", "score": 0.9},
            {"id": "2", "content": "Rust ownership model", "score": 0.8},
        ]
        with patch("ksearch.knowledge.reranker.requests.post", side_effect=ConnectionError):
            results = reranker.rerank("python async", docs, top_k=5)

        assert len(results) == 2
        assert results[0]["id"] == "1"

    def test_rerank_uses_ollama_chat_scores(self):
        """Reranking should sort by scores returned from Ollama chat."""
        reranker = ReRanker(model_name="gemma4:e2b", ollama_url="http://localhost:11434")
        docs = [
            {"id": "1", "content": "Rust ownership model", "score": 0.9},
            {"id": "2", "content": "Python async programming", "score": 0.8},
        ]
        first = MagicMock()
        first.status_code = 200
        first.json.return_value = {"message": {"content": '{"score": 0.12}'}}
        second = MagicMock()
        second.status_code = 200
        second.json.return_value = {"message": {"content": '{"score": 0.91}'}}

        with patch("ksearch.knowledge.reranker.requests.post", side_effect=[first, second]) as mock_post:
            results = reranker.rerank("python async", docs, top_k=2)

        assert results[0]["id"] == "2"
        assert results[0]["rerank_score"] == pytest.approx(0.91)
        assert results[1]["rerank_score"] == pytest.approx(0.12)
        body = mock_post.call_args.kwargs["json"]
        assert body["model"] == "gemma4:e2b"
        assert body["format"] == "json"

    def test_rerank_truncates_content(self):
        """Content is truncated to max_content_length before sending to Ollama."""
        reranker = ReRanker(max_content_length=100, ollama_url="http://localhost:11434")
        long_content = "word " * 1000
        docs = [{"id": "1", "content": long_content, "score": 0.5}]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": '{"score": 0.5}'}}

        with patch("ksearch.knowledge.reranker.requests.post", return_value=mock_response) as mock_post:
            results = reranker.rerank("test", docs, top_k=1)

        assert len(results) == 1
        user_message = mock_post.call_args.kwargs["json"]["messages"][1]["content"]
        assert len(user_message) < len(long_content)

    def test_rerank_preserves_original_fields(self):
        """Re-ranking should not remove original document fields."""
        reranker = ReRanker(ollama_url="http://localhost:11434")
        docs = [
            {"id": "1", "content": "test", "score": 0.5, "extra": "value"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": '{"score": 0.7}'}}

        with patch("ksearch.knowledge.reranker.requests.post", return_value=mock_response):
            results = reranker.rerank("test", docs, top_k=1)

        assert results[0]["id"] == "1"
        assert results[0]["extra"] == "value"

    def test_rerank_respects_top_k(self):
        """Should return at most top_k results."""
        reranker = ReRanker(ollama_url="http://localhost:11434")
        docs = [{"id": str(i), "content": f"doc {i}", "score": 0.5} for i in range(20)]
        responses = []
        for i in range(20):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"message": {"content": f'{{"score": {20 - i}}}'}}
            responses.append(response)

        with patch("ksearch.knowledge.reranker.requests.post", side_effect=responses):
            results = reranker.rerank("test", docs, top_k=3)

        assert len(results) <= 3

    def test_rerank_handles_missing_content(self):
        """Should not crash on docs without content key."""
        reranker = ReRanker(ollama_url="http://localhost:11434")
        docs = [{"id": "1", "score": 0.5}]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": '{"score": 0.2}'}}

        with patch("ksearch.knowledge.reranker.requests.post", return_value=mock_response):
            results = reranker.rerank("test", docs, top_k=1)

        assert len(results) == 1
