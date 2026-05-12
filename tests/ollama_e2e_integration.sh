#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
SEARXNG_URL="${SEARXNG_URL:-http://localhost:48888}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text:latest}"
BAD_MODEL="${BAD_MODEL:-fredrezones55/qwen3.5-opus:9b}"
EMBED_DIMENSION="${EMBED_DIMENSION:-768}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TMP_ROOT="$(mktemp -d)"
KB_DIR="$TMP_ROOT/kbase"
NOTES_DIR="$TMP_ROOT/notes"
RESULTS_DIR="${RESULTS_DIR:-/tmp/ksearch-ollama-e2e-results}"
REPORT_PATH="$RESULTS_DIR/ollama_e2e_report_${TIMESTAMP}.md"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

mkdir -p "$KB_DIR" "$NOTES_DIR"
mkdir -p "$RESULTS_DIR"

log() {
  printf '[ollama-e2e] %s\n' "$1"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'missing required command: %s\n' "$1" >&2
    exit 1
  }
}

check_service() {
  local name="$1"
  local url="$2"
  curl -fsS "$url" >/dev/null
  log "$name reachable: $url"
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    printf 'assertion failed: %s\n' "$label" >&2
    printf 'expected to find: %s\n' "$needle" >&2
    exit 1
  fi
}

run_and_capture() {
  local label="$1"
  shift
  log "$label"
  "$@"
}

require_cmd curl
require_cmd uv

check_service "Ollama" "$OLLAMA_URL/api/tags"
check_service "SearXNG" "$SEARXNG_URL/search?q=test&format=json"

OLLAMA_TAGS="$(curl -fsS "$OLLAMA_URL/api/tags")"
assert_contains "$OLLAMA_TAGS" "$EMBED_MODEL" "embedding model must be available in Ollama tags"
assert_contains "$OLLAMA_TAGS" "$BAD_MODEL" "negative-case model should be available in Ollama tags"

cat > "$NOTES_DIR/asyncio-en.md" <<'EOF'
# Python Asyncio Cancellation Guide

In Python asyncio, task cancellation propagates by raising CancelledError inside the coroutine. Good practice is to use try/finally for cleanup and re-raise CancelledError after cleanup.
EOF

cat > "$NOTES_DIR/asyncio-zh.md" <<'EOF'
# Python 异步取消说明

在 Python asyncio 中，任务取消通常通过在协程内部抛出 CancelledError 传播。推荐使用 try/finally 做清理，并在清理后继续抛出 CancelledError。
EOF

cat > "$NOTES_DIR/asyncio-mixed.md" <<'EOF'
# Asyncio Cleanup Checklist

When a coroutine is cancelled, release database connections, close files, and preserve cancellation semantics. 异步任务被取消时，需要清理资源并避免吞掉取消异常。
EOF

cd "$PROJECT_DIR"

RESET_OUTPUT="$(run_and_capture "reset temporary kbase" \
  uv run ksearch kbase reset --confirm \
  --mode chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL")"
assert_contains "$RESET_OUTPUT" "kbase reset" "kbase reset should succeed"

INGEST_OUTPUT="$(run_and_capture "ingest multilingual fixture notes" \
  uv run ksearch kbase ingest "$NOTES_DIR" \
  --mode chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --source e2e)"
assert_contains "$INGEST_OUTPUT" "Ingested 3 chunks" "kbase ingest should ingest all fixture notes"

KB_SEARCH_EN="$(run_and_capture "ksearch search english keyword" \
  uv run ksearch kbase query "asyncio cancellation propagation" \
  --mode chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --top-k 3)"
assert_contains "$KB_SEARCH_EN" "Python Asyncio Cancellation" "english ksearch search should hit english fixture"

KB_SEARCH_ZH="$(run_and_capture "ksearch search chinese keyword" \
  uv run ksearch kbase query "异步取消传播 清理资源" \
  --mode chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --top-k 3)"
assert_contains "$KB_SEARCH_ZH" "Python 异步取消说明" "chinese ksearch search should hit chinese fixture"

