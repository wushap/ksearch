# ksearch Modularization Design

## Goal

Refactor the current `ksearch` package into clearer domain-oriented modules while preserving all external behavior:

- CLI commands and flags remain compatible
- Output format remains compatible
- Cache directory layout remains compatible
- SQLite cache schema remains compatible
- Existing kbase storage layout remains compatible

This refactor is structural, not product-facing. It is intended to reduce coupling, shrink oversized modules, and make future changes safer.

## Current Problems

The current package already has some separation, but several modules still mix multiple responsibilities:

- `src/ksearch/converter.py` mixes network fetch, extraction strategy, fallback selection, timeout handling, and content cleaning
- `src/ksearch/cache.py` mixes file storage, SQLite persistence, cache querying, and stats
- `src/ksearch/search.py` mixes orchestration, URL policy, extraction triggering, and persistence wiring
- `src/ksearch/kbase.py` is the largest module and mixes chunking, embeddings, vector store concerns, ingestion, querying, metadata handling, and stats
- `src/ksearch/iterative_engine.py` is mostly orchestration already, but it still depends on low-level services directly

These boundaries make behavior harder to reason about and increase the risk of accidental regressions when changing one part of the system.

## Non-Goals

This refactor does not:

- change CLI semantics
- change the search result rendering format
- change cache file naming
- change the cache SQLite schema
- change kbase on-disk layout or vector compatibility rules
- introduce new product features
- rewrite the implementation from scratch

## Chosen Direction

Use a domain-oriented modular refactor with compatibility shims.

This means the codebase will be reorganized around stable areas of responsibility:

- web search and content extraction
- cache persistence
- search orchestration
- knowledge base operations
- iterative search strategy
- CLI entrypoints

The migration will be incremental. New modules are introduced first. Existing public modules remain as thin compatibility layers during the transition so tests and CLI behavior stay stable.

## Rejected Alternatives

### Full one-shot rewrite

Rejected because the current test suite is broad but the package has enough coupling that a one-shot migration would create unnecessary risk.

### Minimal facade-only cleanup

Rejected because it would improve naming without materially reducing internal complexity in the largest modules.

## Target Module Structure

The refactor should move toward this package layout:

```text
src/ksearch/
  cli/
    __init__.py
    search.py
    kbase.py
    system.py

  web/
    __init__.py
    search_client.py
    url_policy.py
    extractor.py
    cleaner.py

  cache_layer/
    __init__.py
    repository.py
    store.py
    service.py

  searching/
    __init__.py
    service.py

  knowledge/
    __init__.py
    chunking.py
    embeddings.py
    vector_store.py
    service.py

  iterative_flow/
    __init__.py
    engine.py
    query.py
    sufficiency.py
    convergence.py

  models.py
  config.py
  output.py
  __main__.py
```

## Naming Rationale

The subpackage names intentionally avoid collisions with current top-level modules such as:

- `search.py`
- `cache.py`
- `kbase.py`
- `iterative.py`

That allows incremental migration without import ambiguity during the transition. A later cleanup can decide whether to keep the new names or collapse the old modules into packages, but that is not required for this refactor to succeed.

## Responsibilities By Module

### `web/`

Purpose: all network search and webpage content extraction behavior.

Expected responsibilities:

- SearXNG requests and result normalization
- URL skip policy
- HTML fetching for extraction
- main-body extraction strategy
- fallback extraction strategy
- content cleaning

Expected components:

- `SearchClient`
- `UrlPolicy`
- `ContentExtractor`
- `ContentCleaner`

`ContentExtractor` should own the extraction pipeline but not know about cache or kbase persistence.

### `cache_layer/`

Purpose: local cache persistence and retrieval.

Expected responsibilities:

- SQLite record persistence
- Markdown file storage
- cache lookup
- cache existence checks
- cache stats

Expected components:

- `CacheRepository`
- `CacheStore`
- `CacheService`

`CacheService` preserves the current `CacheManager` behavior while delegating persistence details to narrower collaborators.

### `searching/`

Purpose: normal search orchestration.

Expected responsibilities:

- cache-first lookup flow
- network fallback flow
- duplicate filtering
- invoking webpage extraction
- saving converted results
- returning unified result entries

Expected component:

- `SearchService` or a retained `SearchEngine` compatibility name

This layer should depend on `cache_layer` and `web`, but should not implement extraction details itself.

### `knowledge/`

Purpose: knowledge base ingestion and semantic retrieval.

Expected responsibilities:

- file/content chunking
- embedding generation
- vector store adaptation
- ingestion from files
- ingestion from raw content
- semantic search
- compatibility metadata management
- kbase stats

Expected components:

- `Chunker`
- `EmbeddingProvider`
- `VectorStore`
- `KnowledgeBaseService`

The goal is to break `kbase.py` into smaller parts without changing behavior or persisted data rules.

### `iterative_flow/`

Purpose: iterative kbase-first search strategy.

Expected responsibilities:

- query classification
- sufficiency scoring
- convergence checks
- iteration boundary rules
- iterative web expansion orchestration

Expected components:

- `QueryClassifier`
- `SufficiencyEvaluator`
- `ConvergenceEvaluator`
- `IterationBoundary`
- `IterativeSearchEngine`

This module remains an orchestration layer and should depend on `knowledge`, `cache_layer`, and `web`.

### `cli/`

Purpose: command registration and user-facing CLI flow.

