# Content Optimization Module

## Overview

The `content_optimization` module adds AI-driven iterative content refinement to ksearch. It uses a local LLM (via Ollama) to evaluate search result quality, identify information gaps, and iteratively improve results until a confidence threshold is met.

This module is inspired by the iterative refinement pattern from `local-deepresearch`, adapted to work with ksearch's search/cache/kbase pipeline.

## Architecture

```
                          ┌──────────────────────┐
                          │   CLI: ksearch        │
                          │   optimize <query>    │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │   ContentOptimizer    │
                          │   (orchestrator)      │
                          └──┬──────────────┬────┘
                             │              │
                ┌────────────▼──┐    ┌──────▼───────────┐
                │QualityEvaluator│    │  OllamaChatClient │
                │(evaluate)      │    │  (/api/chat)      │
                └──────┬────────┘    └───────────────────┘
                       │
              ┌────────▼────────┐
              │  Prompt Templates│
              │  (prompts.py)    │
              └─────────────────┘
```

## Iterative Refinement Loop

The core loop in `ContentOptimizer.optimize()`:

```
1. Fetch initial results (or use provided results)
2. Aggregate content (truncate to MAX_CONTENT_CHARS)
3. For each iteration (up to max_iterations):
   a. Call QualityEvaluator.evaluate() → QualityAssessment
   b. If action == "COMPLETE" or confidence >= threshold → stop
   c. Use refinement_query from assessment to search for more results
   d. Merge new results, re-aggregate content
4. Synthesize final content via LLM
5. Return OptimizationResult
```

The evaluator sends content to the LLM with a structured prompt requesting JSON output:
```json
{
  "action": "REFINE or COMPLETE",
  "confidence": 0.0 to 1.0,
  "gaps": ["gap1", "gap2"],
  "refinement_query": "targeted query to fill gaps",
  "summary": "quality assessment"
}
```

## Module Files

### `ollama_client.py` — Ollama Chat Client

Communicates with Ollama's `/api/chat` endpoint for LLM generation. This is distinct from the existing `EmbeddingGenerator` which uses `/api/embeddings`.

**Key class:** `OllamaChatClient`

| Method | Description |
|--------|-------------|
| `chat(messages, format_json, temperature)` | Send message list to Ollama, return response text |
| `generate(prompt, system, format_json, temperature)` | Convenience wrapper for single-prompt usage |
| `health_check()` | Check Ollama availability and model presence |

**Configuration:**
- `model`: Ollama model name (default: `gemma4:e2b`)
- `ollama_url`: Ollama server URL (default: `http://localhost:11434`)
- `temperature`: LLM temperature (default: `0.3`)
- `timeout`: Request timeout in seconds (default: `60`)

When `format_json=True`, Ollama's `"format": "json"` feature forces the model to return valid JSON, eliminating a class of parsing errors.

### `prompts.py` — Prompt Templates

Centralizes all prompt templates. Each function returns a `(system_prompt, user_prompt)` tuple.

| Function | Purpose |
|----------|---------|
| `format_evaluation_prompt(query, results_text)` | Quality evaluation with REFINE/COMPLETE actions |
| `format_refine_prompt(query, gaps)` | Generate targeted follow-up search query |
| `format_synthesis_prompt(query, content)` | Synthesize final optimized content |

### `evaluator.py` — Quality Evaluator

Uses the Ollama chat client to assess content quality. Returns a structured `QualityAssessment`.

**Key class:** `QualityEvaluator`

| Method | Description |
|--------|-------------|
| `evaluate(query, content)` | Evaluate content quality, return `QualityAssessment` |
| `should_continue(assessment)` | Check if refinement should continue |

**Fallback behavior:** If the LLM returns malformed JSON, returns a safe `QualityAssessment(action="COMPLETE", confidence=0.5)` to terminate the loop gracefully.

**Action validation:** If the LLM returns an unexpected action value (not "REFINE" or "COMPLETE"), defaults to "COMPLETE" with a warning.

### `optimizer.py` — Content Optimizer

The main orchestrator implementing the iterative refinement loop.

**Key class:** `ContentOptimizer`

| Method | Description |
|--------|-------------|
| `optimize(query, search_fn, initial_results)` | Run iterative refinement with search |
| `optimize_content(query, content)` | Evaluate existing content without re-searching |
| `_aggregate_content(results)` | Combine result contents with character limits |
| `_synthesize(query, content)` | LLM-based content synthesis |

**Design decisions:**
- `MAX_CONTENT_CHARS = 8000`: limits content sent to the LLM to stay within context windows
- `search_fn` is a callable dependency injection — works with any search backend
- Input `results` list is copied to avoid mutating the caller's data
- Assessment is initialized with safe defaults to handle `max_iterations=0`

## Integration Points

### Standalone CLI (`ksearch optimize`)

The primary usage mode. Runs the full search + optimization pipeline.

```bash
ksearch optimize "python asyncio" --verbose
```

### Iterative Flow Post-Processing

When `optimization_enabled: true` in config, the `IterativeSearchEngine` runs content optimization as a post-processing step after the iterative search completes.

The integration uses lazy imports to avoid pulling in the `content_optimization` module when disabled:

```python
if self.optimization_enabled:
    from ksearch.content_optimization import ContentOptimizer, OllamaChatClient, QualityEvaluator
    # ... build optimizer and run
```

## Configuration

All settings in `~/.ksearch/config.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `optimization_enabled` | `false` | Enable optimization in iterative search engine |
| `optimization_model` | `gemma4:e2b` | Ollama model for generation |
| `optimization_max_iterations` | `3` | Max refinement iterations |
| `optimization_confidence_threshold` | `0.8` | Quality score to stop refinement |
| `optimization_max_time_seconds` | `120` | Hard time limit |
| `optimization_temperature` | `0.3` | LLM temperature (lower = more deterministic) |

## Prerequisites

1. Ollama running at configured URL (default: `http://localhost:11434`)
2. Required model pulled: `ollama pull gemma4:e2b`

## Data Types

### `QualityAssessment`

Returned by `QualityEvaluator.evaluate()`:

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | "REFINE" or "COMPLETE" |
| `confidence` | `float` | 0.0 to 1.0 |
| `gaps` | `list[str]` | Identified information gaps |
| `refinement_query` | `str` | Suggested follow-up query |
| `summary` | `str` | Brief quality assessment |

### `OptimizationResult`

Returned by `ContentOptimizer.optimize()`:

| Field | Type | Description |
|-------|------|-------------|
| `original_query` | `str` | The original search query |
| `final_content` | `str` | Synthesized optimized content |
| `quality` | `QualityAssessment` | Final quality assessment |
| `iterations_used` | `int` | Number of refinement iterations |
| `elapsed_seconds` | `float` | Total elapsed time |
| `refinement_history` | `list[dict]` | Per-iteration details |
