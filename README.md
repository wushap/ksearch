# kbase

English | [简体中文](./README.zh-CN.md)

`kbase` is a research-oriented CLI that combines local cache, semantic knowledge-base retrieval, and live web search in one workflow.

Instead of treating search as a stateless query, `kbase` turns each run into reusable local knowledge:

- cache-first web search to avoid repeated fetching and conversion
- kbase semantic retrieval on top of Chroma or Qdrant
- iterative kbase-first search that expands to the web only when local knowledge is insufficient
- automatic web-to-Markdown conversion for reuse and later ingestion
- safer embedding model switching with kbase metadata validation
- unified cache + kbase statistics for observability

## Why kbase

Most CLI search tools stop at "return search results".  
`kbase` is built for an incremental knowledge loop:

1. search local cache and semantic kbase first
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

### kbase-first Retrieval, Not Just Web Search

Use plain cached search, semantic kbase retrieval, or iterative kbase-first expansion depending on the task.

### Better Content Extraction

`kbase` now prefers `trafilatura` for main-body extraction and falls back to `markitdown`, which improves article cleanliness and reduces boilerplate noise.

### Safer Embedding Changes

kbase metadata stores embedding model and dimension. If you switch embedding settings, `kbase` will block mismatched kbase reuse and require an explicit reset.

### Unified Statistics

`kbase stats` shows:

- cache entry count
- kbase entry count
- total size
- keyword variety
- website/domain distribution
- search engine distribution
- kbase source distribution
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
kbase search "python asyncio"
```

Common variants:

```bash
kbase search "rust async" --only-cache
kbase search "agent memory" --no-cache
kbase search "latest ai trends" --time-range week --max-results 5
kbase search "python asyncio" --format path
kbase search "vector database" --verbose
```

Unified statistics:

```bash
kbase stats
```

## Common Workflows

### 1. Cache-first Search

```bash
kbase search "python asyncio"
```

Use this for normal interactive search with local reuse.

### 2. kbase-assisted Search

```bash
kbase search "task cancellation" --kbase chroma
```

Use this when you already have local notes or previously ingested material.

### 3. kbase-only Semantic Retrieval

```bash
kbase query "asyncio cancellation" --top-k 5
```

Use this when you want semantic retrieval without new web fetching.

### 4. Iterative kbase-first Search

```bash
kbase search "how does asyncio cancellation propagate" --kbase chroma --iterative
```

Use this when local knowledge may be incomplete and you want controlled web expansion plus kbase ingestion.

## Knowledge Base Commands

```bash
kbase ingest ~/notes --source logseq --verbose
kbase ingest ~/docs/readme.md --source manual
kbase query "async programming best practices" --top-k 5
kbase list
kbase delete ~/old-notes/test.md
kbase clear --confirm
kbase reset --confirm --embedding-model nomic-embed-text --embedding-dimension 768
```

## Iterative Search

Iterative mode is a sufficiency-driven orchestration layer:

1. classify the query style
2. search the kbase first
3. score result sufficiency
4. fetch the web only if needed
5. convert pages to Markdown
6. save to cache and ingest into the kbase
7. stop when sufficiency or hard limits are reached

Notes:

- `--iterative` requires `--kbase chroma` or `--kbase qdrant`
- iterative mode keeps new web material in local cache for later reuse

## Embedding Safety

Embedding settings used by the kbase must stay consistent with stored vectors.

- changing `embedding_model` or `embedding_dimension` invalidates old kbase vectors
- kbase metadata is persisted and checked on open
- mismatched configuration requires an explicit reset

Example:

```bash
kbase config --embedding-model mxbai-embed-large --embedding-dimension 1024
kbase reset --confirm --embedding-model mxbai-embed-large --embedding-dimension 1024
kbase ingest ~/notes --source logseq
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
~/.kbase/config.json
```

Example:

```json
{
  "searxng_url": "http://localhost:48888",
  "store_dir": "~/.kbase/store",
  "index_db": "~/.kbase/index.db",
  "max_results": 10,
  "timeout": 30,
  "format": "markdown",
  "time_range": "",
  "no_cache": false,
  "only_cache": false,
  "verbose": false,
  "kbase_mode": "",
  "kbase_dir": "~/.kbase/kbase",
  "kbase_top_k": 5,
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
- `--kbase`: enable kbase retrieval via `chroma`, `qdrant`, or `none`
- `--embedding-model`: choose kbase embedding model
- `--embedding-dimension`: choose kbase embedding dimension
- `--iterative`: enable iterative kbase-first search
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

It creates a temporary kbase and fixture notes, runs English, Chinese, and mixed-keyword flows, validates `--only-cache` and `--iterative`, and writes a Markdown report.
