# Ksearch Embedding Dimension Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make embedding model changes safe by adding configurable embedding dimensions, kbase metadata validation, and an explicit reset flow.

**Architecture:** Extend config and CLI so the embedding model and dimension are explicit inputs to knowledge-base construction. Persist kbase metadata alongside the local kbase directory, validate it on open, and require an explicit reset when the configured model or dimension no longer matches the stored kbase.

**Tech Stack:** Python, Typer, Chroma, Qdrant, pytest

---

### Task 1: Lock behavior with tests

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_kbase.py`
- Modify: `tests/test_main.py`

- [ ] Add a config test proving `embedding_dimension` exists in defaults and survives merge.
- [ ] Add kbase tests proving new metadata is written on first init, reused on reopen, and rejected when model or dimension changes.
- [ ] Add a CLI test proving `kbase reset --confirm` rebuilds a kbase instance with the requested settings.

### Task 2: Implement safe kbase metadata

**Files:**
- Modify: `src/ksearch/kbase.py`

- [ ] Add `embedding_dimension` to `KnowledgeBase`.
- [ ] Replace hard-coded vector sizes with the configured dimension.
- [ ] Persist kbase metadata under the kbase directory and validate it before using a non-empty kbase.
- [ ] Add an explicit reset method that clears data and refreshes metadata.

### Task 3: Wire config and CLI

**Files:**
- Modify: `src/ksearch/config.py`
- Modify: `src/ksearch/__main__.py`

- [ ] Add `embedding_dimension` to default config and config update flow.
- [ ] Pass embedding model and dimension through all kbase construction paths.
- [ ] Add `kbase reset --confirm` so users can safely reset the kbase after changing embedding settings.

### Task 4: Document and verify

**Files:**
- Modify: `README.md`

- [ ] Document the new `embedding_dimension` setting and the requirement to reset/rebuild kbase when switching embedding model or dimension.
- [ ] Run focused pytest targets, then a broader regression subset covering config, kbase, embeddings, CLI, and iterative search integration.
