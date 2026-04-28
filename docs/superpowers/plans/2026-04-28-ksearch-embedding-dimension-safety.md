# Ksearch Embedding Dimension Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make embedding model changes safe by adding configurable embedding dimensions, KB metadata validation, and an explicit reset flow.

**Architecture:** Extend config and CLI so the embedding model and dimension are explicit inputs to knowledge-base construction. Persist KB metadata alongside the local KB directory, validate it on open, and require an explicit reset when the configured model or dimension no longer matches the stored KB.

**Tech Stack:** Python, Typer, Chroma, Qdrant, pytest

---

### Task 1: Lock behavior with tests

**Files:**
- Modify: `tests/test_config.py`
- Modify: `tests/test_kb.py`
- Modify: `tests/test_main.py`

- [ ] Add a config test proving `embedding_dimension` exists in defaults and survives merge.
- [ ] Add KB tests proving new metadata is written on first init, reused on reopen, and rejected when model or dimension changes.
- [ ] Add a CLI test proving `kb reset --confirm` rebuilds a KB instance with the requested settings.

### Task 2: Implement safe KB metadata

**Files:**
- Modify: `src/ksearch/kb.py`

- [ ] Add `embedding_dimension` to `KnowledgeBase`.
- [ ] Replace hard-coded vector sizes with the configured dimension.
- [ ] Persist KB metadata under the KB directory and validate it before using a non-empty KB.
- [ ] Add an explicit reset method that clears data and refreshes metadata.

### Task 3: Wire config and CLI

**Files:**
- Modify: `src/ksearch/config.py`
- Modify: `src/ksearch/__main__.py`

- [ ] Add `embedding_dimension` to default config and config update flow.
- [ ] Pass embedding model and dimension through all KB construction paths.
- [ ] Add `ksearch kb reset --confirm` so users can safely reset the KB after changing embedding settings.

### Task 4: Document and verify

**Files:**
- Modify: `README.md`

- [ ] Document the new `embedding_dimension` setting and the requirement to reset/rebuild KB when switching embedding model or dimension.
- [ ] Run focused pytest targets, then a broader regression subset covering config, KB, embeddings, CLI, and iterative search integration.
