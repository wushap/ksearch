"""Cross-encoder re-ranking for search results."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ReRanker:
    """Re-ranks search results using a cross-encoder model.

    The model is lazy-loaded on first use to avoid startup cost.
    Uses ``sentence_transformers.CrossEncoder`` (available via existing dep).
    """

    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "cpu",
        max_content_length: int = 512,
    ):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device
        self.max_content_length = max_content_length
        self._model = None

    def _ensure_model(self) -> bool:
        """Lazy-load the cross-encoder model. Returns True if available."""
        if self._model is not None:
            return True
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self.device)
            return True
        except Exception as exc:
            logger.warning("Failed to load cross-encoder model '%s': %s", self.model_name, exc)
            return False

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Re-rank *documents* by cross-encoder relevance to *query*.

        Each document dict must have a ``"content"`` key.  The method adds a
        ``"rerank_score"`` key to each returned document and sorts by it.

        If the model cannot be loaded, the original *documents* are returned
        unchanged (truncated to *top_k*).
        """
        if not documents:
            return []

        if not self._ensure_model():
            return documents[:top_k]

        pairs = [
            (query, doc.get("content", "")[: self.max_content_length])
            for doc in documents
        ]
        scores = self._model.predict(pairs)

        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        reranked = sorted(documents, key=lambda d: d.get("rerank_score", 0.0), reverse=True)
        return reranked[:top_k]


__all__ = ["ReRanker"]
