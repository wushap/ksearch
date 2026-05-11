# kbase

English | [简体中文](./README.zh-CN.md)

`ksearch` is a research-oriented CLI that combines local cache, semantic knowledge-base retrieval, and live web search in one workflow.

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

`ksearch stats` shows:

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

### AI Content Optimization

`ksearch optimize` uses a local LLM via Ollama to iteratively evaluate and refine search results. The optimization loop:

1. fetch search results
2. evaluate content quality with LLM
3. identify information gaps
4. generate targeted follow-up queries
5. re-search and merge new results
6. repeat until confidence threshold or max iterations reached
7. synthesize final optimized content

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

### 2. kbase-assisted Search

```bash
ksearch search "task cancellation" --kbase chroma
```

Use this when you already have local notes or previously ingested material.

### 3. kbase-only Semantic Retrieval

```bash
kbase query "asyncio cancellation" --top-k 5
```

Use this when you want semantic retrieval without new web fetching.

### 4. Iterative kbase-first Search

```bash
ksearch search "how does asyncio cancellation propagate" --kbase chroma --iterative
```

Use this when local knowledge may be incomplete and you want controlled web expansion plus kbase ingestion.

### 5. AI Content Optimization

```bash
ksearch optimize "python asyncio best practices"
```

Uses a local LLM (via Ollama) to iteratively evaluate search result quality, identify gaps, and refine results until a confidence threshold is met. Requires Ollama with `gemma4:e2b` pulled.

```bash
# Optimize with custom parameters
ksearch optimize "rust async runtime" --model gemma4:e2b --max-iterations 5 --confidence 0.9

# Optimize a local file
ksearch optimize "summarize this" --file ./notes.md

# Verbose output showing refinement iterations
ksearch optimize "distributed systems" --verbose
```

To pull the required model:

```bash
ollama pull gemma4:e2b
```

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
ksearch config --embedding-model mxbai-embed-large --embedding-dimension 1024
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
~/.ksearch/config.json
```

Repository example:

```text
./config.example.json
```

Copy it to `~/.ksearch/config.json` and adjust only the keys you need.

Default example:

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
  "only_kbase": false,
  "verbose": false,
  "kbase_mode": "chroma",
  "kbase_dir": "~/.ksearch/kbase",
  "kbase_top_k": 5,
  "qdrant_url": "http://localhost:6333",
  "embedding_mode": "ollama",
  "embedding_model": "nomic-embed-text",
  "embedding_dimension": 768,
  "ollama_url": "http://localhost:11434",
  "iterative_enabled": true,
  "max_iterations": 5,
  "max_time_seconds": 180,
  "fact_threshold": 0.7,
  "exploration_threshold": 0.4,
  "scoring_weights": {
    "vector": 0.4,
    "count": 0.3,
    "coverage": 0.3
  },
  "hybrid_search": true,
  "rerank_enabled": true,
  "rerank_model": "gemma4:e2b",
  "bm25_top_k": 20,
  "vector_top_k": 20,
  "rrf_k": 60,
  "optimization_enabled": true,
  "optimization_model": "gemma4:e2b",
  "optimization_max_iterations": 3,
  "optimization_confidence_threshold": 0.8,
  "optimization_max_time_seconds": 120,
  "optimization_temperature": 0.3
}
```

All keys in `~/.ksearch/config.json` are optional. You can keep a sparse file and only override the values you care about; omitted keys fall back to built-in defaults.

### Configuration Reference

#### Search and Output

| Key | Default | Allowed / Type | What it does |
| --- | --- | --- | --- |
| `searxng_url` | `http://localhost:48888` | URL string | Base URL for SearXNG web search requests. |
| `store_dir` | `~/.ksearch/store` | Path string | Directory where converted page content is stored on disk. |
| `index_db` | `~/.ksearch/index.db` | Path string | SQLite index used for cache metadata and cache lookup. |
| `max_results` | `10` | Integer >= 1 | Max number of web results requested per search iteration. |
| `timeout` | `30` | Integer seconds | HTTP timeout for SearXNG, page fetch, and conversion work. |
| `format` | `markdown` | `markdown`, `path` | CLI output format. `markdown` prints structured content, `path` prints cached file paths only. |
| `time_range` | `""` | `""`, `day`, `week`, `month`, `year` | Optional freshness filter for web search and partial-cache lookup. Empty string disables the filter. |
| `no_cache` | `false` | Boolean | Skip cache reads and force web retrieval. New results can still be written into cache. |
| `only_cache` | `false` | Boolean | Return cache matches only. This disables network search and also disables iterative kbase-first flow. |
| `only_kbase` | `false` | Boolean | Search only the kbase and skip web search. Useful for fully local retrieval. |
| `verbose` | `false` | Boolean | Print extra CLI progress and backend status messages. |

