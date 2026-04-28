# kbase

[English](./README.md) | 简体中文

`kbase` 是一个面向研究和知识积累的 CLI 工具，把本地缓存、知识库语义检索和实时网络搜索整合到同一条工作流里。

它不是一次性搜索工具，而是一个持续积累知识的闭环：

1. 先查本地缓存和知识库
2. 本地不足时再扩展到网络
3. 把网页正文清洗并转换成 Markdown
4. 落地到本地缓存
5. 在后续检索中持续复用

## 为什么这个项目有价值

普通搜索 CLI 的终点通常是“返回结果”。  
`kbase` 的目标是把每次搜索都变成未来可复用的本地知识资产。

它适合：

- 个人研究工作流
- 本地 AI / agent memory 管道
- 笔记库与网页知识混合检索
- 需要不断提升检索质量的技术调查场景

## 核心亮点

### 缓存优先，减少重复抓取

优先复用本地缓存，避免重复请求、重复正文提取和重复转换。

### 支持语义知识库检索

基于 Chroma 或 Qdrant 的 kbase 检索，不只是关键词匹配，而是语义召回。

### 支持迭代式 kbase-first 搜索

先查 kbase，再评估是否足够；只有本地知识不足时才扩展网页，并把新结果回灌到缓存和 kbase。

### 正文清洗质量更高

现在优先使用 `trafilatura` 做主内容抽取，再 fallback 到 `markitdown`，能明显减少导航、页脚和模板噪音。

### Embedding 切换更安全

kbase 会记录 embedding model 和 dimension。切模型或维度时，如果和已有向量不一致，项目会阻止错误复用并要求显式 reset。

### 统一统计能力

`kbase stats` 可以统一查看：

- 当前缓存条数
- kbase 条数
- 总大小
- 关键词种类数
- 网站来源分布
- 搜索引擎分布
- kbase source 分布
- embedding 配置

### 提供真实环境 E2E 测试脚本

仓库内置了 Ollama + SearXNG 的真实端到端测试脚本，覆盖中英文和混合关键词场景。

## 安装

基础安装：

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

## 快速开始

基础搜索：

```bash
kbase search "python asyncio"
```

常见变体：

```bash
kbase search "rust async" --only-cache
kbase search "agent memory" --no-cache
kbase search "latest ai trends" --time-range week --max-results 5
kbase search "python asyncio" --format path
kbase search "vector database" --verbose
```

统一统计：

```bash
kbase stats
```

## 常见工作流

### 1. 普通缓存优先搜索

```bash
kbase search "python asyncio"
```

适合日常查询，优先复用已有本地知识。

### 2. 启用知识库辅助检索

```bash
kbase search "task cancellation" --kbase chroma
```

适合已经有本地笔记、历史缓存或导入文档时使用。

### 3. 只做知识库语义检索

```bash
kbase query "异步取消传播" --top-k 5
```

适合只想查本地 kbase，不想触发新的网络抓取。

### 4. 迭代式 kbase-first 搜索

```bash
kbase search "how does asyncio cancellation propagate" --kbase chroma --iterative
```

适合本地知识可能不完整，但又希望受控地扩展网页并回灌 kbase 的场景。

## 知识库命令

```bash
kbase ingest ~/notes --source logseq --verbose
kbase ingest ~/docs/readme.md --source manual
kbase query "异步编程最佳实践" --top-k 5
kbase list
kbase delete ~/old-notes/test.md
kbase clear --confirm
kbase reset --confirm --embedding-model nomic-embed-text --embedding-dimension 768
```

## 迭代式 kbase-first 搜索

迭代模式本质上是一个“充分性驱动”的搜索编排层：

1. 先判断查询更偏事实型还是探索型
2. 优先查 kbase
3. 计算结果充分性
4. 不足时再扩展网页
5. 将网页转成 Markdown
6. 写入缓存并回灌 kbase
7. 达到阈值或边界条件后停止

注意：

- `--iterative` 必须和 `--kbase chroma` 或 `--kbase qdrant` 一起使用
- 迭代模式会保留网页缓存，因此后续搜索可以复用这些内容

## Embedding 模型切换

知识库中的向量必须和入库时使用的 embedding 配置保持一致。

- 修改 `embedding_model` 或 `embedding_dimension` 后，旧 kbase 不能直接混用
- kbase 元数据会持久化并在打开时校验
- 不匹配时需要显式 reset 后再重新 ingest

示例：

```bash
kbase config --embedding-model mxbai-embed-large --embedding-dimension 1024
kbase reset --confirm --embedding-model mxbai-embed-large --embedding-dimension 1024
kbase ingest ~/notes --source logseq
```

## Docker 服务

```bash
docker compose up -d
docker exec ksearch-ollama ollama pull nomic-embed-text
```

默认地址：

- Qdrant: `http://localhost:6333`
- SearXNG: `http://localhost:48888`
- Ollama: `http://localhost:11434`
- Open WebUI: `http://localhost:3000`（启用对应 profile 时）

## 配置

默认配置文件：

```text
~/.kbase/config.json
```

示例：

```json
{
  "searxng_url": "http://localhost:48888",
  "store_dir": "~/.kbase/store",
  "index_db": "~/.kbase/index.db",
  "max_results": 10,
  "timeout": 30,
  "format": "markdown",
  "time_range": "",
  "no_cache": false,
  "only_cache": false,
  "verbose": false,
  "kbase_mode": "",
  "kbase_dir": "~/.kbase/kbase",
  "kbase_top_k": 5,
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

- `--format`, `-f`: `markdown` 或 `path`
- `--time-range`, `-t`: `day` / `week` / `month` / `year`
- `--max-results`, `-m`: 限制网页搜索结果数量
- `--searxng-url`, `-s`: 指定 SearXNG 地址
- `--store-dir`, `-d`: 指定缓存目录
- `--index-db`: 指定 SQLite 索引路径
- `--timeout`: 请求超时秒数
- `--no-cache`: 忽略缓存，强制联网
- `--only-cache`: 只返回缓存结果
- `--kbase`: 启用 kbase 检索，值为 `chroma`、`qdrant` 或 `none`
- `--embedding-model`: 指定 kbase embedding 模型
- `--embedding-dimension`: 指定 kbase embedding 维度
- `--iterative`: 启用迭代式 kbase-first 搜索
- `--verbose`, `-v`: 输出详细执行信息

## 测试

单元和集成风格测试：

```bash
uv run pytest -q
```

真实 Ollama + SearXNG 端到端测试：

```bash
bash tests/ollama_e2e_integration.sh
```

该脚本要求：

- Ollama 在 `http://localhost:11434`
- SearXNG 在 `http://localhost:48888`
- Ollama 中存在 `nomic-embed-text:latest`
- 存在一个负例非 embedding 模型，当前默认是 `fredrezones55/qwen3.5-opus:9b`

脚本会创建临时 kbase 和测试文档，覆盖英文、中文和混合关键词流程，验证 `--only-cache` 与 `--iterative`，并生成 Markdown 报告。
