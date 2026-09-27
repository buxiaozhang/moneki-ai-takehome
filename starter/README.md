# 经营看板 + 问答服务

运营内部用的问答服务：一条线查销售数据库，一条线查公司知识库。
Python 3.12，只用 `fastapi` / `uvicorn` / `httpx`，测试用 `pytest`。

## 跑起来

```bash
make setup      # uv venv --python 3.12 + 装依赖
make rebuild    # 重建清洗表与检索索引
make run        # 起服务，默认 http://127.0.0.1:8000
make test       # 跑测试
```

换一套数据或知识库：

```bash
make rebuild DATA_DIR=/path/to/data KB_DIR=/path/to/knowledge_base
```

`DATA_DIR`、`KB_DIR`、`VAR_DIR` 也可以直接作为环境变量传给 `make run`。

## 目录

| 文件 | 干什么的 |
|---|---|
| `kbqa/config.py` | 环境变量与路径；“今天”固定 2026-09-01 |
| `kbqa/cleaning.py` | 把原始 `sales` 导进 `var/clean.db` |
| `kbqa/tools.py` | 指标查询：汇总、按天、支付方式、商品排行、门店、品类、对比、单价 |
| `kbqa/loader.py` | 读知识库文件，认出 doc_id、标题、生效日期 |
| `kbqa/chunker.py` | 切块 |
| `kbqa/tokenizer.py` | 分词 |
| `kbqa/index.py` | BM25 索引 + 磁盘缓存 |
| `kbqa/retriever.py` | 检索与元数据过滤 |
| `kbqa/docfacts.py` / `units.py` | 从文档里挑句子、出引用 |
| `kbqa/planner.py` / `entities.py` / `timeparse.py` | 意图、实体、时间 |
| `kbqa/answerer.py` / `hybrid.py` / `render.py` | 组装回答 |
| `kbqa/llm.py` / `live.py` / `toolspec.py` | 模型客户端与工具回路 |
| `kbqa/insights.py` | 看板的统计预警规则（纯函数） |
| `kbqa/api_ui.py` / `web/` | 看板页面、流式接口、调试接口（**不属于契约**） |
| `kbqa/service.py` / `server.py` | 编排与 HTTP 层 |

## 接口

契约接口（`docs/API_CONTRACT.md`，改动会影响评测）：

| 方法 | 路径 |
|---|---|
| GET | `/api/health` |
| GET | `/api/metrics/summary` |
| GET | `/api/metrics/daily` |
| POST | `/api/retrieve` |
| POST | `/api/chat` |
| GET | `/api/trace/{trace_id}` |
| GET | `/api/data_quality` |

看板与调试接口（`kbqa/api_ui.py`，与契约分开维护）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 看板页面 |
| GET | `/api/ui/dashboard` | 一次给全首屏：汇总、逐日、Top 商品、门店对比、支付构成、异常预警 |
| POST | `/api/chat/stream` | 流式问答（SSE） |
| GET | `/api/traces` | 最近若干次问答 |
| GET | `/api/debug/index` | 哪些文档进了索引、切了多少块、跳过了什么 |
| GET | `/api/debug/doc/{id}` | 一份文档的全文与切片 |
| POST | `/api/debug/retrieve` | 检索对照：哪些候选被过滤、什么原因 |
| GET | `/api/debug/catalog` | 门店/商品维表、数据区间、模型接入状态 |
| GET | `/api/debug/config` | 生效的路径与配置（不含 Key 明文） |
| GET | `/api/debug/sql` | 在清洗表上跑只读 SQL |

调试接口会把知识库全文、检索中间态和清洗库 SQL 都摊开，**只在开发时用，别对外暴露**。

## 看板

四个页签：**经营看板** / 对话 / 知识库索引 / 数据质量。

* **筛选**：日期区间（带「全部 / 最近 7 天 / 按月」快捷键）、门店、商品、Top N。
* **趋势图**：逐日净营业额柱状图，零营业额、低于均值 −2σ、环比骤降的日子单独着色并打点。
* **图表联动**：点柱子或表格行互相高亮；点门店对比条直接下钻到那家门店；点预警里的日期跳到那一天。
* **Top 商品**：按净营业额排序，带占比条。
* **数据质量**：清洗台账，剔除原因用堆叠条看构成。
* **异常预警**：固定统计规则（零营业额、连续 2 天以上零营业额、低于均值 −2σ、环比降幅 ≥50%、退款占比 ≥5%）。规则而不是模型判断 —— 透明、误报可预期，也不会被误读成"模型觉得这里有问题"。阈值都在 `kbqa/insights.py` 里，可传参调整。

图表是**自绘 SVG**（`web/charts.js`），不引任何 CDN：离线环境可用，也不会因为外网不通而白屏。

## 调试面板

对话页右侧把 `/api/trace/{trace_id}` 完整可视化，流式提问时实时刷新：

* **耗时构成**：各步骤耗时条，一眼看出时间花在哪（是按占比画的，不是严格时间轴 —— trace 里没记步骤起止时刻）。
* **规划**：intent / kind / 检索词 / 区间 / 门店 / 商品 / 完整问题。
* **检索**：每条命中的分数条（按最高分归一）、补位片段灰显、被过滤的文档连同**过滤原因**一起列出。
* **工具调用**：每次都列出参数。
* **提示词**：发给模型的完整请求与模型原始输出，折叠展示。

## 两种模式

配了 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 就走模型，没配就走本地模板回答。
没有 Key 时服务照常启动，`/api/chat` 不会 500。

## 测试

```
make test        # pytest：接口、检索、回答、统计规则
make test-web    # 前端 DOM 冒烟（node + jsdom，缺依赖会自动跳过）
```

前端那套单独放是因为 **pytest 验证不了页面 JS 会不会抛错**：`$('x')` 取到 null、
图表在容器宽度为 0 时画、点击联动的重画顺序 —— 这些接口测试全绿也照样白屏。
`tests/web_smoke.js` 把脚本真的放进 JSDOM 跑一遍，覆盖看板渲染、图表联动、
追踪面板和流式问答。缺 jsdom 时它跳过并返回 0，不会卡住流水线。

交接说明见 `HANDOVER.md`。
