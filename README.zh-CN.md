# kbase

[English](./README.md) | 简体中文

`ksearch` 是一个面向研究和知识积累的 CLI 工具，把本地缓存、知识库语义检索和实时网络搜索整合到同一条工作流里。

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

`ksearch stats` 可以统一查看：

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

### AI 内容优化

`ksearch optimize` 使用本地 LLM（通过 Ollama）迭代评估和优化搜索结果。优化循环如下：

1. 获取搜索结果
2. 使用 LLM 评估内容质量
3. 识别信息缺口
4. 生成针对性的后续查询
5. 重新搜索并合并新结果
6. 重复直到达到置信度阈值或最大迭代次数
7. 合成最终优化内容

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
ksearch search "python asyncio"
```

常见变体：

```bash
ksearch search "rust async" --only-cache
ksearch search "agent memory" --no-cache
ksearch search "latest ai trends" --time-range week --max-results 5
ksearch search "python asyncio" --format path
ksearch search "vector database" --verbose
```

统一统计：

```bash
ksearch stats
```

## 常见工作流

### 1. 普通缓存优先搜索

```bash
ksearch search "python asyncio"
```

适合日常查询，优先复用已有本地知识。

### 2. 启用知识库辅助检索

```bash
ksearch search "task cancellation" --kbase chroma
```

适合已经有本地笔记、历史缓存或导入文档时使用。

### 3. 只做知识库语义检索

```bash
ksearch kbase query "异步取消传播" --top-k 5
```

适合只想查本地 kbase，不想触发新的网络抓取。

### 4. 迭代式 kbase-first 搜索

```bash
ksearch search "how does asyncio cancellation propagate" --kbase chroma --iterative
```

适合本地知识可能不完整，但又希望受控地扩展网页并回灌 kbase 的场景。

### 5. AI 内容优化

```bash
ksearch optimize "python asyncio best practices"
```

使用本地 LLM（通过 Ollama）迭代评估搜索结果质量，识别信息缺口，并持续优化直到达到置信度阈值。需要 Ollama 并已拉取 `gemma4:e2b` 模型。

```bash
# 自定义参数优化
ksearch optimize "rust async runtime" --model gemma4:e2b --max-iterations 5 --confidence 0.9

# 优化本地文件
ksearch optimize "summarize this" --file ./notes.md

# 详细输出，显示每轮优化迭代过程
ksearch optimize "distributed systems" --verbose
```

拉取所需模型：

```bash
ollama pull gemma4:e2b
```

## 知识库命令

```bash
ksearch kbase ingest ~/notes --source logseq --verbose
ksearch kbase ingest ~/docs/readme.md --source manual
ksearch kbase query "异步编程最佳实践" --top-k 5
ksearch kbase list
ksearch kbase delete ~/old-notes/test.md
ksearch kbase clear --confirm
ksearch kbase reset --confirm --embedding-model nomic-embed-text --embedding-dimension 768
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
ksearch config --embedding-model mxbai-embed-large --embedding-dimension 1024
ksearch kbase reset --confirm --embedding-model mxbai-embed-large --embedding-dimension 1024
ksearch kbase ingest ~/notes --source logseq
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
~/.ksearch/config.json
```

仓库内示例：

```text
./config.example.json
```

可以先复制到 `~/.ksearch/config.json`，再按需修改。

默认示例：

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
  "only_kbase": false,
  "verbose": false,
  "kbase_mode": "chroma",
  "kbase_dir": "~/.ksearch/kbase",
  "kbase_top_k": 5,
  "qdrant_url": "http://localhost:6333",
  "embedding_mode": "ollama",
  "embedding_model": "nomic-embed-text",
  "embedding_dimension": 768,
  "ollama_url": "http://localhost:11434",
  "allow_embedding_fallback": false,
  "iterative_enabled": true,
  "max_iterations": 5,
  "max_time_seconds": 180,
  "fact_threshold": 0.7,
  "exploration_threshold": 0.4,
  "scoring_weights": {
    "vector": 0.4,
    "count": 0.3,
    "coverage": 0.3
  },
  "hybrid_search": true,
  "rerank_enabled": true,
  "rerank_model": "gemma4:e2b",
  "bm25_top_k": 20,
  "vector_top_k": 20,
  "rrf_k": 60,
  "optimization_enabled": true,
  "optimization_model": "gemma4:e2b",
  "optimization_max_iterations": 3,
  "optimization_confidence_threshold": 0.8,
  "optimization_max_time_seconds": 120,
  "optimization_temperature": 0.3
}
```

