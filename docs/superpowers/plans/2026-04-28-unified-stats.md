# Unified Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a unified statistics command that summarizes cache and knowledge-base state in one place.

**Architecture:** Keep aggregation logic close to each storage layer by adding stats helpers to `CacheManager` and `KnowledgeBase`. Expose the combined view through a new top-level `kbase stats` command that renders overview, cache, and kbase sections without changing search behavior.

**Tech Stack:** Python, sqlite3, Typer, Rich, Chroma/Qdrant, pytest

---

### Task 1: Lock expected behavior

**Files:**
- Modify: `tests/test_cache.py`
- Modify: `tests/test_kbase.py`
- Modify: `tests/test_main.py`

- [ ] Add a cache test for entry count, keyword variety, total size, engine counts, and domain counts.
- [ ] Add a kbase test for chunk count, source-file count, total size, and source counts.
- [ ] Add a CLI test that requires `kbase stats` to print unified overview headings.

### Task 2: Implement storage-level stats helpers

**Files:**
- Modify: `src/ksearch/cache.py`
- Modify: `src/ksearch/kbase.py`

- [ ] Add a cache stats method that reads SQLite plus on-disk files.
- [ ] Add a kbase stats method that summarizes stored entries, file paths, sizes, and source distribution.

### Task 3: Expose unified stats in CLI

**Files:**
- Modify: `src/ksearch/__main__.py`
- Modify: `README.md`

- [ ] Add `kbase stats` with cache and kbase configuration options.
- [ ] Render overview, cache, and kbase tables with human-readable size output.
- [ ] Document the new command briefly in the README.

### Task 4: Verify

**Files:**
- None

- [ ] Run focused tests for cache, kbase, and CLI stats.
- [ ] Run a broader regression subset covering existing cache/kbase/search behavior.
