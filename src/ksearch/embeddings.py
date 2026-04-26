"""Embedding generation module.

Supports multiple embedding backends:
1. Ollama (local LLM server) - Primary for production
2. sentence-transformers (local Python) - Fallback
3. Simple hash-based - Last resort for testing

Usage:
    embedder = EmbeddingGenerator(mode="ollama")
    vector = embedder.embed("some text")

    # Batch embedding
    vectors = embedder.embed_batch(["text1", "text2"])
"""

import hashlib
import logging
from typing import Optional

from ksearch.config import expand_path

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for text."""

    def __init__(
        self,
        mode: str = "ollama",
        model: str = "nomic-embed-text",
        ollama_url: str = "http://localhost:11434",
        dimension: int = 768,
    ):
        """Initialize embedding generator.

        Args:
            mode: "ollama", "sentence-transformers", or "simple"
            model: Model name (Ollama model or sentence-transformers model)
            ollama_url: Ollama server URL
            dimension: Output dimension (for simple mode)
        """
        self.mode = mode
        self.model = model
        self.ollama_url = ollama_url
        self.dimension = dimension
        self._st_model = None  # sentence-transformers model cache

    def embed(self, text: str) -> list[float]:
        """Generate embedding for single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        if self.mode == "ollama":
            return self._embed_ollama(text)
        elif self.mode == "sentence-transformers":
            return self._embed_st(text)
        elif self.mode == "simple":
            return self._embed_simple(text)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        return [self.embed(t) for t in texts]

    def _embed_ollama(self, text: str) -> list[float]:
        """Generate embedding via Ollama API."""
        try:
            import requests
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60,
            )
            if response.status_code == 200:
                return response.json()["embedding"]
            else:
                logger.warning(f"Ollama returned {response.status_code}: {response.text}")
                return self._fallback_embed(text)
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama not available, using fallback")
            return self._fallback_embed(text)
        except Exception as e:
            logger.warning(f"Ollama error: {e}")
            return self._fallback_embed(text)

    def _embed_st(self, text: str) -> list[float]:
        """Generate embedding via sentence-transformers."""
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer(self.model)
            except ImportError:
                logger.warning("sentence-transformers not installed")
                return self._fallback_embed(text)

        return self._st_model.encode(text).tolist()

    def _embed_simple(self, text: str) -> list[float]:
        """Simple hash-based embedding for testing."""
        words = text.lower().split()
        vec = [0.0] * self.dimension
        for word in words:
            hash_val = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
            idx = hash_val % self.dimension
            vec[idx] += 1.0
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def _fallback_embed(self, text: str) -> list[float]:
        """Fallback embedding when primary fails."""
        # Try sentence-transformers first
        try:
            return self._embed_st(text)
        except Exception:
            pass

        # Fall back to simple
        logger.warning("All embedding backends failed, using simple hash")
        return self._embed_simple(text)

    def health_check(self) -> dict:
        """Check health of embedding backends."""
        result = {
            "mode": self.mode,
            "model": self.model,
            "ollama": False,
            "sentence_transformers": False,
            "simple": True,  # Always works
        }

        # Check Ollama
        try:
            import requests
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name") for m in models]
                result["ollama"] = True
                result["ollama_models"] = model_names
                result["model_available"] = self.model in model_names or any(
                    m.startswith(self.model) for m in model_names
                )
        except Exception as e:
            result["ollama_error"] = str(e)

        # Check sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            result["sentence_transformers"] = True
        except ImportError:
            pass

        return result


def get_embedder(config: dict) -> EmbeddingGenerator:
    """Get embedding generator from config."""
    return EmbeddingGenerator(
        mode=config.get("embedding_mode", "ollama"),
        model=config.get("embedding_model", "nomic-embed-text"),
        ollama_url=config.get("ollama_url", "http://localhost:11434"),
    )