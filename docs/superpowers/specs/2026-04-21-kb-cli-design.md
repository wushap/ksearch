# KB CLI 工具设计文档

> Superseded by `docs/superpowers/specs/2026-04-28-ksearch-iterative-search-design.md` for the current `ksearch` architecture.

> 个人知识库 + 网络搜索 Python CLI 工具

## 概述

`kb` 是一个结合本地知识库缓存和网络搜索的 CLI 工具。用户输入关键词后，优先从本地 SQLite 索引查找缓存内容，必要时补充网络搜索结果，所有结果通过 markitdown 转换为 Markdown 格式存储。

**核心特性**：
- 本地缓存优先，减少重复下载
- 自动转换并存储所有搜索结果
- 支持时间范围过滤（day/week/month/year）
- 结构化 Markdown 输出 + 文件路径输出格式
- uv 管理项目依赖

---

## 1. 数据流设计

```
用户输入关键词
    │
    ▼
┌─────────────────┐
│  加载配置       │ ←── JSON 配置 + CLI 参数合并
│  初始化组件     │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  SQLite 索引    │ ←── 查询匹配模式
│  精确匹配?      │
│  keyword=?      │
└─────────────────┘
    │
    ├─ 完全匹配 → 直接返回缓存内容（不发起网络搜索）
    │
    ▼ 部分匹配 / 无匹配
┌─────────────────┐
│  输出部分匹配   │ ←── 先输出部分匹配的缓存结果（标记 [cached]）
│  的缓存内容     │
└─────────────────┘
    │
    ▼ 同时发起
┌─────────────────┐
│  SearXNG API    │ ←── 网络搜索补充
│  /search?q=...  │
│  &time_range=   │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  结果去重       │ ←── 跳过已缓存的 URL
│  遍历新 URL     │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  markitdown     │ ←── 并行转换 URL → Markdown
│  .convert(url)  │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  缓存存储       │ ←── sha256(url).md + SQLite 索引
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  合并输出       │ ←── 缓存结果 + 网络结果（去重）
│  stdout         │
└─────────────────┘
```

**匹配规则**：
| 匹配类型 | 查询条件 | 行为 |
|----------|----------|------|
| 完全匹配 | `keyword = ?` | 仅返回缓存，不搜索网络 |
| 部分匹配 | `keyword LIKE '%?%'` | 先输出缓存，同时发起网络搜索 |
| 无匹配 | 无结果 | 直接发起网络搜索 |

---

## 2. SQLite 索引结构

```sql
CREATE TABLE cache (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,           -- 原始 URL
    file_hash TEXT NOT NULL,            -- sha256(url) 文件名
    file_path TEXT NOT NULL,            -- 完整存储路径
    title TEXT,                         -- 页面标题
    keyword TEXT NOT NULL,              -- 搜索关键词
    cached_date TEXT,                   -- 缓存保存日期
    published_date TEXT,                -- 内容发布日期（来自 SearXNG）
    engine TEXT                         -- 来源引擎
);

-- 索引
CREATE INDEX idx_keyword ON cache(keyword);
CREATE INDEX idx_keyword_exact ON cache(keyword);
CREATE INDEX idx_url ON cache(url);
CREATE INDEX idx_cached_date ON cache(cached_date);
```

---

## 3. 输出格式设计

### Markdown 格式（默认）

```markdown
# 搜索结果: "关键词"

## 缓存结果 (2条)

### 1. [cached] 页面标题
- **URL**: https://example.com/article
- **来源**: google
- **缓存时间**: 2026-04-21 10:30:00
- **文件路径**: ~/.kb/store/a1b2c3.md

---

（完整的 Markdown 转换内容）

---

### 2. [cached] 另一个标题
...

---

## 网络搜索结果 (8条)

### 3. 新搜索标题
- **URL**: https://newsite.com/page
- **来源**: duckduckgo, wikipedia
- **转换时间**: 2026-04-21 12:00:00
- **文件路径**: ~/.kb/store/d4e5f6.md

---

（完整的 Markdown 转换内容）

---

...

总计: 10条结果
```

### 路径格式（`--format=path`）

```
~/.kb/store/a1b2c3.md
~/.kb/store/b2c3d4.md
~/.kb/store/c3d4e5.md
~/.kb/store/d4e5f6.md
```