KB_SEARCH_MIXED="$(run_and_capture "ksearch search mixed keyword" \
  uv run ksearch kbase query "Python 异步 cancellation cleanup" \
  --mode chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --top-k 3)"
assert_contains "$KB_SEARCH_MIXED" "Asyncio Cleanup Checklist" "mixed ksearch search should hit mixed fixture"

SEARCH_CACHE_EN="$(run_and_capture "search only-cache english keyword" \
  uv run ksearch search "asyncio cancellation propagation" \
  --kbase chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --only-cache)"
assert_contains "$SEARCH_CACHE_EN" "缓存结果 (3条)" "only-cache english search should return three kbase-backed results"

SEARCH_CACHE_ZH="$(run_and_capture "search only-cache chinese keyword" \
  uv run ksearch search "异步取消传播 清理资源" \
  --kbase chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --only-cache)"
assert_contains "$SEARCH_CACHE_ZH" "缓存结果 (3条)" "only-cache chinese search should return three kbase-backed results"

ITERATIVE_EN="$(run_and_capture "iterative english search" \
  uv run ksearch search "python asyncio cancellation best practices" \
  --kbase chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --iterative \
  --max-results 2 \
  --timeout 15)"
assert_contains "$ITERATIVE_EN" "总计:" "iterative english search should produce formatted results"

ITERATIVE_ZH="$(run_and_capture "iterative chinese search" \
  uv run ksearch search "Python 异步取消 最佳实践" \
  --kbase chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$EMBED_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --iterative \
  --max-results 2 \
  --timeout 15)"
assert_contains "$ITERATIVE_ZH" "总计:" "iterative chinese search should produce formatted results"

BAD_MODEL_EMBED="$(curl -sS "$OLLAMA_URL/api/embeddings" -d "{\"model\":\"$BAD_MODEL\",\"prompt\":\"test embedding\"}")"
assert_contains "$BAD_MODEL_EMBED" "does not support embeddings" "negative model should fail the embedding endpoint"

BAD_MODEL_SEARCH="$(run_and_capture "search with non-embedding model negative case" \
  uv run ksearch search "asyncio cancellation propagation" \
  --kbase chroma \
  --kbase-dir "$KB_DIR" \
  --embedding-model "$BAD_MODEL" \
  --embedding-dimension "$EMBED_DIMENSION" \
  --ollama-url "$OLLAMA_URL" \
  --only-cache 2>&1 || true)"
assert_contains "$BAD_MODEL_SEARCH" "does not support embeddings" "negative search should fail loudly for non-embedding model"

cat > "$REPORT_PATH" <<EOF
# Ollama E2E Report

- Time: $TIMESTAMP
- Ollama URL: $OLLAMA_URL
- SearXNG URL: $SEARXNG_URL
- Embedding model: $EMBED_MODEL
- Negative model: $BAD_MODEL
- Embedding dimension: $EMBED_DIMENSION
- Temporary kbase dir: $KB_DIR

## kbase Search EN

\`\`\`
$KB_SEARCH_EN
\`\`\`

## kbase Search ZH

\`\`\`
$KB_SEARCH_ZH
\`\`\`

## kbase Search Mixed

\`\`\`
$KB_SEARCH_MIXED
\`\`\`

## Search Only Cache EN

\`\`\`
$SEARCH_CACHE_EN
\`\`\`

## Search Only Cache ZH

\`\`\`
$SEARCH_CACHE_ZH
\`\`\`

## Iterative EN

\`\`\`
$ITERATIVE_EN
\`\`\`

## Iterative ZH

\`\`\`
$ITERATIVE_ZH
\`\`\`

## Negative Embedding API Response

\`\`\`
$BAD_MODEL_EMBED
\`\`\`

## Negative Search Output

\`\`\`
$BAD_MODEL_SEARCH
\`\`\`
EOF

log "report written to $REPORT_PATH"
printf '%s\n' "$REPORT_PATH"
