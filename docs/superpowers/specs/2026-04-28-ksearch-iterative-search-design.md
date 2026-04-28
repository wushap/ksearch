# ksearch Iterative Search Design

> Sync `ksearch` documentation and implementation around kbase-assisted iterative search, without broad unrelated refactors.

## Goal

Bring the repository to a coherent state where:

- `ksearch` documentation matches the current project name and feature set
- iterative kbase-first search is a documented, tested, and maintainable path
- the CLI, config, and result semantics are consistent across normal and iterative search flows
- small, task-aligned code quality improvements are applied where they reduce ambiguity or duplicated logic

## Scope

This design covers:

- the `kbase search` command, especially `--kbase` and `--iterative`
- config defaults and README/spec/plan synchronization
- iterative search orchestration and result conversion
- targeted cleanup in the touched modules

This design does not cover:

- new storage backends
- large kbase schema redesigns
- a new ranking model
- broad refactors outside the search path

## Current Problems

The repository has drifted in three ways:

1. The existing spec/plan describe an older `kbase-cli` shape, while the codebase is now `ksearch` with kbase features and optional iterative search.
2. The iterative flow exists in code and tests, but its behavior is not yet consistently exposed in README/config/docs.
3. Search-path responsibilities are partially duplicated between the CLI and the iterative engine, which makes result semantics and maintenance less clear than they should be.

## Approaches Considered

### 1. Minimal doc-only sync

Update README and spec files only, leave the code shape mostly as-is.

Pros:

- Fastest path
- Lowest implementation risk

Cons:

- Leaves search flow inconsistencies in place
- Misses the chance to tighten semantics while the feature is still new

### 2. Targeted alignment around iterative search

Keep the existing architecture, but formalize the iterative path as a documented orchestration layer, reduce duplication where it directly affects the feature, and synchronize tests/docs/config.

Pros:

- Best balance of delivery speed and technical clarity
- Improves maintainability without destabilizing unrelated modules
- Matches the current user request

Cons:

- Requires touching several files instead of just docs

### 3. Full search-architecture refactor

Rebuild the search stack around a single shared orchestration abstraction.

Pros:

- Cleanest long-term architecture

Cons:

- Too large for the current task
- Higher regression risk
- Would delay finishing the iterative feature and documentation work

## Recommended Approach

Use approach 2.

The repository already has a workable split:

- `SearchEngine` for cache/network flow
- `KnowledgeBase` for semantic storage/search
- `IterativeSearchEngine` for kbase-first adaptive search

The right move is to tighten those boundaries instead of replacing them.

## Target Behavior

### Normal search

`kbase search <query>` keeps the current behavior:

- optional kbase recall when `--kbase` is enabled
- normal cache-first/network-second search for web results
- combined output through the shared output formatter

### Iterative search

`kbase search <query> --kbase <mode> --iterative` behaves as follows:

1. Classify the query as `fact` or `exploration`
2. Search the kbase
3. Evaluate result sufficiency against the threshold for that query type
4. If sufficient, return kbase-derived results immediately
5. If insufficient, run bounded web expansion:
   - search the web
   - skip already-cached URLs
   - convert retrievable URLs to Markdown
   - ingest converted content into the kbase
   - track web-derived results for final output
6. Re-check stop conditions using convergence and hard boundaries
7. Return a combined result set with stable output semantics

## Architecture

### CLI layer

[`src/ksearch/__main__.py`](/home/lan/workspace/test/search/inc/src/ksearch/__main__.py)

Responsibilities:

- parse CLI options
- merge config sources
- initialize dependencies
- choose between normal and iterative search paths
- print formatted output and user-facing errors

Design constraint:

- the CLI should not own low-level search rules beyond selecting the execution path

### Standard search orchestration

[`src/ksearch/search.py`](/home/lan/workspace/test/search/inc/src/ksearch/search.py)

Responsibilities:

- exact/partial cache lookup
- network fallback
- URL filtering
- conversion and cache persistence

Design constraint:

- standard search should remain the non-iterative code path

### Iterative orchestration

[`src/ksearch/iterative.py`](/home/lan/workspace/test/search/inc/src/ksearch/iterative.py)

Responsibilities:

- query classification
- sufficiency scoring
- convergence checks
- iteration boundaries
- kbase ingestion of new web content
- final result combination

Design constraint:

- iterative logic should be self-contained and should reuse shared data models instead of inventing new output semantics in the CLI

### Knowledge base

[`src/ksearch/kbase.py`](/home/lan/workspace/test/search/inc/src/ksearch/kbase.py)

Responsibilities:

- semantic storage
- semantic retrieval
- file ingestion
- content ingestion for web-discovered material

Design constraint:

- direct-content ingestion should be supported as a first-class helper because iterative search produces converted text before it exists as a local source file

## Result Semantics

All user-visible search results should continue to be expressed as `ResultEntry`.

Required invariants:

- `title` is always populated when the source provides one
- `file_path` is stable and usable for `path` output mode
- `source` clearly distinguishes kbase-derived vs web-derived material
- combined result lists avoid duplicate entries by path/identity

For iterative search:

- kbase hits are returned first
- web-expanded results are appended after deduplication
- the output formatter should not need feature-specific branching

## Configuration

The default config remains file-based and mergeable with CLI overrides.

Iterative search settings that must be documented and supported:

- `iterative_enabled`
- `max_iterations`
- `max_time_seconds`
- `fact_threshold`
- `exploration_threshold`
- `scoring_weights`

CLI behavior:

- `--iterative` enables the iterative path
- iterative mode requires `--kbase` or an equivalent configured `kbase_mode`
- invalid combinations should fail with a clear user-facing message

## Error Handling

Rules:

- missing kbase mode for iterative search is a usage error
- failure in the iterative path should surface a clear top-level message
- individual URL conversion failures should not abort the whole search
- optional kbase failures in non-iterative mode may degrade gracefully when possible

## Testing

Testing should cover:

- convergence evaluation
- query classification
- sufficiency scoring
- iteration boundaries
- iterative engine orchestration with mocked dependencies
- CLI/config behavior for iterative mode
- documentation examples staying aligned with real flags and config keys

## Documentation Deliverables

The repository should end this task with:

- a new iterative-search design doc
- an implementation plan aligned to `ksearch`, not `kbase-cli`
- an updated README covering iterative mode and config keys
- obsolete assumptions in older docs either replaced or clearly superseded

## Success Criteria

This task is complete when:

- the codebase exposes iterative search coherently through CLI, config, and docs
- tests pass for the touched functionality
- README and internal docs match the current `ksearch` architecture
- the touched code is modestly cleaner and less ambiguous than before