---

## 4. 配置文件结构

路径：`~/.kb/config.json`

```json
{
  "searxng_url": "http://localhost:48888",
  "store_dir": "~/.kb/store",
  "index_db": "~/.kb/index.db",
  "max_results": 10,
  "timeout": 30,
  "format": "markdown",
  "time_range": "",
  "no_cache": false,
  "only_cache": false,
  "verbose": false
}
```

| 配置字段 | CLI 参数 | 说明 | 默认值 |
|----------|----------|------|--------|
| `searxng_url` | `--searxng-url` | SearXNG 实例地址 | `http://localhost:48888` |
| `store_dir` | `--store-dir` | 缓存存储目录 | `~/.kb/store` |
| `index_db` | `--index-db` | SQLite 索引路径 | `~/.kb/index.db` |
| `max_results` | `--max-results` | 最大结果数 | `10` |
| `timeout` | `--timeout` | 网络请求超时秒数 | `30` |
| `format` | `--format` | 输出格式 | `markdown` |
| `time_range` | `--time-range` | 时间范围 | 空（不限） |
| `no_cache` | `--no-cache` | 强制网络搜索 | `false` |
| `only_cache` | `--only-cache` | 仅查本地缓存 | `false` |
| `verbose` | `--verbose` | 详细输出 | `false` |

**优先级**：CLI 参数 > 配置文件 > 程序默认值

---

## 5. CLI 命令结构

```bash
kb search "关键词" [选项]
```

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--format` | `-f` | 输出格式：`markdown` / `path` | `markdown` |
| `--time-range` | `-t` | 时间范围：`day` / `week` / `month` / `year` | 不限 |
| `--max-results` | `-m` | 最大结果数 | `10` |
| `--searxng-url` | `-s` | SearXNG 实例地址 | 配置值 |
| `--store-dir` | `-d` | 缓存存储目录 | 配置值 |
| `--index-db` | | SQLite 索引路径 | 配置值 |
| `--timeout` | | 网络请求超时秒数 | 配置值 |
| `--no-cache` | | 强制网络搜索 | `false` |
| `--only-cache` | | 仅查本地缓存 | `false` |
| `--verbose` | `-v` | 详细处理信息 | `false` |
| `--help` | `-h` | 显示帮助 | |

**使用示例**：

```bash
# 基本搜索
kb search "Python asyncio 教程"

# 仅返回文件路径
kb search "Rust 并发编程" -f path

# 搜索一周内的内容
kb search "AI 最新进展" -t week -m 5

# 强制重新搜索
kb search "已有关键词" --no-cache

# 仅查看本地缓存
kb search "已有关键词" --only-cache
```

---

## 6. 项目结构与依赖

```
kb/
├── pyproject.toml          # uv 项目配置
├── README.md
├── src/
│   └── kb/
│       ├── __init__.py     # 包入口，版本信息
│       ├── __main__.py     # CLI 入口点 `kb` 命令
│       ├── config.py       # 配置管理
│       ├── cache.py        # SQLite 索引 + 文件存储
│       ├── searxng.py      # SearXNG API 客户端
│       ├── converter.py    # markitdown 转换封装
│       ├── search.py       # 搜索流程编排
│       ├── output.py       # 输出格式化
│       └── models.py       # 数据结构定义
│
└── tests/
    ├── test_config.py
    ├── test_cache.py
    ├── test_searxng.py
    └── test_search.py
```

**pyproject.toml**：

```toml
[project]
name = "kb"
version = "0.1.0"
description = "Personal knowledge base with web search - CLI tool"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.12.0",
    "rich>=13.0.0",
    "requests>=2.28.0",
    "markitdown[all]>=0.0.1",
]

