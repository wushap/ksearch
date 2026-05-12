"""Tests for shared CLI helpers."""

from unittest.mock import patch

import pytest

from ksearch.cli_common import build_kbase, resolve_search_runtime_config


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


def test_build_kbase_rejects_none_mode():
    with pytest.raises(ValueError, match="kbase_mode"):
        build_kbase({"kbase_mode": "none"})


def test_resolve_search_runtime_config_auto_disables_unavailable_default_features(monkeypatch):
    monkeypatch.setattr("ksearch.cli_common._probe_kbase_backend", lambda config: (True, None))
    monkeypatch.setattr("ksearch.cli_common._probe_kbase_embedding", lambda config: (False, "ollama unavailable"))
    monkeypatch.setattr("ksearch.cli_common._probe_ollama_chat_model", lambda *args, **kwargs: (False, "model unavailable"))

    effective, degradations = resolve_search_runtime_config(
        {
            "kbase_mode": "chroma",
            "iterative_enabled": True,
            "rerank_enabled": True,
            "optimization_enabled": True,
            "rerank_model": "gemma4:e2b",
            "optimization_model": "gemma4:e2b",
            "ollama_url": "http://localhost:11434",
        },
        explicit_flags=set(),
    )

    assert effective["kbase_mode"] == "none"
    assert effective["iterative_enabled"] is False
    assert effective["rerank_enabled"] is False
    assert effective["optimization_enabled"] is False
    assert degradations


def test_resolve_search_runtime_config_rejects_explicit_iterative_when_kbase_unavailable(monkeypatch):
    monkeypatch.setattr("ksearch.cli_common._probe_kbase_backend", lambda config: (True, None))
    monkeypatch.setattr("ksearch.cli_common._probe_kbase_embedding", lambda config: (False, "ollama unavailable"))

    with pytest.raises(RuntimeError, match="iterative"):
        resolve_search_runtime_config(
            {
                "kbase_mode": "chroma",
                "iterative_enabled": True,
                "rerank_enabled": False,
                "optimization_enabled": False,
                "ollama_url": "http://localhost:11434",
            },
            explicit_flags={"iterative"},
        )


def test_resolve_search_runtime_config_rejects_explicit_rerank_when_kbase_unavailable(monkeypatch):
    monkeypatch.setattr("ksearch.cli_common._probe_kbase_backend", lambda config: (False, "backend unavailable"))
    monkeypatch.setattr("ksearch.cli_common._probe_kbase_embedding", lambda config: (True, None))

    with pytest.raises(RuntimeError, match="rerank"):
        resolve_search_runtime_config(
            {
                "kbase_mode": "chroma",
                "iterative_enabled": False,
                "rerank_enabled": True,
                "optimization_enabled": False,
                "ollama_url": "http://localhost:11434",
            },
            explicit_flags={"rerank"},
        )
