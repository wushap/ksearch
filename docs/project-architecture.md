# Project Architecture

## Overview

`ksearch` is a research-oriented CLI that combines:

- local Markdown cache
- semantic knowledge-base retrieval
- live web search
- iterative kbase-first expansion

The current codebase is organized around domain boundaries while preserving compatibility with older module entrypoints.

## High-Level Flow

There are three main user-facing flows:

1. Standard search
2. Iterative kbase-first search
3. AI content optimization

Standard search:

1. Read config and CLI options
2. Search local cache first
3. Query SearXNG when cache is insufficient
4. Extract main webpage content
5. Convert and clean content into Markdown
6. Save results into local cache
7. Render results for CLI output

Iterative search:

1. Classify the query as fact-style or exploration-style
2. Search kbase first
3. Score result sufficiency
4. Expand to web only when local knowledge is insufficient
5. Save extracted content to cache
6. Ingest web content into kbase
7. Re-check sufficiency and convergence
8. Stop when thresholds or hard limits are met

AI content optimization:

1. Fetch search results (via standard or iterative search)
2. Aggregate content from results
3. Evaluate content quality with LLM (returns action/confidence/gaps)
4. If gaps remain and confidence below threshold, generate refinement query
5. Re-search with refinement query, merge new results
6. Repeat evaluation until confidence threshold or max iterations reached
7. Synthesize final optimized content via LLM

## Module Layout

### `src/ksearch/web/`

Responsible for web retrieval and page content extraction.

- `src/ksearch/web/search_client.py`: SearXNG API client
- `src/ksearch/web/url_policy.py`: URL skip rules
- `src/ksearch/web/cleaner.py`: Markdown noise cleanup
- `src/ksearch/web/extractor.py`: main-body extraction and fallback conversion

### `src/ksearch/cache_layer/`

Responsible for cache persistence.

- `src/ksearch/cache_layer/repository.py`: SQLite metadata storage and queries
- `src/ksearch/cache_layer/store.py`: Markdown file storage
- `src/ksearch/cache_layer/service.py`: `CacheManager` compatibility facade

### `src/ksearch/searching/`

Responsible for standard search orchestration.

- `src/ksearch/searching/service.py`: cache-first + network fallback search flow

### `src/ksearch/knowledge/`

Responsible for knowledge-base internals.

- `src/ksearch/knowledge/chunking.py`: content chunking
- `src/ksearch/knowledge/vector_store.py`: Chroma/Qdrant adapter
- `src/ksearch/knowledge/service.py`: ingest/search service assembly

### `src/ksearch/iterative_flow/`

Responsible for iterative search policy and orchestration.

- `src/ksearch/iterative_flow/query.py`: query classification
- `src/ksearch/iterative_flow/sufficiency.py`: sufficiency scoring
- `src/ksearch/iterative_flow/convergence.py`: convergence and iteration boundaries
- `src/ksearch/iterative_flow/engine.py`: iterative orchestration

### `src/ksearch/cli/`

Responsible for CLI command registration.

- `src/ksearch/cli/search.py`: top-level `search`
- `src/ksearch/cli/kbase.py`: `kbase` subcommands
- `src/ksearch/cli/system.py`: `stats`, `config`, `health`
- `src/ksearch/cli/optimize.py`: `optimize` command for AI content optimization

### `src/ksearch/content_optimization/`

Responsible for AI-driven content optimization using LLMs via Ollama.

- `src/ksearch/content_optimization/ollama_client.py`: Ollama `/api/chat` client for LLM generation (distinct from embedding `/api/embeddings`)
- `src/ksearch/content_optimization/prompts.py`: prompt templates for evaluation, refinement query generation, and content synthesis
- `src/ksearch/content_optimization/evaluator.py`: LLM-based quality assessment returning structured `QualityAssessment`
- `src/ksearch/content_optimization/optimizer.py`: iterative refinement orchestrator — evaluate → identify gaps → re-search → repeat

## Compatibility Layer

Older top-level modules are still present as compatibility shims so existing imports continue to work:

- `src/ksearch/converter.py`
- `src/ksearch/cache.py`
- `src/ksearch/search.py`
- `src/ksearch/kbase.py`
- `src/ksearch/content_opt.py` (content optimization)
- `src/ksearch/iterative_query.py`
- `src/ksearch/iterative_sufficiency.py`
- `src/ksearch/iterative_convergence.py`
- `src/ksearch/iterative_engine.py`
- `src/ksearch/cli_search.py`
- `src/ksearch/cli_kbase.py`
- `src/ksearch/cli_optimize.py` (optimize command registration)
- `src/ksearch/cli_system.py`

These files should stay thin and delegate to the new domain modules.

## Core Data Boundaries

Key shared models remain in:

- `src/ksearch/models.py`

Important types:

- `CacheEntry`
- `SearchResult`
- `ResultEntry`
- `KnowledgeBaseEntry`
- `KnowledgeBaseSearchResult`
- `QualityAssessment` (content optimization quality evaluation result)
- `OptimizationResult` (content optimization pipeline result)

## Storage Boundaries

Cache storage:

- SQLite index for cache metadata
- Markdown files for cached page content

Knowledge-base storage:

- Chroma embedded persistence or Qdrant server backend
- persisted embedding metadata for compatibility checks

## Design Intent

This architecture aims to keep:

- orchestration logic separate from persistence details
- extraction logic separate from search orchestration
- vector-store details separate from kbase public behavior
- CLI registration separate from business logic

The result is a codebase that is easier to test, refactor, and extend without breaking old import surfaces.
