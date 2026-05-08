"""BM25 index for hybrid keyword search alongside vector retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BM25Result:
    """A single BM25 retrieval hit."""

    id: str
    score: float
    content: str
    metadata: dict


def tokenize(text: str) -> list[str]:
    """Whitespace + CJK bigram tokenization.

    Handles English (whitespace split + lowercase), Chinese (character bigrams),
    and mixed content without external CJK tokenizer dependencies.
    """
    tokens: list[str] = []
    for word in text.lower().split():
        cjk_buf: list[str] = []
        latin_buf: list[str] = []
        for ch in word:
            if "一" <= ch <= "鿿":
                if latin_buf:
                    tokens.append("".join(latin_buf))
                    latin_buf = []
                cjk_buf.append(ch)
            else:
                if cjk_buf:
                    buf = "".join(cjk_buf)
                    for i in range(len(buf) - 1):
                        tokens.append(buf[i : i + 2])
                    tokens.append(buf)
                    cjk_buf = []
                latin_buf.append(ch)
        if cjk_buf:
            buf = "".join(cjk_buf)
            for i in range(len(buf) - 1):
                tokens.append(buf[i : i + 2])
            tokens.append(buf)
        if latin_buf:
            tokens.append("".join(latin_buf))
    return tokens


class BM25Index:
    """In-memory BM25 index over kbase documents.

    Uses ``rank_bm25.BM25Okapi`` under the hood.  The index is rebuilt from
    scratch on every mutation — acceptable for collections under 50k chunks.
    """

    def __init__(self) -> None:
        self._corpus: list[str] = []
        self._ids: list[str] = []
        self._contents: list[str] = []
        self._metadatas: list[dict] = []
        self._tokenized_corpus: list[list[str]] = []
        self._bm25 = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def build(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """Rebuild the entire index from *ids*, *documents*, and *metadatas*."""
        self._ids = list(ids)
        self._contents = list(documents)
        self._metadatas = list(metadatas) if metadatas else [{} for _ in ids]
        self._tokenized_corpus = [tokenize(doc) for doc in documents]
        self._bm25 = _build_bm25(self._tokenized_corpus)

    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """Add documents to the index (rebuilds internally)."""
        new_ids = self._ids + list(ids)
        new_docs = self._contents + list(documents)
        new_meta = self._metadatas + (
            list(metadatas) if metadatas else [{} for _ in ids]
        )
        self.build(new_ids, new_docs, new_meta)

    def remove(self, ids: list[str]) -> None:
        """Remove documents by *ids* (rebuilds without them)."""
        id_set = set(ids)
        keep = [i for i, doc_id in enumerate(self._ids) if doc_id not in id_set]
        self.build(
            [self._ids[i] for i in keep],
            [self._contents[i] for i in keep],
            [self._metadatas[i] for i in keep],
        )

    def query(self, query: str, top_k: int = 20) -> list[BM25Result]:
        """Return up to *top_k* results ranked by BM25 score."""
        if self._bm25 is None or not self._ids:
            return []

        tokenized_query = tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        ranked_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        results: list[BM25Result] = []
        for idx in ranked_indices:
            if scores[idx] <= 0:
                break
            results.append(
                BM25Result(
                    id=self._ids[idx],
                    score=float(scores[idx]),
                    content=self._contents[idx],
                    metadata=self._metadatas[idx],
                )
            )
        return results

    @property
    def size(self) -> int:
        return len(self._ids)

    def clear(self) -> None:
        self._ids.clear()
        self._contents.clear()
        self._metadatas.clear()
        self._tokenized_corpus.clear()
        self._bm25 = None


def _build_bm25(tokenized_corpus: list[list[str]]):
    """Build a BM25Okapi instance, or return None for empty corpus."""
    if not tokenized_corpus:
        return None
    from rank_bm25 import BM25Okapi

    return BM25Okapi(tokenized_corpus)


__all__ = ["BM25Index", "BM25Result", "tokenize"]
