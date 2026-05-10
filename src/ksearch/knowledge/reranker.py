"""Ollama-backed re-ranking for search results."""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class ReRanker:
    """Re-ranks search results using an Ollama-hosted reranker model."""

    DEFAULT_MODEL = "gemma4:e2b"

    def __init__(
        self,
        model_name: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        timeout: int = 180,
        max_content_length: int = 512,
    ):
        self.model_name = model_name or self.DEFAULT_MODEL
        self.ollama_url = ollama_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.max_content_length = max_content_length

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """Re-rank *documents* by Ollama relevance scores for *query*.

        Each document dict must have a ``"content"`` key.  The method adds a
        ``"rerank_score"`` key to each returned document and sorts by it.

        If the reranker request fails, the original *documents* are returned
        unchanged (truncated to *top_k*).
        """
        if not documents:
            return []

        try:
            score_map = {
                index: self._score_document(query, doc.get("content", ""))
                for index, doc in enumerate(documents)
            }
        except Exception as exc:
            logger.warning("Failed to rerank with Ollama model '%s': %s", self.model_name, exc)
            return documents[:top_k]

        for index, doc in enumerate(documents):
            doc["rerank_score"] = float(score_map.get(index, doc.get("score", 0.0)))

        reranked = sorted(documents, key=lambda d: d.get("rerank_score", 0.0), reverse=True)
        return reranked[:top_k]

    def _score_document(self, query: str, content: str) -> float:
        response = requests.post(
            f"{self.ollama_url}/api/chat",
            json=self._build_request_body(query, content),
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Ollama returned {response.status_code}: {response.text}")

        try:
            raw = response.json()["message"]["content"]
            data = json.loads(raw)
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unexpected Ollama response format: {exc}") from exc

        try:
            return float(data["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Ollama reranker response did not contain a usable score") from exc

    def _build_request_body(self, query: str, content: str) -> dict:
        return {
            "model": self.model_name,
            "messages": self._build_messages(query, content),
            "stream": False,
            "format": "json",
            "options": {"temperature": self.temperature},
        }

    def _build_messages(self, query: str, content: str) -> list[dict[str, str]]:
        system = (
            "You are a relevance scorer for retrieval ranking. "
            "Given a search query and one candidate passage, return JSON only in the form "
            '{"score": 0.0}. Use a score from 0.0 to 1.0 where higher means more relevant.'
        )
        user = (
            f"Query: {query}\n\n"
            f"Document: {content[: self.max_content_length]}\n\n"
            'Return exactly {"score": <number>}.'
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


__all__ = ["ReRanker"]