`~/.ksearch/config.json` 里的所有键都可以省略。你可以只保留需要覆盖的字段，未填写的字段会自动回退到内置默认值。

### 配置项说明

#### 搜索与输出

| 配置项 | 默认值 | 可选值 / 类型 | 用处 |
| --- | --- | --- | --- |
| `searxng_url` | `http://localhost:48888` | URL 字符串 | SearXNG 网页搜索服务地址。 |
| `store_dir` | `~/.ksearch/store` | 路径字符串 | 转换后的网页正文在本地磁盘上的保存目录。 |
| `index_db` | `~/.ksearch/index.db` | 路径字符串 | 缓存元数据使用的 SQLite 索引库。 |
| `max_results` | `10` | 大于等于 1 的整数 | 每次搜索迭代最多请求多少条网页结果。 |
| `timeout` | `30` | 秒数整数 | SearXNG 请求、网页抓取和内容转换的超时时间。 |
| `format` | `markdown` | `markdown`、`path` | CLI 输出格式。`markdown` 输出结构化内容，`path` 只输出缓存文件路径。 |
| `time_range` | `""` | `""`、`day`、`week`、`month`、`year` | 可选的时间过滤条件，同时作用于网页搜索和部分缓存匹配。空字符串表示不限制。 |
| `no_cache` | `false` | 布尔值 | 跳过缓存读取，强制走联网搜索；新结果仍可能写入缓存。 |
| `only_cache` | `false` | 布尔值 | 只返回缓存命中，禁用联网搜索，也会关闭 iterative kbase-first 流程。 |
| `only_kbase` | `false` | 布尔值 | 只查 kbase，不走网页搜索，适合纯本地检索。 |
| `verbose` | `false` | 布尔值 | 输出更详细的 CLI 执行信息和后端状态。 |

#### kbase

| 配置项 | 默认值 | 可选值 / 类型 | 用处 |
| --- | --- | --- | --- |
| `kbase_mode` | `chroma` | `chroma`、`qdrant`、`none` | 选择 kbase 后端。`none` 表示关闭 kbase。默认 `search` 会先探测后端，不可用时自动关闭 kbase 路径。 |
| `kbase_dir` | `~/.ksearch/kbase` | 路径字符串 | 本地 kbase 数据和元数据的持久化目录。 |
| `kbase_top_k` | `5` | 大于等于 1 的整数 | kbase 检索返回的结果数，也是 iterative sufficiency 判断使用的候选数。 |
| `qdrant_url` | `http://localhost:6333` | URL 字符串 | Qdrant 服务地址，仅在 `kbase_mode=qdrant` 时使用。 |

#### Embedding

| 配置项 | 默认值 | 可选值 / 类型 | 用处 |
| --- | --- | --- | --- |
| `embedding_mode` | `ollama` | `ollama`、`sentence-transformers`、`simple` | embedding helper 偏好的后端模式。常规本地部署建议保持 `ollama`。 |
| `embedding_model` | `nomic-embed-text` | 模型名字符串 | kbase 使用的 embedding 模型。对已有 kbase 修改该值，通常需要重建或重置 kbase。 |
| `embedding_dimension` | `768` | 大于等于 1 的整数 | 期望的 embedding 向量维度，必须和实际模型输出维度一致。 |
| `ollama_url` | `http://localhost:11434` | URL 字符串 | Ollama 服务地址，embedding、rerank、内容优化都会用到。 |
| `allow_embedding_fallback` | `false` | 布尔值 | 允许 kbase embedding 在失败时退回 sentence-transformers 或 simple。常规运行建议保持关闭，让模型或维度错误直接失败。 |