#### Knowledge Base

| Key | Default | Allowed / Type | What it does |
| --- | --- | --- | --- |
| `kbase_mode` | `chroma` | `chroma`, `qdrant`, `none` | Selects the kbase backend. `none` disables kbase retrieval. Iterative search requires `chroma` or `qdrant`. |
| `kbase_dir` | `~/.ksearch/kbase` | Path string | Persistent storage directory for local kbase data and metadata. |
| `kbase_top_k` | `5` | Integer >= 1 | Number of kbase hits returned and used during iterative sufficiency checks. |
| `qdrant_url` | `http://localhost:6333` | URL string | Qdrant server address. Used only when `kbase_mode` is `qdrant`. |

#### Embeddings

| Key | Default | Allowed / Type | What it does |
| --- | --- | --- | --- |
| `embedding_mode` | `ollama` | `ollama`, `sentence-transformers`, `simple` | Preferred embedding backend for embedding helper paths. Keep `ollama` for the normal local setup. |
| `embedding_model` | `nomic-embed-text` | Model name string | Embedding model name used by the kbase. Changing it for an existing kbase requires rebuilding or resetting that kbase. |
| `embedding_dimension` | `768` | Integer >= 1 | Expected embedding vector length. Must match the actual model output dimension stored in the kbase. |
| `ollama_url` | `http://localhost:11434` | URL string | Ollama server address for embeddings, reranking, and content optimization. |

#### Iterative Search

| Key | Default | Allowed / Type | What it does |
| --- | --- | --- | --- |
| `iterative_enabled` | `true` | Boolean | Enables kbase-first iterative search. The engine checks kbase sufficiency first, then falls back to web search only when needed. |
| `max_iterations` | `5` | Integer >= 1 | Upper bound on iterative search rounds after the initial kbase pass. |
| `max_time_seconds` | `180` | Integer seconds | Time budget for one iterative search request. |
| `fact_threshold` | `0.7` | Float | Sufficiency threshold for fact-style queries that need stronger evidence. |
| `exploration_threshold` | `0.4` | Float | Sufficiency threshold for broader exploratory queries. |
| `scoring_weights` | `{"vector": 0.4, "count": 0.3, "coverage": 0.3}` | Object with `vector`, `count`, `coverage` floats | Weights used by the sufficiency scorer to balance semantic match quality, result count, and content coverage. |

#### Hybrid Retrieval and Re-ranking

| Key | Default | Allowed / Type | What it does |
| --- | --- | --- | --- |
| `hybrid_search` | `true` | Boolean | Enables BM25 + vector hybrid retrieval inside the kbase. |
| `rerank_enabled` | `true` | Boolean | Enables the Ollama reranker on top of retrieved kbase candidates. |
| `rerank_model` | `gemma4:e2b` | Model name string | Ollama model name used for reranking candidate passages. |
| `bm25_top_k` | `20` | Integer >= 1 | Number of lexical BM25 candidates considered during hybrid retrieval. |
| `vector_top_k` | `20` | Integer >= 1 | Number of vector-search candidates considered during hybrid retrieval. |
| `rrf_k` | `60` | Integer >= 1 | Reciprocal Rank Fusion constant used when combining BM25 and vector ranks. |

#### Content Optimization

| Key | Default | Allowed / Type | What it does |
| --- | --- | --- | --- |
| `optimization_enabled` | `true` | Boolean | Enables post-processing optimization for iterative search results. |
| `optimization_model` | `gemma4:e2b` | Model name string | Ollama model name used by the optimization/evaluation loop. |
| `optimization_max_iterations` | `3` | Integer >= 1 | Max number of refinement rounds for content optimization. |
| `optimization_confidence_threshold` | `0.8` | Float from `0.0` to `1.0` | Stops refinement once the evaluator reaches this confidence threshold. |
| `optimization_max_time_seconds` | `120` | Integer seconds | Time budget for a single optimization request. |
| `optimization_temperature` | `0.3` | Float >= `0.0` | Sampling temperature used for optimization model responses. |

#### Legacy Aliases

Older config files are still accepted with these compatibility keys:

| Legacy key | Current key |
| --- | --- |
| `kb_mode` | `kbase_mode` |
| `kb_dir` | `kbase_dir` |
| `kb_top_k` | `kbase_top_k` |
| `only_kb` | `only_kbase` |

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

### `ksearch optimize` Options

- `--model`: Ollama model for optimization (default: `gemma4:e2b`)
- `--max-iterations`, `-i`: max refinement iterations (default: 3)
- `--confidence`, `-c`: quality confidence threshold (default: 0.8)
- `--temperature`: LLM temperature (default: 0.3)
- `--file`: optimize a local file instead of searching
- `--verbose`, `-v`: show refinement iteration details

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
