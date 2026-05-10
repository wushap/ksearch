# ksearch CLI Debug Logging Design

> Add a global debug logging mode for all `ksearch` CLI commands, with per-run log directories and end-to-end traceability across the command execution flow.

## Goal

Introduce a global `--debug` flag at the root CLI level so any command can run in debug mode:

- `ksearch --debug search ...`
- `ksearch --debug optimize ...`
- `ksearch --debug stats`
- `ksearch --debug config ...`
- `ksearch --debug health`
- `ksearch --debug kbase ...`

When enabled, the CLI should create a per-run debug directory under `~/.ksearch/debug/cli-<time>/` and record the full processing flow from command input through intermediate component activity to final result summary.

The logging should be useful for real diagnosis, not just command start/end markers.

## Scope

This design covers:

- root-level CLI debug flag handling
- per-run debug session setup and teardown
- debug log file layout and formats
- structured event recording across CLI, search, kbase, rerank, optimization, and external-request boundaries
- content truncation rules for readable but actionable logs
- tests proving the feature works across commands

This design does not cover:

- remote log shipping
- log rotation or retention cleanup
- a TUI or web viewer for debug sessions
- persistent background daemon logging
- non-CLI entrypoints outside `ksearch.__main__`

## Current Problems

The repository already uses Python `logging` in several modules, but there is no usable CLI-level debug workflow:

1. There is no global switch to enable detailed tracing for a specific CLI run.
2. Logs are not routed into a per-command session directory.
3. Most core components do not emit enough structured diagnostic detail to reconstruct the full execution path.
4. There is no stable artifact set that captures command context, component events, and final outcome in one place.

This makes debugging cross-component issues unnecessarily expensive, especially for:

- cache vs network behavior
- kbase retrieval vs hybrid retrieval vs rerank behavior
- iterative sufficiency and fallback decisions
- Ollama and SearXNG interaction failures
- command-specific wiring issues

## Requirements

### Functional Requirements

- The root CLI must accept a global `--debug` flag.
- `--debug` must work with all existing CLI subcommands.
- Enabling debug must create a run directory under `~/.ksearch/debug/`.
- Each debug run directory must be unique and timestamped.
- The command context must be recorded once at startup.
- Components involved in the command must emit trace events during execution.
- Command completion must write a final result summary with success or failure status.
- Failures must still write enough information to diagnose where the run stopped.

### Logging Detail Requirements

The chosen detail level is:

- metadata plus content summaries
- truncated query, content, prompt, and response excerpts
- no full raw payload dumps by default

This means the logs should show what happened and why, without becoming unreadably large.

### Non-Functional Requirements

- When `--debug` is not enabled, existing CLI behavior should remain unchanged.
- Debug logging should add minimal overhead when disabled.
- Log output should be append-safe and readable while a command is still running.
- The design should reuse standard `logging` where possible instead of inventing a parallel logging system for text logs.

## Approaches Considered

### 1. Unified debug session with standard logging plus structured event sink

Use one root-level debug session manager that:

- creates the per-run directory
- configures `logging` handlers
- writes human-readable logs
- writes structured JSONL events
- exposes helper functions for context and result summaries

Modules continue using `logging.getLogger(__name__)`, while selected workflow points add structured event calls.

Pros:

- matches the existing codebase well
- gives both human-readable and machine-readable artifacts
- keeps instrumentation incremental and targeted
- works for all commands from one root switch

Cons:

- requires adding instrumentation across several modules

### 2. CLI wrapper-only tracing

Add debug behavior only around command entry and exit, with minimal component changes.

Pros:

- smallest code change

Cons:

- does not satisfy the requirement for full component-level process tracing
- weak diagnostic value for search, kbase, rerank, and optimization flows

### 3. Full custom tracing framework

Introduce a bespoke tracing layer with explicit spans, nested contexts, and custom collectors everywhere.

Pros:

- maximum control and detail

Cons:

- too heavy for the current repository
- higher implementation cost and maintenance burden
- duplicates capabilities that standard `logging` already provides well enough here

## Recommended Approach

Use approach 1.

This repository already has clear component boundaries and some existing logger usage. The right move is to add one centralized debug session manager and instrument the key workflow stages, instead of layering a large new tracing framework onto the project.

## CLI Behavior

### Root Flag

The root `Typer` app in `src/ksearch/__main__.py` should accept:

- `--debug`

Expected invocation pattern:

```bash
ksearch --debug search "python asyncio"
ksearch --debug kbase query "rerank model"
ksearch --debug optimize "async cancellation"
```

The debug flag is global, not repeated on each subcommand.

### Default Behavior

Without `--debug`:

- no debug directory is created
- no file handlers are configured
- existing output and error behavior remain unchanged

With `--debug`:

- a debug session is initialized before command execution
- a run directory is created
- command context and events are recorded until the command finishes or fails

## Debug Directory Layout

Each run creates:

```text
~/.ksearch/debug/
  cli-YYYYMMDD-HHMMSS/
    session.log
    context.json
    events.jsonl
    result.json
```

### `session.log`

Purpose:

- human-readable chronological log for direct inspection

Contents:

- timestamps
- log level
- logger name
- event message
- exception tracebacks when present

### `context.json`

Purpose:

- immutable startup context snapshot for the run

Contents:

- raw `argv`
- resolved subcommand name
- current working directory
- process id
- Python version
- start timestamp
- debug directory path
- merged config snapshot when the command uses config

### `events.jsonl`

Purpose:

- structured event stream for grep, `jq`, or later tooling

Each line must be a JSON object with a stable shape:

- `ts`
- `level`
- `component`
- `event`
- `command`
- `elapsed_ms`
- `data`

### `result.json`

Purpose:

- final summary of command outcome

Contents:

