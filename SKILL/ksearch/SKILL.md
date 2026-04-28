---
name: ksearch
description: Use when the user wants to search topics, inspect cached material, query the local knowledge base, or run KB-assisted web search with the ksearch CLI.
---

# ksearch Skill

Use this skill when the user wants to search, inspect cached material, query the knowledge base, or run KB-assisted iterative search.

## Trigger

Use this skill when the user asks to:

- 搜索某个主题、问题、教程、资料
- 用 `ksearch` / `kb` 查内容
- 只查缓存、只查知识库、强制重新联网搜索
- 把搜索结果保存并复用到本地知识库
- search a topic, article, tutorial, or reference
- run `ksearch` for cache, KB, or web retrieval
- force fresh web search or limit results to local content
- ingest local files into the knowledge base

## Command Choice

Pick the command by intent:

- 普通搜索：`uv run ksearch search "<query>"`
- 只查网页缓存：`uv run ksearch search "<query>" --only-cache`
- 强制联网：`uv run ksearch search "<query>" --no-cache`
- 语义知识库检索：`uv run ksearch kb search "<query>" --mode chroma`
- KB-first 迭代搜索：`uv run ksearch search "<query>" --kb chroma --iterative`
- 导入本地文档到 KB：`uv run ksearch kb ingest <path> --kb-dir <dir> --source <label>`

## Default Workflow

When the user asks to "search X", use this order:

1. If they explicitly want KB semantics, use `kb search` or `search --kb`.
2. If they want fresh web results, use `search --no-cache`.
3. If they want reusable results and KB augmentation, use `search --kb ... --iterative`.
4. If they only want existing local content, use `search --only-cache`.

## Core Commands

```bash
# Standard search
uv run ksearch search "python asyncio"

# Cache only
uv run ksearch search "python asyncio" --only-cache

# Force web search
uv run ksearch search "python asyncio tutorial" --no-cache --max-results 5

# KB semantic search
uv run ksearch kb search "asyncio cancellation" --mode chroma --kb-dir ~/.ksearch/kb

# Iterative KB-first search
uv run ksearch search "asyncio cancellation" --kb chroma --kb-dir ~/.ksearch/kb --iterative

# Ingest local docs into KB
uv run ksearch kb ingest ~/notes --kb-dir ~/.ksearch/kb --source logseq
```

## Important Options

- `--format path`: return only cached file paths
- `--time-range week|month|year`: restrict web search time window
- `--max-results N`: limit web results
- `--timeout N`: network/conversion timeout
- `--kb chroma|qdrant|none`: enable KB search mode
- `--kb-dir <dir>`: choose the KB storage directory explicitly
- `--qdrant-url <url>`: choose the Qdrant server when using qdrant mode
- `--iterative`: use KB-first sufficiency-driven search
- `--verbose`: show path selection and result counts

## Output Semantics

`search` output is grouped into:

- `缓存结果`: local KB results or previously cached web material
- `网络搜索结果`: newly fetched web pages in the current run

Interpretation rules:

- `URL` is the original web URL when available
- `文件路径` is the local cached Markdown path
- `来源` identifies KB or web origin

## KB Notes

- `search --kb ...` mixes KB recall into the normal search flow
- `kb search ...` is KB-only semantic retrieval
- `search --only-cache --kb ... --kb-dir ...` should be used when the user wants local-only results including KB content
- `--kb-dir` matters; if omitted, commands may read or write a different KB than expected

## Iterative Search Notes

Use iterative search when:

- the user wants KB-first retrieval with web expansion
- local notes are likely incomplete
- the user wants results to become reusable in later searches

Behavior:

1. Search KB first
2. Score sufficiency
3. If insufficient, fetch web pages
4. Convert to Markdown, cache locally, ingest into KB
5. Return deduplicated combined results

## Troubleshooting

- If `search --no-cache` returns no results, check `uv run ksearch health`
- If KB results are unexpectedly empty, verify `--kb-dir`
- If iterative search is noisy, inspect the cached Markdown files under `~/.ksearch/store/`
- If the user wants raw file inspection, rerun with `--format path`

## Good Defaults

For most interactive use:

```bash
uv run ksearch search "<query>" --max-results 5 --timeout 15
```

For KB-assisted research:

```bash
uv run ksearch search "<query>" --kb chroma --kb-dir ~/.ksearch/kb --iterative --max-results 3 --timeout 15
```
