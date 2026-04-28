# ksearch

结合本地缓存、知识库检索和网络搜索的 Python CLI 工具。

## 特性

- 缓存优先的网页搜索，避免重复抓取和转换
- 基于 Chroma 或 Qdrant 的知识库语义检索
- 可选的迭代式 KB-first 搜索：先查 KB，不足时再受限扩展网页并回灌 KB
- 自动将网页内容转换为 Markdown 并写入本地缓存
- 支持 Markdown 输出和纯路径输出
- JSON 配置文件 + CLI 参数覆盖

## 安装

```bash
uv sync
```

可选依赖：

```bash
uv pip install -e ".[qdrant]"
uv pip install -e ".[ollama]"
uv pip install -e ".[crawl4ai]"
uv pip install -e ".[all]"
```

## 基本使用

标准搜索命令使用 `search` 子命令：

```bash
ksearch search "python asyncio"
```

常见选项：

```bash
ksearch search "rust async" --only-cache
ksearch search "agent memory" --no-cache
ksearch search "latest ai trends" --time-range week --max-results 5
ksearch search "python asyncio" --format path
ksearch search "vector database" --verbose
```

## 知识库搜索

启用 KB 检索：

```bash
ksearch search "task cancellation" --kb chroma
```

只做知识库操作时使用 `kb` 子命令：

```bash
ksearch kb ingest ~/notes --source logseq --verbose
ksearch kb ingest ~/docs/readme.md --source manual
ksearch kb search "异步编程最佳实践" --top-k 5
ksearch kb list
ksearch kb delete ~/old-notes/test.md
ksearch kb clear --confirm
ksearch kb reset --confirm --embedding-model nomic-embed-text --embedding-dimension 768
```

## 迭代式 KB-first 搜索

当你希望优先利用本地知识库，不足时再自动扩展网页结果并回灌 KB，可使用：

```bash
ksearch search "how does asyncio cancellation propagate" --kb chroma --iterative
```

迭代模式行为：

1. 判断查询更偏向事实型还是探索型
2. 先做 KB 搜索并计算充分性分数
3. 若结果不足，则抓取新的网页结果
4. 将网页内容转换为 Markdown、写入缓存，并直接摄入 KB
5. 达到充分性、收敛条件或边界条件后停止

限制与要求：

- `--iterative` 需要同时启用 `--kb chroma` 或 `--kb qdrant`
- 迭代模式会保留网页结果缓存，因此后续搜索可复用这些内容

## Embedding 模型切换

知识库向量的 `embedding_model` 和 `embedding_dimension` 必须和入库时保持一致。

- 修改 embedding 模型或维度后，旧 KB 不能继续混用
- `ksearch` 现在会为 KB 写入元数据，并在模型或维度不匹配时报错
- 发生切换时，先执行显式重置，再重新摄入文档

示例：

```bash
ksearch config --embedding-model mxbai-embed-large --embedding-dimension 1024
ksearch kb reset --confirm --embedding-model mxbai-embed-large --embedding-dimension 1024
ksearch kb ingest ~/notes --source logseq
```

## Docker 部署

```bash
docker compose up -d
docker exec ksearch-ollama ollama pull nomic-embed-text
```

默认服务：

- Qdrant: `http://localhost:6333`
- SearXNG: `http://localhost:48888`
- Ollama: `http://localhost:11434`
- Open WebUI: `http://localhost:3000`（启用对应 profile 时）

## 配置

默认配置文件路径：`~/.ksearch/config.json`

示例：

```json
{
  "searxng_url": "http://localhost:48888",
  "store_dir": "~/.ksearch/store",
  "index_db": "~/.ksearch/index.db",
  "max_results": 10,
  "timeout": 30,
  "format": "markdown",
  "time_range": "",
  "no_cache": false,
  "only_cache": false,
  "verbose": false,
  "kb_mode": "",
  "kb_dir": "~/.ksearch/kb",
  "kb_top_k": 5,
  "qdrant_url": "http://localhost:6333",
  "embedding_model": "nomic-embed-text",
  "embedding_dimension": 768,
  "ollama_url": "http://localhost:11434",
  "iterative_enabled": false,
  "max_iterations": 5,
  "max_time_seconds": 180,
  "fact_threshold": 0.7,
  "exploration_threshold": 0.4,
  "scoring_weights": {
    "vector": 0.4,
    "count": 0.3,
    "coverage": 0.3
  }
}
```

优先级：

```text
CLI 参数 > 配置文件 > 默认值
```

## 关键参数

搜索命令常用参数：

- `--format`, `-f`: `markdown` 或 `path`
- `--time-range`, `-t`: `day` / `week` / `month` / `year`
- `--max-results`, `-m`: 限制网页搜索结果数量
- `--searxng-url`, `-s`: 指定 SearXNG 服务地址
- `--store-dir`, `-d`: 指定缓存目录
- `--index-db`: 指定 SQLite 索引路径
- `--timeout`: 请求超时秒数
- `--no-cache`: 忽略网页缓存，强制抓取网络结果
- `--only-cache`: 只返回网页缓存
- `--kb`: 启用 KB 搜索，值为 `chroma`、`qdrant` 或 `none`
- `--embedding-model`: 指定 KB 使用的 embedding 模型
- `--embedding-dimension`: 指定 KB 使用的 embedding 维度
- `--iterative`: 启用迭代式 KB-first 搜索
- `--verbose`, `-v`: 打印详细信息

## 验证

```bash
uv run pytest -q
```

真实环境端到端测试：

```bash
bash tests/ollama_e2e_integration.sh
```

这个脚本要求本机可访问：

- Ollama: `http://localhost:11434`
- SearXNG: `http://localhost:48888`
- Ollama 中存在 `nomic-embed-text:latest`
- 负例模型默认使用 `fredrezones55/qwen3.5-opus:9b`

脚本会创建临时 KB 和临时测试文档，覆盖中英文和混合关键词检索、`--only-cache`、`--iterative`，并生成一份 markdown 报告。
