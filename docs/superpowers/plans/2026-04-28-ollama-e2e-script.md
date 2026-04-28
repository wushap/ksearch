# Ollama E2E Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable end-to-end integration script that validates the live Ollama + kbase + SearXNG workflow with multilingual keywords.

**Architecture:** Keep the integration test outside pytest's live execution path as a standalone shell script under `tests/`, because it depends on real local services. Add a lightweight pytest guard that checks the script exists and still covers the intended commands and scenarios, then document how to run it.

**Tech Stack:** Bash, pytest, kbase CLI, Ollama HTTP API, SearXNG

---

### Task 1: Lock the script contract

**Files:**
- Create: `tests/test_ollama_e2e_script.py`

- [ ] Add a test that requires `tests/ollama_e2e_integration.sh` to exist.
- [ ] Add assertions that the script covers `kbase reset`, `kbase ingest`, `kbase search`, `search --only-cache`, `search --iterative`, and a non-embedding model negative case.

### Task 2: Implement the real integration script

**Files:**
- Create: `tests/ollama_e2e_integration.sh`

- [ ] Build a standalone Bash script that validates live dependencies, creates an isolated temp kbase, runs multilingual kbase and search flows, and writes a markdown report.
- [ ] Ensure the script uses the currently available `nomic-embed-text:latest` model and records the observed non-embedding-model failure path.

### Task 3: Document usage and verify

**Files:**
- Modify: `README.md`

- [ ] Add a short section showing how to run the new Ollama E2E integration script and what local services it expects.
- [ ] Run the new pytest guard, then execute the script itself in the current environment and confirm it succeeds.
