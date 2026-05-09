# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`ksearch` is a Python CLI tool for research-oriented search combining local cache, semantic knowledge-base retrieval, and live web search. Built with Typer, it uses a cache-first strategy and an iterative kbase-first expansion loop.

## Development Commands

```bash
# Install dependencies
uv sync

# Install with optional extras
uv pip install -e ".[all]"

# Run the CLI
ksearch search "query"
kbase query "term" --top-k 5
ksearch optimize "query" --verbose

# Run tests
uv run pytest -q

# Run a single test file
uv run pytest tests/test_search.py -q

# Run a single test
uv run pytest tests/test_search.py::test_function_name -q

# Live E2E test (requires Ollama + SearXNG running)
bash tests/ollama_e2e_integration.sh

# Start Docker services
docker compose up -d
docker exec ksearch-ollama ollama pull nomic-embed-text
```

## Architecture

Two main user-facing flows:

**Standard search**: config -> local cache -> SearXNG web fetch -> extract/clean to Markdown -> cache -> render

**Iterative kbase-first search**: classify query -> kbase lookup -> score sufficiency -> web-expand if needed -> cache + kbase ingest -> repeat until thresholds met

**AI content optimization**: fetch results -> LLM quality evaluation -> identify gaps -> refinement query -> re-search -> repeat until confidence threshold -> synthesize final content

### Module Layout

Source is under `src/ksearch/`. The codebase is organized into domain packages with thin compatibility shims at the top level.

- **`web/`** - SearXNG client (`search_client.py`), URL skip rules (`url_policy.py`), Markdown cleanup (`cleaner.py`), main-body extraction with trafilatura+markitdown fallback (`extractor.py`)
- **`cache_layer/`** - SQLite metadata (`repository.py`), Markdown file storage (`store.py`), `CacheManager` facade (`service.py`)
- **`searching/`** - Standard cache-first + network fallback search orchestration (`service.py`)
- **`knowledge/`** - Content chunking (`chunking.py`), Chroma/Qdrant vector adapter (`vector_store.py`), ingest/search assembly (`service.py`)
- **`iterative_flow/`** - Query classification (`query.py`), sufficiency scoring (`sufficiency.py`), convergence boundaries (`convergence.py`), orchestration engine (`engine.py`)
- **`content_optimization/`** - Ollama chat client (`ollama_client.py`), prompt templates (`prompts.py`), LLM-based quality evaluator (`evaluator.py`), iterative content optimizer (`optimizer.py`)
- **`cli/`** - Typer command registration: `search.py`, `kbase.py`, `system.py`, `optimize.py`
- **`models.py`** - Shared data types: `CacheEntry`, `SearchResult`, `ResultEntry`, `KnowledgeBaseEntry`, `KnowledgeBaseSearchResult`, `QualityAssessment`, `OptimizationResult`
- **`config.py`** - Config loading with CLI > config file > defaults priority
- **`embeddings.py`** - Embedding model management with metadata validation

### Compatibility Shims

Top-level files (`cache.py`, `search.py`, `kbase.py`, `converter.py`, `content_opt.py`, `iterative.py`, `cli_search.py`, `cli_optimize.py`, etc.) are thin wrappers that delegate to the domain modules. Keep them thin; don't add logic here.

## Key Design Decisions

- **Embedding safety**: kbase stores embedding model/dimension in metadata. Switching embeddings requires an explicit `kbase reset` to avoid vector mismatches.
- **Extraction pipeline**: trafilatura for main-body extraction, markitdown as fallback.
- **Storage**: SQLite index + Markdown files for cache; Chroma embedded or Qdrant server for vector store.
- **Config path**: `~/.ksearch/config.json`
- **Content optimization**: uses Ollama `/api/chat` (not `/api/embeddings`) with `gemma4:e2b` for LLM generation. Disabled by default (`optimization_enabled: false`). Lazy imports avoid pulling in the module when not needed.

## External Services

Docker Compose provides: Qdrant (6333), SearXNG (48888), Ollama (11434), Open WebUI (3000, opt-in profile `webui`).