#### 迭代搜索

| 配置项 | 默认值 | 可选值 / 类型 | 用处 |
| --- | --- | --- | --- |
| `iterative_enabled` | `true` | 布尔值 | 开启 kbase-first 的迭代搜索流程。系统会先判断 kbase 结果是否足够，不够时再回退到网页搜索。默认 `search` 会在 kbase 不可用时自动关闭它。 |
| `max_iterations` | `5` | 大于等于 1 的整数 | 初始 kbase 检索之后，最多允许再进行多少轮迭代。 |
| `max_time_seconds` | `180` | 秒数整数 | 单次 iterative 搜索的总时间预算。 |
| `fact_threshold` | `0.7` | 浮点数 | 面向事实型问题的 sufficiency 阈值，要求更高。 |
| `exploration_threshold` | `0.4` | 浮点数 | 面向探索型问题的 sufficiency 阈值，要求更宽松。 |
| `scoring_weights` | `{"vector": 0.4, "count": 0.3, "coverage": 0.3}` | 含 `vector`、`count`、`coverage` 浮点字段的对象 | sufficiency 打分权重，用来平衡语义相关性、结果数量和内容覆盖度。 |

#### 混合检索与重排

| 配置项 | 默认值 | 可选值 / 类型 | 用处 |
| --- | --- | --- | --- |
| `hybrid_search` | `true` | 布尔值 | 开启 kbase 内部的 BM25 + 向量混合检索。 |
| `rerank_enabled` | `true` | 布尔值 | 在召回后的 kbase 候选上开启 Ollama rerank。默认 `search` 会在 Ollama rerank 模型不可用时自动关闭它。 |
| `rerank_model` | `gemma4:e2b` | 模型名字符串 | 用于 rerank 候选片段的 Ollama 模型名。 |
| `bm25_top_k` | `20` | 大于等于 1 的整数 | 混合检索时参与融合的 BM25 候选数量。 |
| `vector_top_k` | `20` | 大于等于 1 的整数 | 混合检索时参与融合的向量候选数量。 |
| `rrf_k` | `60` | 大于等于 1 的整数 | BM25 和向量结果做 RRF 融合时使用的常数。 |

#### 内容优化

| 配置项 | 默认值 | 可选值 / 类型 | 用处 |
| --- | --- | --- | --- |
| `optimization_enabled` | `true` | 布尔值 | 开启 iterative 搜索结果的后处理优化。默认 `search` 会在 Ollama 优化模型不可用时自动关闭它。 |
| `optimization_model` | `gemma4:e2b` | 模型名字符串 | 内容优化和质量评估循环使用的 Ollama 模型名。 |
| `optimization_max_iterations` | `3` | 大于等于 1 的整数 | 内容优化最多允许的 refinement 轮数。 |
| `optimization_confidence_threshold` | `0.8` | `0.0` 到 `1.0` 的浮点数 | 当评估器置信度达到该阈值时停止继续 refinement。 |
| `optimization_max_time_seconds` | `120` | 秒数整数 | 单次优化请求的总时间预算。 |
| `optimization_temperature` | `0.3` | 大于等于 `0.0` 的浮点数 | 优化模型的采样温度。 |

#### 兼容旧字段

旧配置文件中的以下字段仍然会被兼容映射：

| 旧字段 | 当前字段 |
| --- | --- |
| `kb_mode` | `kbase_mode` |
| `kb_dir` | `kbase_dir` |
| `kb_top_k` | `kbase_top_k` |
| `only_kb` | `only_kbase` |

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

### `ksearch optimize` 参数

- `--model`: 指定 Ollama 优化模型（默认：`gemma4:e2b`）
- `--max-iterations`, `-i`: 最大优化迭代次数（默认：3）
- `--confidence`, `-c`: 质量置信度阈值（默认：0.8）
- `--temperature`: LLM 温度参数（默认：0.3）
- `--file`: 优化本地文件而非搜索
- `--verbose`, `-v`: 显示每轮优化迭代详情

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
