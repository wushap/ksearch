# ksearch

English | [简体中文](./README.zh-CN.md)

`ksearch` is a research-oriented CLI that combines local cache, semantic knowledge-base retrieval, and live web search in one workflow.

Instead of treating search as a stateless query, `ksearch` turns each run into reusable local knowledge:

- cache-first web search to avoid repeated fetching and conversion
- KB semantic retrieval on top of Chroma or Qdrant
- iterative KB-first search that expands to the web only when local knowledge is insufficient
- automatic web-to-Markdown conversion for reuse and later ingestion
- safer embedding model switching with KB metadata validation
- unified cache + KB statistics for observability

## Why ksearch

Most CLI search tools stop at "return search results".  
`ksearch` is built for an incremental knowledge loop:

1. search local cache and semantic KB first
2. fetch the web only when needed
3. clean and convert pages into Markdown
4. persist them locally
5. reuse them in future searches

This makes it useful for:

- personal research workflows
- local AI / agent memory pipelines
- note-backed search across mixed local and web knowledge
- repeatable technical investigation with growing retrieval quality

## Highlights

### KB-first Retrieval, Not Just Web Search

Use plain cached search, semantic KB retrieval, or iterative KB-first expansion depending on the task.

### Better Content Extraction

`ksearch` now prefers `trafilatura` for main-body extraction and falls back to `markitdown`, which improves article cleanliness and reduces boilerplate noise.

### Safer Embedding Changes

KB metadata stores embedding model and dimension. If you switch embedding settings, `ksearch` will block mismatched KB reuse and require an explicit reset.

### Unified Statistics

`ksearch stats` shows:

- cache entry count
- KB entry count
- total size
- keyword variety
- website/domain distribution
- search engine distribution
- KB source distribution
- embedding configuration

### Live E2E Validation

The repo includes a real Ollama + SearXNG end-to-end script for multilingual search validation.

## Installation

Base install:

```bash
uv sync
```

Optional extras:

```bash
uv pip install -e ".[qdrant]"
uv pip install -e ".[ollama]"
uv pip install -e ".[crawl4ai]"
uv pip install -e ".[all]"
```

## Quick Start

Basic search:

```bash
ksearch search "python asyncio"
```

Common variants:

```bash
ksearch search "rust async" --only-cache
ksearch search "agent memory" --no-cache
ksearch search "latest ai trends" --time-range week --max-results 5
ksearch search "python asyncio" --format path
ksearch search "vector database" --verbose
```

Unified statistics:

```bash
ksearch stats
```

## Common Workflows

### 1. Cache-first Search

```bash
ksearch search "python asyncio"
```

Use this for normal interactive search with local reuse.

### 2. KB-assisted Search

```bash
ksearch search "task cancellation" --kb chroma
```

Use this when you already have local notes or previously ingested material.

### 3. KB-only Semantic Retrieval

```bash
ksearch kb search "asyncio cancellation" --top-k 5
```

Use this when you want semantic retrieval without new web fetching.

### 4. Iterative KB-first Search

```bash
ksearch search "how does asyncio cancellation propagate" --kb chroma --iterative
```

Use this when local knowledge may be incomplete and you want controlled web expansion plus KB ingestion.

## Knowledge Base Commands

```bash
ksearch kb ingest ~/notes --source logseq --verbose
ksearch kb ingest ~/docs/readme.md --source manual
ksearch kb search "async programming best practices" --top-k 5
ksearch kb list
ksearch kb delete ~/old-notes/test.md
ksearch kb clear --confirm
ksearch kb reset --confirm --embedding-model nomic-embed-text --embedding-dimension 768
```

## Iterative Search

Iterative mode is a sufficiency-driven orchestration layer:

1. classify the query style
2. search the KB first
3. score result sufficiency
4. fetch the web only if needed
5. convert pages to Markdown
6. save to cache and ingest into the KB
7. stop when sufficiency or hard limits are reached

Notes:

- `--iterative` requires `--kb chroma` or `--kb qdrant`
- iterative mode keeps new web material in local cache for later reuse

## Embedding Safety

Embedding settings used by the KB must stay consistent with stored vectors.

- changing `embedding_model` or `embedding_dimension` invalidates old KB vectors
- KB metadata is persisted and checked on open
- mismatched configuration requires an explicit reset

Example:

```bash
ksearch config --embedding-model mxbai-embed-large --embedding-dimension 1024
ksearch kb reset --confirm --embedding-model mxbai-embed-large --embedding-dimension 1024
ksearch kb ingest ~/notes --source logseq
```

## Docker Services

```bash
docker compose up -d
docker exec ksearch-ollama ollama pull nomic-embed-text
```

Default endpoints:

- Qdrant: `http://localhost:6333`
- SearXNG: `http://localhost:48888`
- Ollama: `http://localhost:11434`
- Open WebUI: `http://localhost:3000` (when the profile is enabled)

## Configuration

Default config path:

```text
~/.ksearch/config.json
```

Example:

```json
{
  "searxng_url": "http://localhost:48888",
  "store_dir": "~/.ksearch/store",
  "index_db": "~/.ksearch/index.db",
  "max_results": 10,
  "timeout": 30,
  "format": "markdown",
  "time_range": "",
  "no_cache": false,
  "only_cache": false,
  "verbose": false,
  "kb_mode": "",
  "kb_dir": "~/.ksearch/kb",
  "kb_top_k": 5,
  "qdrant_url": "http://localhost:6333",
  "embedding_model": "nomic-embed-text",
  "embedding_dimension": 768,
  "ollama_url": "http://localhost:11434",
  "iterative_enabled": false,
  "max_iterations": 5,
  "max_time_seconds": 180,
  "fact_threshold": 0.7,
  "exploration_threshold": 0.4,
  "scoring_weights": {
    "vector": 0.4,
    "count": 0.3,
    "coverage": 0.3
  }
}
```

Priority order:

```text
CLI args > config file > defaults
```

## Important CLI Options

- `--format`, `-f`: `markdown` or `path`
- `--time-range`, `-t`: `day` / `week` / `month` / `year`
- `--max-results`, `-m`: limit web results
- `--searxng-url`, `-s`: set SearXNG endpoint
- `--store-dir`, `-d`: set cache directory
- `--index-db`: set SQLite index path
- `--timeout`: request timeout in seconds
- `--no-cache`: skip cache and force network
- `--only-cache`: return cached results only
- `--kb`: enable KB retrieval via `chroma`, `qdrant`, or `none`
- `--embedding-model`: choose KB embedding model
- `--embedding-dimension`: choose KB embedding dimension
- `--iterative`: enable iterative KB-first search
- `--verbose`, `-v`: print detailed execution info

## Testing

Unit and integration-style tests:

```bash
uv run pytest -q
```

Live Ollama + SearXNG E2E:

```bash
bash tests/ollama_e2e_integration.sh
```

This script expects:

- Ollama at `http://localhost:11434`
- SearXNG at `http://localhost:48888`
- `nomic-embed-text:latest` available in Ollama
- a negative-case non-embedding model, currently `fredrezones55/qwen3.5-opus:9b`

It creates a temporary KB and fixture notes, runs English, Chinese, and mixed-keyword flows, validates `--only-cache` and `--iterative`, and writes a Markdown report.