Expected responsibilities:

- define Typer commands
- map flags into config/options
- instantiate services
- render output
- user-facing error messaging

CLI code should not own business logic beyond argument handling and wiring.

## Stable Shared Models

`src/ksearch/models.py` remains the stable shared domain model module for this refactor unless a later change proves it needs splitting.

The following dataclasses are considered stable compatibility contracts during the refactor:

- `CacheEntry`
- `SearchResult`
- `ResultEntry`

Field names and semantics must remain compatible.

## Compatibility Strategy

Compatibility is a hard constraint for this work.

### CLI compatibility

The following must remain unchanged:

- command names
- flags and option names
- default behavior
- output layout for markdown/path modes

### Cache compatibility

The following must remain unchanged:

- cache file path generation based on URL hash
- cache file format
- SQLite table schema
- SQLite field meanings
- existing cached data readability

### Kbase compatibility

The following must remain unchanged:

- embedding compatibility checks
- persisted metadata behavior
- storage layout expectations for current backends
- query result semantics

### Import compatibility during migration

Current top-level modules should remain available as thin compatibility shims during the refactor. For example:

- `src/ksearch/converter.py`
- `src/ksearch/cache.py`
- `src/ksearch/search.py`
- `src/ksearch/kbase.py`
- `src/ksearch/iterative_engine.py`

These files can gradually become wrappers or re-exports over the new modular implementation.

## Extraction Pipeline Design

The current webpage extraction behavior should remain logically identical, but the implementation should be decomposed.

Target internal flow:

1. Search client returns normalized search results
2. URL policy filters known bad targets
3. extractor fetches HTML
4. extractor tries main-body extraction with `trafilatura`
5. cleaner removes common boilerplate
6. if extracted content is too short, fallback extraction runs with `markitdown`
7. cleaner runs on fallback output
8. short content is rejected
9. successful content is returned to orchestration

This flow currently exists, but it is embedded in one module. The refactor should preserve the behavior while making each step independently testable.

## Search Orchestration Design

Normal search orchestration should remain:

1. exact cache match
2. partial cache match
3. network search when allowed
4. duplicate URL filtering
5. URL policy filtering
6. extraction and cleaning
7. cache persistence
8. unified result output

The orchestration layer should be responsible only for sequencing and decision-making, not low-level implementation details.

## Knowledge Base Design

The knowledge base layer should be split so that these concerns are isolated:

- chunking policy
- embedding generation
- backend-specific vector storage
- high-level ingest/query/reset operations

The main rule is that `KnowledgeBaseService` becomes the coordination point, while lower-level collaborators do the concrete work.

This split should be conservative. The first modularization pass does not need to introduce abstraction for hypothetical future backends beyond what the current system already supports.

## Iterative Search Design

Iterative search should remain a strategy layer on top of existing services:

1. classify query type
2. search kbase first
3. score sufficiency
4. if insufficient, expand to web
5. extract content
6. persist to cache
7. ingest into kbase
8. re-query and evaluate convergence
9. stop on sufficiency or iteration boundary

This layer must not take ownership of cache internals, extraction internals, or vector backend internals.

## Migration Plan Shape

Implementation should proceed in stages that can each be tested independently:

1. Extract `web/` and `cache_layer/` internals while preserving current public classes
2. Move normal search orchestration onto the new modules
3. Split `kbase.py` into `knowledge/` collaborators behind a stable service
4. Move iterative orchestration and CLI wiring onto the new services
5. Remove dead internal code once compatibility wrappers are proven stable

Each stage should preserve a working CLI and passing targeted tests.

## Testing Strategy

The refactor is complete only if behavior remains stable.

Minimum verification should include:

- `tests/test_converter.py`
- `tests/test_search.py`
- `tests/test_cache.py`
- `tests/test_kbase.py`
- `tests/test_iterative.py`
- `tests/test_main.py`
- `tests/test_output.py`

Additional verification expectations:

- existing CLI behavior remains unchanged
- cached Markdown files are still written under the same path rule
- existing SQLite cache records remain readable
- short-content rejection still behaves the same
- iterative ingestion still persists extracted web content into cache and kbase

## Risks

### Import-cycle risk

Splitting large modules can accidentally create circular imports. Shared models and narrow service interfaces should be used to avoid that.

### Over-abstraction risk

The refactor should not introduce interfaces that only serve theoretical future use cases. Extract only the seams already present in the existing behavior.

### Compatibility drift

It is easy to accidentally change cache persistence semantics or CLI defaults during a structural rewrite. Compatibility-sensitive behavior should be covered by focused regression tests before moving code.

### kbase migration risk

`kbase.py` is the largest and most coupled module. It should be modularized later in the sequence, after the web and cache boundaries are stable.

## Success Criteria

This design is successful when all of the following are true:

- package structure reflects domain boundaries clearly
- oversized modules are materially smaller
- orchestration logic is separated from low-level mechanics
- CLI behavior remains compatible
- cache and kbase persistence remain compatible
- existing tests pass with minimal or no user-facing behavior changes

## Implementation Guidance

The implementation should favor:

- thin compatibility shims
- incremental commits by domain
- test-first changes for each moved responsibility
- small, focused modules over large replacement files

The implementation should avoid:

- broad renaming with no boundary improvement
- simultaneous persistence and behavior changes
- changing data models unless required for compatibility preservation