[project.scripts]
kb = "kb.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
]
```

---

## 7. 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| SearXNG 连接失败 | 提示错误，返回本地缓存（如有），退出码 1 |
| markitdown 转换失败 | 警告日志，跳过该 URL，继续其他 |
| URL 已缓存但文件丢失 | 删除索引记录，重新下载 |
| 网络请求超时 | 提示超时，返回本地缓存（如有），退出码 1 |
| 配置文件不存在 | 自动创建默认配置 |
| 配置文件格式错误 | 提示错误，使用默认值继续 |
| 存储目录不存在 | 自动创建 |
| SQLite 索引损坏 | 提示错误，可重建索引 |

**错误输出格式**（rich）：

```
⚠ Warning: Failed to convert https://bad-url.com (timeout)
✓ 9 of 10 results cached successfully
```

---

## 8. 模块核心逻辑

### config.py

```python
def load_config(config_path: str = "~/.kb/config.json") -> dict
def merge_config(cli_args: dict, file_config: dict, defaults: dict) -> dict
def init_default_config(config_path: str) -> None
```

### cache.py

```python
class CacheManager:
    def __init__(self, db_path: str, store_dir: str)
    def exact_match(self, keyword: str) -> list[CacheEntry]
    def partial_match(self, keyword: str, time_range: str = None) -> list[CacheEntry]
    def save(self, url: str, content: str, keyword: str, metadata: dict) -> str
    def exists(self, url: str) -> bool
    def get_file_path(self, url: str) -> str
    def cleanup_missing_files(self) -> None
```

### searxng.py

```python
class SearXNGClient:
    def __init__(self, base_url: str, timeout: int = 30)
    def search(self, query: str, time_range: str = None, max_results: int = 10) -> list[SearchResult]
```

### converter.py

```python
class ContentConverter:
    def __init__(self, timeout: int = 30)
    def convert_url(self, url: str) -> str
```

### search.py

```python
class SearchEngine:
    def __init__(self, cache: CacheManager, searxng: SearXNGClient, converter: ContentConverter)
    def search(self, keyword: str, options: dict) -> list[ResultEntry]
```

### output.py

```python
def format_markdown(results: list[ResultEntry], keyword: str) -> str
def format_paths(results: list[ResultEntry]) -> str
def print_output(results: list[ResultEntry], format: str, keyword: str, verbose: bool)
```

### models.py

```python
@dataclass
class CacheEntry:
    url: str
    file_path: str
    title: str
    keyword: str
    cached_date: str
    engine: str
    content: str

@dataclass
class SearchResult:
    url: str
    title: str
    content: str
    engine: str
    published_date: str

@dataclass
class ResultEntry:
    url: str
    title: str
    content: str
    file_path: str
    cached: bool
    source: str
    cached_date: str
```

---

## 9. 搜索流程时序

| 时间 | 动作 | 输出 |
|------|------|------|
| T+0s | 用户输入、加载配置、初始化组件 | |
| T+0.1s | 查询 SQLite（精确 + 部分匹配） | |
| T+0.2s | 判断匹配类型，输出缓存结果 | `[cached] 结果1...` |
| T+0.2s | 发起 SearXNG 请求（部分/无匹配时） | |
| T+2s | SearXNG 返回，去重已缓存 URL | |
| T+2s | 并行转换新 URL（ThreadPoolExecutor） | |
| T+10s | 保存文件、更新索引、输出网络结果 | `结果3... 结果4...` |
| T+10s | 输出统计、退出 | `✓ 总计: 10条结果` |

---

## 10. 首次运行初始化

```
kb search "关键词"（首次）
    │
    ├─ ~/.kb/ 不存在 → 创建
    ├─ ~/.kb/config.json 不存在 → 创建默认配置
    ├─ ~/.kb/store/ 不存在 → 创建
    ├─ ~/.kb/index.db 不存在 → 创建数据库 + 表
    │
    ▼
继续正常搜索流程
```

---

## 11. 本地缓存时间过滤

当用户指定 `--time-range` 时，本地缓存查询也按时间过滤：

```python
# 一周内的缓存
query = """
SELECT * FROM cache 
WHERE keyword LIKE ? 
AND cached_date >= datetime('now', '-7 days')
"""
```

**时间范围映射**：
| CLI 参数 | SQLite 条件 |
|----------|-------------|
| `day` | `cached_date >= datetime('now', '-1 day')` |
| `week` | `cached_date >= datetime('now', '-7 days')` |
| `month` | `cached_date >= datetime('now', '-30 days')` |
| `year` | `cached_date >= datetime('now', '-365 days')` |
| 空 | 无过滤 |