- `success`
- `command`
- `started_at`
- `finished_at`
- `elapsed_ms`
- `result_count` when applicable
- `summary`
- `error` when applicable

## Logging Module Design

Add a focused module, for example:

- `src/ksearch/debug_logging.py`

Responsibilities:

- start a debug session
- create the log directory
- configure file handlers
- write `context.json`
- append structured events to `events.jsonl`
- write `result.json`
- expose the active session metadata to instrumented code

Recommended public helpers:

- `start_debug_session(...)`
- `is_debug_enabled()`
- `get_debug_dir()`
- `write_context(...)`
- `log_event(...)`
- `finish_debug_session(...)`

The implementation may use module-level state or `contextvars` to avoid threading session objects through every function call. The important constraint is that non-debug runs stay cheap and debug runs remain globally accessible across components in the current process.

## Instrumentation Boundaries

The project should not try to log every line of code. It should log stable workflow boundaries and decisions.

### CLI Entry and Commands

Instrument:

- root command start
- selected subcommand
- parsed user-facing arguments
- merged config snapshot
- command success/failure
- total command duration

Targets:

- `src/ksearch/__main__.py`
- `src/ksearch/cli/search.py`
- `src/ksearch/cli/optimize.py`
- `src/ksearch/cli/system.py`
- `src/ksearch/cli/kbase.py`

### Search Flow

Instrument:

- cache exact-match attempt and hit count
- cache partial-match attempt and hit count
- whether network search is skipped
- SearXNG query parameters summary
- returned network result count
- filtered/skipped URL count
- conversion success/failure per URL
- cache persistence path per stored result
- final returned result count

Targets:

- `src/ksearch/searching/service.py`
- `src/ksearch/web/search_client.py`
- `src/ksearch/cache_layer/service.py`
- `src/ksearch/web/extractor.py`

### kbase Flow

Instrument:

- kbase mode and embedding config on initialization
- ingest file/directory start and finish
- file count and chunk count
- query parameters
- whether hybrid retrieval is used
- BM25 hit count
- vector hit count
- merged candidate count
- final top-k count

Targets:

- `src/ksearch/kbase.py`
- `src/ksearch/knowledge/service.py`
- `src/ksearch/knowledge/vector_store.py`

### Iterative, Optimization, and Rerank Flow

Instrument:

- iterative query type
- sufficiency score and threshold
- early-sufficient return vs web fallback
- iteration count and stop reason
- optimization iteration number
- evaluator action and confidence
- remaining gaps summary
- rerank model name
- per-document rerank score with content preview

Targets:

- `src/ksearch/iterative_flow/engine.py`
- `src/ksearch/content_optimization/optimizer.py`
- `src/ksearch/content_optimization/evaluator.py`
- `src/ksearch/knowledge/reranker.py`

### External Dependency Boundaries

Instrument:

- request target URL or service endpoint
- key request parameters summary
- HTTP status code
- request duration
- model name where relevant
- exception type and message on failure

Do not log full raw responses by default.

## Content Truncation Rules

To keep logs readable while still useful, apply truncation consistently.

Recommended limits:

- query text: full unless extremely long
- content preview: first 500 characters
- prompt preview: first 1000 characters
- LLM response preview: first 1000 characters
- result lists: first 5 item summaries

If data is truncated, the log entry should make that explicit, either by:

- adding a `truncated: true` marker in structured data, or
- appending a short marker in text logs

## Error Handling

Debug mode must be resilient:

- logging failures should not crash the main command unless session initialization itself fails catastrophically
- command exceptions should still be logged before the CLI exits
- `result.json` should be written on both success and failure paths whenever possible

If a command exits early through `typer.Exit`, the result summary should still indicate:

- command name
- exit status
- elapsed time
- last known summary

## Security and Privacy

This repository currently does not appear to use secret-bearing CLI flags widely, but the debug design should still avoid assuming all future config is safe to dump unfiltered.

The debug session manager should support a small redaction policy for obvious sensitive keys such as:

- `token`
- `api_key`
- `password`
- `secret`

Paths, model names, URLs, and non-secret config values should remain visible because they are operationally important for debugging.

## Testing Strategy

Implementation must follow TDD.

### CLI-Level Tests

Add tests proving:

- `ksearch --debug search ...` creates a debug directory
- `ksearch --debug optimize ...` creates a debug directory
- `ksearch --debug kbase query ...` creates a debug directory
- no debug directory is created when `--debug` is not passed

### Artifact Tests

Add tests proving the created directory contains:

- `session.log`
- `context.json`
- `events.jsonl`
- `result.json`

Add tests proving:

- `context.json` includes command metadata
- `result.json` includes success/failure status
- `events.jsonl` contains command start/finish entries

### Behavior Tests

Add targeted tests for:

- config snapshot logging
- event truncation behavior for large content
- failure-path logging when a command raises an exception

### Instrumentation Tests

Do not hard-code every message string.

Instead, verify:

- event presence
- component names
- stable event keys
- summary fields

This keeps tests focused on behavior and file structure rather than brittle wording.

## Rollout Plan

1. Add root `--debug` support and debug session manager.
2. Add CLI-level command lifecycle logging and artifact creation tests.
3. Instrument search flow.
4. Instrument kbase flow.
5. Instrument iterative, optimization, and rerank flow.
6. Add failure-path and truncation tests.
7. Update CLI help text or docs if needed after behavior is stable.

## Success Criteria

This work is complete when:

- every CLI command can be run with `ksearch --debug ...`
- a per-run directory is created under `~/.ksearch/debug/cli-<time>/`
- logs capture the full high-level execution path across participating components
- summaries and truncated content previews are present
- failure runs remain diagnosable
- tests cover root flag behavior, artifact creation, and key event emission
