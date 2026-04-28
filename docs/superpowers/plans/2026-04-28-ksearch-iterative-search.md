# ksearch Iterative Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `ksearch` iterative kbase-first search across implementation, tests, and documentation, then apply targeted search-path cleanup.

**Architecture:** Keep the current split between CLI, standard search, kbase, and iterative orchestration. Tighten the iterative path so it uses clear result semantics and bounded web expansion, then synchronize README and internal docs with the actual `ksearch` feature set.

**Tech Stack:** Python 3.10+, typer, rich, requests, markitdown, sqlite3, chromadb/qdrant, pytest

---

## File Structure

- [`src/ksearch/__main__.py`](/home/lan/workspace/test/search/inc/src/ksearch/__main__.py): CLI entry and execution-path selection
- [`src/ksearch/config.py`](/home/lan/workspace/test/search/inc/src/ksearch/config.py): default config and merge behavior
- [`src/ksearch/iterative.py`](/home/lan/workspace/test/search/inc/src/ksearch/iterative.py): iterative search orchestration and evaluators
- [`src/ksearch/kbase.py`](/home/lan/workspace/test/search/inc/src/ksearch/kbase.py): kbase ingestion helpers
- [`tests/test_iterative.py`](/home/lan/workspace/test/search/inc/tests/test_iterative.py): iterative engine unit coverage
- [`README.md`](/home/lan/workspace/test/search/inc/README.md): user-facing docs
- [`docs/superpowers/specs/2026-04-28-ksearch-iterative-search-design.md`](/home/lan/workspace/test/search/inc/docs/superpowers/specs/2026-04-28-ksearch-iterative-search-design.md): design spec

### Task 1: Lock Down Iterative CLI and Config Semantics

**Files:**
- Modify: `src/ksearch/__main__.py`
- Modify: `src/ksearch/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing config/CLI tests**

```python
def test_merge_config_preserves_iterative_defaults():
    merged = merge_config({}, {}, DEFAULT_CONFIG)
    assert merged["iterative_enabled"] is False
    assert merged["max_iterations"] == 5


def test_merge_config_applies_iterative_cli_override():
    merged = merge_config(
        {"iterative_enabled": True},
        {"kbase_mode": "chroma"},
        DEFAULT_CONFIG,
    )
    assert merged["iterative_enabled"] is True
    assert merged["kbase_mode"] == "chroma"
```

- [ ] **Step 2: Run tests to verify current coverage gap**

Run: `uv run pytest tests/test_config.py -v`
Expected: either missing iterative assertions or no coverage for the new keys

- [ ] **Step 3: Make CLI/config behavior explicit**

```python
if config.get("iterative_enabled"):
    kbase_mode_value = config.get("kbase_mode")
    if not kbase_mode_value or kbase_mode_value == "none":
        console.print("[red]Iterative search requires --kbase mode (chroma or qdrant)[/red]")
        raise typer.Exit(1)
```

```python
DEFAULT_CONFIG = {
    # ...
    "iterative_enabled": False,
    "max_iterations": 5,
    "max_time_seconds": 180,
    "fact_threshold": 0.7,
    "exploration_threshold": 0.4,
    "scoring_weights": {"vector": 0.4, "count": 0.3, "coverage": 0.3},
}
```

- [ ] **Step 4: Run tests to verify config behavior**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ksearch/__main__.py src/ksearch/config.py tests/test_config.py
git commit -m "feat: document and validate iterative search config"
```

### Task 2: Tighten Iterative Search Orchestration

**Files:**
- Modify: `src/ksearch/iterative.py`
- Modify: `src/ksearch/kbase.py`
- Test: `tests/test_iterative.py`

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_iterative_engine_returns_kb_results_when_sufficient(...):
    kbase.search.return_value = [make_kb_result("a", 0.95, "content")]
    engine = IterativeSearchEngine(kbase, searxng, converter, cache, config)
    results = engine.search("what is python")
    assert len(results) == 1
    assert results[0].source == "kbase"


def test_iterative_engine_ingests_only_uncached_web_results(...):
    cache.exists.side_effect = [True, False]
    searxng.search.return_value = [cached_result, fresh_result]
    engine.search("explore ai agents")
    kbase.ingest_file_from_content.assert_called_once()
