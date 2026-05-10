"""Tests for shared CLI helpers."""

from unittest.mock import patch

from ksearch.cli_common import build_kbase


def test_build_kbase_passes_ollama_url_to_reranker():
    captured = {}

    class FakeKnowledgeBase:
        def __init__(self, **kwargs):
            captured["knowledge_base_kwargs"] = kwargs

    class FakeReRanker:
        def __init__(self, **kwargs):
            captured["reranker_kwargs"] = kwargs

    config = {
        "kbase_mode": "chroma",
        "kbase_dir": "/tmp/kbase",
        "embedding_model": "nomic-embed-text",
        "embedding_dimension": 768,
        "ollama_url": "http://ollama.internal:11434",
        "rerank_enabled": True,
        "rerank_model": "gemma4:e2b",
        "hybrid_search": True,
    }

    with patch("ksearch.cli_common.KnowledgeBase", FakeKnowledgeBase):
        with patch("ksearch.knowledge.reranker.ReRanker", FakeReRanker):
            build_kbase(config)

    assert captured["reranker_kwargs"]["model_name"] == "gemma4:e2b"
    assert captured["reranker_kwargs"]["ollama_url"] == "http://ollama.internal:11434"
    assert captured["knowledge_base_kwargs"]["reranker"] is not None
