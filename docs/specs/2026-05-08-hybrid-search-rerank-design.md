# Hybrid Search + Re-ranking Design

## Goal

Improve ksearch's retrieval quality (both precision and recall) by adding BM25 keyword search alongside the existing dense vector search, merging results with Reciprocal Rank Fusion (RRF), and re-ranking with a cross-encoder model.

## Current State

- Pure cosine vector search via Chroma/Qdrant
- Fixed 1000-char chunking with basic sentence boundary detection
- No keyword/BM25 matching
- No re-ranking
- Single embedding per query, no query expansion

## Target State

```
Query
  ├─> BM25 Index (keyword matching) ──┐
  │                                    ├─ RRF Merge ─> Cross-Encoder Re-rank ─> Top-K Results
  └─> Vector Store (semantic match) ──┘
```

## Components

### 1. BM25 Index — `src/ksearch/knowledge/bm25_index.py` (new)

In-memory BM25 index using the `rank_bm25` library (~pure Python, no GPU).

```python
class BM25Index:
    def __init__(self):
        self._corpus: list[str] = []
        self._ids: list[str] = []
        self._metadatas: list[dict] = []
        self._bm25 = None

    def build(self, ids, documents, metadatas): ...
    def add(self, ids, documents, metadatas): ...
    def remove(self, ids: list[str]): ...
    def query(self, query: str, top_k: int = 20) -> list[BM25Result]: ...
```

**Design decisions:**
- Full rebuild on change (rank_bm25 doesn't support incremental updates). For collections under 50k chunks, rebuild takes <1s.
- Tokenization: whitespace + CJK bigrams. Handles English, Chinese, and mixed content without adding jieba.
- BM25Result is a lightweight dataclass: `id`, `score`, `metadata`.

### 2. Cross-Encoder Re-ranker — `src/ksearch/knowledge/reranker.py` (new)

Uses `sentence_transformers.CrossEncoder` (already available via existing dependency).

```python
class ReRanker:
    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # ~80MB

    def __init__(self, model_name=None, device="cpu"): ...
    def _ensure_model(self): ...  # lazy load
    def rerank(self, query, documents, top_k=5) -> list[dict]: ...
```

**Design decisions:**
- Lazy loading: model downloads on first use (~80MB), then cached on disk. No startup penalty.
- Truncate content to first 512 chars for scoring — key terms are usually near the top.
- Preserves original vector/RRF scores alongside `rerank_score`.
- Graceful fallback: if model download fails, returns unranked results.

### 3. Hybrid Query — `src/ksearch/knowledge/vector_store.py` (modified)

New method on `KnowledgeVectorStore`:

```python
def hybrid_query(
    self,
    *,
    query: str,
    embedding: list[float],
    top_k: int,
    bm25_top_k: int = 20,
    vector_top_k: int = 20,
    rrf_k: int = 60,
    filter_source: str = None,
) -> list:
```

**RRF formula:**
```
RRF_score(d) = Σ 1 / (k + rank_i(d))
```

where k=60 (standard smoothing constant), rank_i is document d's rank in list i.

Each retrieval method over-fetches (20 candidates), RRF merges, then we take the final top_k.

### 4. Pipeline Integration — `src/ksearch/knowledge/service.py` (modified)

```python
class KnowledgeService:
    def __init__(self, ..., reranker=None, use_hybrid=True, use_rerank=True):
        ...

    def search(self, query, top_k=5, ...):
        embedding = embed_fn(query)

        # Stage 1: Retrieval
        if self.use_hybrid:
            candidates = self.vector_store.hybrid_query(
                query=query, embedding=embedding, top_k=top_k * 4
            )
        else:
            candidates = self.vector_store.query(embedding=embedding, top_k=top_k * 4)

        # Stage 2: Re-ranking
        if self.use_rerank and self.reranker and candidates:
            results = self.reranker.rerank(query, candidates, top_k=top_k)
        else:
            results = candidates[:top_k]

        return results
```

**Graceful degradation:** Missing rank_bm25 → vector-only. Missing cross-encoder model → RRF-ranked results. Pipeline never breaks.

### 5. BM25 Index Lifecycle

| Event | Action |
|---|---|
| `KnowledgeVectorStore.__init__` | Scan all stored docs, build BM25 index |
| `KnowledgeVectorStore.add()` | Rebuild BM25 index after insert |
| `KnowledgeVectorStore.delete_entry()` | Rebuild BM25 index after delete |
| `KnowledgeVectorStore.clear()` | Clear BM25 index |
| `KnowledgeVectorStore.delete_by_file()` | Rebuild BM25 index after delete |

Index stays in sync with vector store. Callers don't need to know about BM25.

### 6. Tokenization

```python
def tokenize(text: str) -> list[str]:
    """Whitespace + CJK bigram tokenization."""
```

- English: whitespace split + lowercase
- Chinese: character bigrams (e.g., "搜索" → ["搜", "索", "搜索"])
- Mixed: handles transitions between CJK and Latin scripts
- No external CJK tokenizer dependency needed

### 7. Config & CLI

New config options in `~/.ksearch/config.json`:

```json
{
  "hybrid_search": true,
  "rerank_enabled": true,
  "rerank_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
  "bm25_top_k": 20,
  "vector_top_k": 20,
  "rrf_k": 60
}
```

New CLI flags:
- `--hybrid` / `--no-hybrid`
- `--rerank` / `--no-rerank`

Both default to ON.

### 8. Dependencies

| Package | Purpose | Size |
|---|---|---|
| `rank_bm25` (new) | BM25 Okapi implementation | ~5KB pure Python |
| `sentence-transformers` (existing) | CrossEncoder re-ranking | already installed |
| `chromadb` (existing) | Vector store | already installed |
| `qdrant-client` (existing) | Vector store | already installed |

### 9. Testing Strategy

| Test file | Coverage |
|---|---|
| `tests/test_bm25_index.py` | Build, query, add, remove with known documents |
| `tests/test_reranker.py` | Re-ranking order, empty input, fallback behavior |
| `tests/test_hybrid_query.py` | RRF merge correctness, filter_source pass-through |
| Existing tests | Must still pass — hybrid/rerank are additive |

## Scope

**In scope:**
- BM25 index module
- Cross-encoder re-ranker module
- Hybrid query method on vector store
- Pipeline wiring in KnowledgeService
- Config and CLI flags
- Unit tests

**Out of scope (future work):**
- Semantic/recursive chunking improvements
- Query expansion (HyDE, multi-query)
- Parent-child chunking
- MMR diversity filtering
- Sufficiency scoring upgrades for iterative flow

## Impact

- **Precision**: Cross-encoder re-ranking is the single biggest precision win in modern RAG. BM25 catches exact terminology that cosine similarity misses.
- **Recall**: Hybrid retrieval captures documents that either method alone would miss.
- **Backward compatibility**: All changes are additive. Existing tests, CLI, and config continue to work. Default ON with easy opt-out via flags/config.
- **Performance**: BM25 rebuild <1s for typical collections. Re-ranking ~100ms for 20 docs on CPU. Total overhead <2s per search.