```

- [ ] **Step 2: Run tests to verify expected failures or missing assertions**

Run: `uv run pytest tests/test_iterative.py -v`
Expected: FAIL on orchestration semantics not yet covered

- [ ] **Step 3: Refine the iterative engine**

```python
class IterativeSearchEngine:
    def search(self, query: str) -> list[ResultEntry]:
        query_type = self.query_classifier.classify(query)
        threshold = self.sufficiency.get_threshold(query_type)
        kb_results = self.kbase.search(query, top_k=10)
        score = self.sufficiency.score(kb_results)

        if self.sufficiency.is_sufficient(score, threshold):
            return self._convert_kbase_results(kb_results)

        # bounded web expansion + deduplicated final combination
```

```python
def ingest_file_from_content(self, content: str, metadata: dict = None, ... ) -> int:
    if not content:
        return 0
    # chunk generated content and store directly into the kbase backend
```

- [ ] **Step 4: Run iterative tests**

Run: `uv run pytest tests/test_iterative.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ksearch/iterative.py src/ksearch/kbase.py tests/test_iterative.py
git commit -m "feat: tighten iterative kbase-first search flow"
```

### Task 3: Reduce Search-Path Ambiguity in the CLI

**Files:**
- Modify: `src/ksearch/__main__.py`
- Modify: `src/ksearch/models.py`
- Test: `tests/test_output.py`

- [ ] **Step 1: Write a failing output/shape regression test**

```python
def test_result_entry_from_iterative_path_formats_like_standard_results():
    entry = ResultEntry(
        url="web:https://example.com",
        title="Example",
        content="Body",
        file_path="/tmp/example.md",
        cached=True,
        source="web",
        cached_date="2026-04-28",
    )
    output = format_markdown([entry], "example")
    assert "Example" in output
    assert "/tmp/example.md" in output
```

- [ ] **Step 2: Run the targeted output test**

Run: `uv run pytest tests/test_output.py -v`
Expected: coverage gap or formatting assumption to clarify

- [ ] **Step 3: Keep `ResultEntry` semantics stable across paths**

```python
all_results = iterative_engine.search(keyword)
```

```python
all_results.append(
    ResultEntry(
        url=f"kbase://{r.id}",
        title=r.title or r.file_path,
        content=preview,
        file_path=r.file_path,
        cached=True,
        source=f"kbase:{r.source or 'local'}",
        cached_date=created_at,
    )
)
```

- [ ] **Step 4: Run affected tests**

Run: `uv run pytest tests/test_output.py tests/test_iterative.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ksearch/__main__.py src/ksearch/models.py tests/test_output.py
git commit -m "refactor: stabilize search result semantics"
```

### Task 4: Synchronize README and Internal Docs

**Files:**
- Modify: `README.md`
- Create: `docs/superpowers/specs/2026-04-28-ksearch-iterative-search-design.md`
- Create: `docs/superpowers/plans/2026-04-28-ksearch-iterative-search.md`

- [ ] **Step 1: Update README examples and config**

```markdown
### Iterative kbase-first search

```bash
ksearch --kbase chroma --iterative "how does asyncio task cancellation work"
```

```json
{
  "iterative_enabled": false,
  "max_iterations": 5,
  "max_time_seconds": 180
}
```
```

- [ ] **Step 2: Review docs for project-name drift and obsolete assumptions**

Run: `rg -n "kbase-cli|\\bkb\\b" README.md docs/superpowers/specs docs/superpowers/plans`
Expected: only intentional references remain

- [ ] **Step 3: Save the final synced docs**

```markdown
- `ksearch` is the project/package/CLI name
- `kbase` remains the subcommand namespace for knowledge-base operations
- iterative mode requires kbase mode
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-04-28-ksearch-iterative-search-design.md docs/superpowers/plans/2026-04-28-ksearch-iterative-search.md
git commit -m "docs: sync ksearch iterative search documentation"
```

### Task 5: Full Verification

**Files:**
- Test: `tests/test_config.py`
- Test: `tests/test_output.py`
- Test: `tests/test_iterative.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Run focused regression tests**

Run: `uv run pytest tests/test_config.py tests/test_output.py tests/test_iterative.py tests/test_search.py -v`
Expected: PASS

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 3: Review working tree**

Run: `git status --short`
Expected: only intended documentation/code/test changes remain

- [ ] **Step 4: Commit**

```bash
git add README.md src/ksearch/__main__.py src/ksearch/config.py src/ksearch/iterative.py src/ksearch/kbase.py tests/test_config.py tests/test_output.py tests/test_iterative.py tests/test_search.py
git commit -m "feat: complete iterative search documentation and cleanup"
```
