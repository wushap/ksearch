---
name: ksearch
description: Use ksearch CLI to search personal knowledge base with web search - combines local cache and SearXNG network search
---

# ksearch Skill

Use this skill when the user wants to search for information using the personal knowledge base tool that combines local caching and web search.

## When to Use

Trigger this skill when:
- User asks to search for information: "search for X", "查找 X", "搜索 X"
- User wants to use ksearch explicitly: "用 ksearch 搜索", "ksearch X"
- User wants cached/web search results: "搜索并缓存", "知识库搜索"

## What This Skill Does

ksearch is a CLI tool that:
1. **Searches local cache first** - exact keyword match returns cached results
2. **Supplements with web search** - partial match triggers SearXNG search
3. **Converts and stores** - web results converted to Markdown and cached
4. **Returns structured output** - Markdown or file path format

## Usage

The CLI is installed at the project directory. Use via uv:

```bash
# Basic search (from project directory)
uv run ksearch "<keyword>"

# Search with options (options BEFORE keyword)
uv run ksearch --verbose "<keyword>"
uv run ksearch --only-cache "<keyword>"
uv run ksearch --no-cache "<keyword>"
uv run ksearch --format path "<keyword>"
uv run ksearch --time-range week "<keyword>"
uv run ksearch --max-results 5 "<keyword>"
```

**IMPORTANT**: Options must come BEFORE the keyword argument.

## Parameters

| Option | Short | Description |
|--------|-------|-------------|
| `--format` | `-f` | Output format: `markdown` (default) or `path` |
| `--time-range` | `-t` | Filter by time: `day`, `week`, `month`, `year` |
| `--max-results` | `-m` | Maximum number of results |
| `--searxng-url` | `-s` | SearXNG instance URL (default: localhost:48888) |
| `--store-dir` | `-d` | Cache storage directory |
| `--no-cache` | | Force network search, skip cache |
| `--only-cache` | | Only search local cache |
| `--verbose` | `-v` | Show detailed output |

## Examples

```bash
# Search for Python (will use cache if exists)
uv run ksearch python

# Force fresh web search
uv run ksearch --no-cache python

# Only check local cache
uv run ksearch --only-cache python

# Search recent results (last week)
uv run ksearch --time-range week AI

# Get file paths only
uv run ksearch --format path python

# Verbose search with limit
uv run ksearch -v --max-results 3 rust
```

## Output Format

### Markdown (default)
```markdown
# 搜索结果: "keyword"

## 缓存结果 (N条)
### 1. [cached] Title
- **URL**: https://...
- **来源**: google
- **缓存时间**: 2026-04-22
- **文件路径**: ~/.ksearch/store/xxx.md
---

(content)

## 网络搜索结果 (M条)
### N. Title
...

总计: X条结果
```

### Path format (`--format path`)
```
~/.ksearch/store/abc123.md
~/.ksearch/store/def456.md
```

## Workflow

When user requests a search:

1. **Check if uv/ksearch available** - verify project exists
2. **Run search command** - use Bash tool with uv run
3. **Parse output** - return results to user
4. **Optionally read cached files** - if user wants full content

## Integration Notes

- Requires SearXNG instance running (default: http://localhost:48888)
- Cache stored at `~/.ksearch/store/`
- **Keyword index files at `~/.ksearch/store/_index/`** - JSON files per keyword for direct lookup
- Index database at `~/.ksearch/index.db` (SQLite backup)
- Config file at `~/.ksearch/config.json`

### Keyword Index Structure

Each keyword has its own JSON index file:

```json
{
  "keyword": "python",
  "entries": [
    {"url": "...", "file_hash": "abc123", "title": "...", "cached_date": "2026-04-25"}
  ]
}
```

Browse `_index/` directory to quickly find cached content by keyword without querying SQLite.

## Error Handling

- If SearXNG unavailable: returns cache results only (if any)
- If no results: outputs "无结果"
- CLI errors show user-friendly messages

## Quick Reference

| User Request | Command |
|--------------|---------|
| "search X" | `uv run ksearch X` |
| "cache only" | `uv run ksearch --only-cache X` |
| "fresh search" | `uv run ksearch --no-cache X` |
| "recent (week)" | `uv run ksearch -t week X` |
| "file paths" | `uv run ksearch -f path X` |
| "detailed" | `uv run ksearch -v X` |

## Optimal Configuration Recommendations

Based on testing, these configurations perform best:

### Quick Search (Recommended Default)

```bash
uv run ksearch --max-results 5 "<keyword>"
```

- **5 results**: ~2 seconds, balances speed and coverage
- Best for everyday searches

### Deep Search

```bash
uv run ksearch --max-results 10 --timeout 60 "<keyword>"
```

- **10 results**: ~8 seconds, comprehensive coverage
- Good for research or learning new topics

### Performance Reference

| max_results | Actual Results | Time | Use Case |
|-------------|----------------|------|----------|
| 3 | ~2 | 6s | Quick check |
| 5 | ~4 | 2s | **Daily recommended** |
| 10 | ~7 | 8s | Deep research |

### Content Quality

After cleaning, content ratio is **~81%** (vs ~12% before):
- Navigation boilerplate removed
- Fallback notices filtered
- Short/redirect pages skipped
- Code blocks and paragraphs preserved

### Recommended Config File

```json
{
  "max_results": 5,
  "timeout": 30,
  "format": "markdown"
}
```

Store in `~/.ksearch/config.json` for consistent defaults.