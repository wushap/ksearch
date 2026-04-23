# KB - 个人知识库 CLI 工具

结合本地知识库缓存和网络搜索的 Python CLI 工具。

## 特性

- **缓存优先搜索**：精确匹配关键词直接返回本地缓存结果，无需网络请求
- **智能补充**：部分匹配时自动发起网络搜索补充新结果
- **自动转换存储**：所有网络搜索结果自动转换为 Markdown 格式并缓存
- **时间范围过滤**：支持 `day`/`week`/`month`/`year` 时间范围搜索
- **灵活输出**：支持结构化 Markdown 输出或纯文件路径输出
- **配置灵活**：JSON 配置文件 + CLI 参数覆盖

## 安装

```bash
# 使用 uv 安装依赖
uv sync

# 或全局安装
uv pip install -e .
```

## 使用

### 基本搜索

```bash
kb search "关键词"
```

### 仅搜索本地缓存

```bash
kb search "关键词" --only-cache
```

### 强制网络搜索（忽略缓存）

```bash
kb search "关键词" --no-cache
```

### 时间范围搜索

```bash
kb search "AI 最新进展" --time-range week    # 一周内
kb search "技术趋势" --time-range month      # 一个月内
```

### 输出文件路径

```bash
kb search "关键词" --format path
```

### 详细输出

```bash
kb search "关键词" --verbose
```

## 配置

配置文件位于 `~/.kb/config.json`：

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

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `searxng_url` | SearXNG 实例地址 | `http://localhost:48888` |
| `store_dir` | Markdown 文件存储目录 | `~/.kb/store` |
| `index_db` | SQLite 索引数据库路径 | `~/.kb/index.db` |
| `max_results` | 最大搜索结果数 | `10` |
| `timeout` | 网络请求超时（秒） | `30` |
| `format` | 输出格式 (`markdown`/`path`) | `markdown` |

## CLI 参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--format` | `-f` | 输出格式 |
| `--time-range` | `-t` | 时间范围 |
| `--max-results` | `-m` | 最大结果数 |
| `--searxng-url` | `-s` | SearXNG 地址 |
| `--store-dir` | `-d` | 存储目录 |
| `--no-cache` | | 强制网络搜索 |
| `--only-cache` | | 仅搜索缓存 |
| `--verbose` | `-v` | 详细输出 |

## 项目结构

```
kb/
├── src/kb/
│   ├── __main__.py    # CLI 入口
│   ├── models.py      # 数据结构
│   ├── config.py      # 配置管理
│   ├── cache.py       # SQLite + 文件缓存
│   ├── searxng.py     # SearXNG API
│   ├── converter.py   # markitdown 转换
│   ├── search.py      # 搜索编排
│   └── output.py      # 输出格式化
└── tests/             # 单元测试
```

## 搜索流程

1. **查询本地缓存**
   - 精确匹配 → 直接返回缓存结果
   - 部分匹配 → 输出缓存 + 发起网络搜索

2. **网络搜索**
   - 调用 SearXNG API
   - 去重已缓存 URL

3. **转换存储**
   - 使用 markitdown 转换为 Markdown
   - 存储到 `~/.kb/store/`
   - 更新 SQLite 索引

4. **输出结果**
   - Markdown 格式：结构化输出 + 元数据
   - Path 格式：仅输出文件路径

## 依赖

- Python 3.10+
- [SearXNG](https://github.com/searxng/searxng) 实例
- [markitdown](https://github.com/microsoft/markitdown) (Microsoft)

## 开发

```bash
# 安装开发依赖
uv sync

# 运行测试
uv run pytest tests/ -v

# 运行 CLI
uv run kb search "test"
```

## License

MIT