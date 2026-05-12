"""Tests for embedding module."""

import pytest

from ksearch.embeddings import EmbeddingGenerator


class TestEmbeddingGenerator:
    def test_init_ollama(self):
        """Test Ollama mode initialization."""
        embedder = EmbeddingGenerator(mode="ollama")
        assert embedder.mode == "ollama"
        assert embedder.model == "nomic-embed-text"
        assert embedder.ollama_url == "http://localhost:11434"

    def test_init_sentence_transformers(self):
        """Test sentence-transformers mode initialization."""
        embedder = EmbeddingGenerator(mode="sentence-transformers")
        assert embedder.mode == "sentence-transformers"

    def test_init_simple(self):
        """Test simple mode initialization."""
        embedder = EmbeddingGenerator(mode="simple", dimension=768)
        assert embedder.mode == "simple"
        assert embedder.dimension == 768

    def test_simple_embed(self):
        """Test simple embedding generation."""
        embedder = EmbeddingGenerator(mode="simple", dimension=768)
        vector = embedder.embed("test text")

        assert len(vector) == 768
        assert isinstance(vector, list)
        assert all(isinstance(v, (int, float)) for v in vector)

    def test_simple_embed_normalization(self):
        """Test simple embedding is normalized."""
        embedder = EmbeddingGenerator(mode="simple", dimension=768)
        vector = embedder.embed("test text for normalization")

        # Check normalization: sum of squares should be ~1
        norm = sum(v * v for v in vector) ** 0.5
        assert 0.99 < norm < 1.01

    def test_embed_batch(self):
        """Test batch embedding."""
        embedder = EmbeddingGenerator(mode="simple", dimension=768)
        texts = ["text one", "text two", "text three"]
        vectors = embedder.embed_batch(texts)

        assert len(vectors) == 3
        for v in vectors:
            assert len(v) == 768

    def test_fallback_embed(self):
        """Test fallback embedding when primary fails."""
        embedder = EmbeddingGenerator(
            mode="ollama",
            ollama_url="http://invalid-url:99999"
        )
        # Should fall back to simple embedding
        vector = embedder._fallback_embed("test")

        assert len(vector) == 768

    def test_health_check(self):
        """Test health check functionality."""
        embedder = EmbeddingGenerator(mode="ollama")
        health = embedder.health_check()

        assert "mode" in health
        assert "model" in health
        assert health["simple"] == True  # Always available

    def test_health_check_ollama_unavailable(self):
        """Test health check when Ollama is unavailable."""
        embedder = EmbeddingGenerator(
            mode="ollama",
            ollama_url="http://invalid-url:99999"
        )
        health = embedder.health_check()

        assert health["ollama"] == False


class TestEmbeddingGeneratorIntegration:
    """Integration tests requiring actual services."""

    @pytest.mark.skip(reason="Requires running Ollama service")
    def test_ollama_embed_live(self):
        """Test live Ollama embedding."""
        embedder = EmbeddingGenerator(mode="ollama")
        vector = embedder.embed("test query")

        assert len(vector) == 768  # nomic-embed-text dimension

    @pytest.mark.skip(reason="Requires sentence-transformers package")
    def test_sentence_transformers_embed(self):
        """Test sentence-transformers embedding."""
        embedder = EmbeddingGenerator(
            mode="sentence-transformers",
            model="all-MiniLM-L6-v2"
        )
        vector = embedder.embed("test query")

        assert len(vector) == 384  # all-MiniLM-L6-v2 dimension


class TestGetEmbedder:
    def test_get_embedder_from_config(self):
        """Test embedder factory from config."""
        from ksearch.embeddings import get_embedder

        config = {
            "embedding_mode": "ollama",
            "embedding_model": "test-model",
            "ollama_url": "http://localhost:99999",
        }
        embedder = get_embedder(config)

        assert embedder.mode == "ollama"
        assert embedder.model == "test-model"
        assert embedder.ollama_url == "http://localhost:99999"


class TestKnowledgeEmbeddingFactory:
    def test_build_kbase_embedding_function_matches_requested_dimension(self):
        from ksearch.embeddings import build_kbase_embedding_function

        embed = build_kbase_embedding_function(
            embedding_mode="simple",
            embedding_model="nomic-embed-text",
            embedding_dimension=128,
            ollama_url="http://invalid-url:99999",
        )

        vector = embed("dimension compatible fallback")
        assert len(vector) == 128

    def test_build_kbase_embedding_function_dimension_mismatch_fails(self, monkeypatch):
        from ksearch.embeddings import build_kbase_embedding_function

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"embedding": [0.1, 0.2]}

        monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
        embed = build_kbase_embedding_function(
            embedding_model="nomic-embed-text",
            embedding_dimension=768,
            ollama_url="http://localhost:11434",
        )

        with pytest.raises(ValueError, match="dimension mismatch"):
            embed("hello")

    def test_build_kbase_embedding_function_non_200_fails(self, monkeypatch):
        from ksearch.embeddings import build_kbase_embedding_function

        class FakeResponse:
            status_code = 400
            text = "model does not support embeddings"

        monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
        embed = build_kbase_embedding_function(
            embedding_model="fredrezones55/qwen3.5-opus:9b",
            embedding_dimension=768,
            ollama_url="http://localhost:11434",
        )

        with pytest.raises(RuntimeError, match="does not support embeddings"):
            embed("hello")
