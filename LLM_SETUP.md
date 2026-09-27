# LLM 接入说明

> 本文按 `docs/API_CONTRACT.md` §7.4 的骨架写。
> 目的是让我们照着它就能把服务切到 DeepSeek `deepseek-flash` + 我们自己的 Key，**不改一行代码**。

---

## 1. 用了什么

| 项 | 值 |
|---|---|
| 协议 | **OpenAI 兼容 Chat Completions**（契约 §7.1 推荐路线） |
| 请求地址 | `POST {LLM_BASE_URL}/chat/completions`，地址**原样拼接**，不补 `/v1`、不截路径、不拆域名 |
| 厂商 / 模型 | 不在代码里固定。开发与自测全部通过环境变量注入，模型名只从 `LLM_MODEL` 读 |
| SDK | **不用任何厂商 SDK**。直接用 `httpx` 发 HTTP 请求（`httpx==0.28.1`） |
| 客户端实现 | `starter/kbqa/llm.py`：`LLMClient.chat()` |
| 工具回路 | `starter/kbqa/live.py`：多轮 `tools` 调用循环 |
| 认证 | 请求头 `Authorization: Bearer {LLM_API_KEY}` |

不用 SDK 是刻意的：换厂商时只改三个环境变量，不需要关心 SDK 的 `base_url` 拼法差异。
代价是重试、错误码分类、保持连接的空行这些要自己处理（§7 有对应自测）。

**请求体**（`llm.py:61-70`）：

```json
{
  "model": "<来自 LLM_MODEL>",
  "messages": [ ... ],
  "max_tokens": 4096,
  "tools": [ ... ],
  "tool_choice": "auto"
}
```

`tools` 只在需要工具时带上。顶层参数**只有这几个** —— 没有 `parallel_tool_calls`、
没有 `seed`、没有 `n`、没有 `temperature`，全部是 DeepSeek 文档里列出的参数。

---

## 2. 配置从哪里读

**只从环境变量读。** 没有配置文件、没有命令行参数（`starter/kbqa/config.py:190-207`）。

| 变量 | 含义 | 默认值 | 必填 |
|---|---|---|---|
| `LLM_BASE_URL` | 模型服务地址，例如 `https://api.deepseek.com` | 空 | 是（缺了走降级模式） |
| `LLM_API_KEY` | 模型 Key | 空 | 是（缺了走降级模式） |
| `LLM_MODEL` | 模型名，例如 `deepseek-flash` | 空 | 是（缺了走降级模式） |
| `LLM_TIMEOUT` | 单次模型调用超时（秒） | `120` | 否 |
| `CHAT_BUDGET` | `/api/chat` 整体预算（秒） | `150` | 否 |

其余与模型无关的配置：`DATA_DIR`、`KB_DIR`、`VAR_DIR`、`TODAY`（默认 `2026-09-01`）。

### 三条读取规则

1. **环境变量优先于 `.env`**。`.env` 只是本机开发的方便，用 `os.environ.setdefault`
   语义填入，**永远不会覆盖已经存在的环境变量**（`config.py:100-104`）。
   你们设的三个变量一定生效。
2. **`.env` 的位置**：先找仓库根目录，再找 `starter/`，文件名 `.env` 或 `.env.local`。
   想完全忽略 `.env`，设 `KBQA_NO_DOTENV=1`（自测 P1–P14 就是这么跑的）。
3. **`LLM_BASE_URL` 会被去掉末尾的 `/`**，其余原样保留。不做任何路径加工。

### 启动时不做的检查

按契约 §7.2 最后一段：**不在启动时校验 Key 格式，也不在启动时调用查余额、列模型之类的接口**。
`/api/health` 只报"有没有配"，不报 Key 内容。

---

## 3. 怎么换成你们的

**改三个环境变量，然后重启服务。不需要重跑重建命令。**

```bash
export LLM_BASE_URL=https://api.deepseek.com
export LLM_API_KEY=<你们的 Key>
export LLM_MODEL=deepseek-flash

cd starter && make run           # 或 python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000
```

Windows PowerShell：

```powershell
$env:LLM_BASE_URL='https://api.deepseek.com'
$env:LLM_API_KEY='<你们的 Key>'
$env:LLM_MODEL='deepseek-flash'
cd starter; .\.venv\Scripts\python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000
```

### 改完要重启吗？要。

**配置只在进程启动时读一次。** 改完环境变量必须重启服务，否则还在用旧配置。
（界面上会提示这一点：处于 mock 模式时，顶栏下会显示缺哪几个变量、以及"配置只在启动时读一次"。）

### 需要重跑 `make rebuild` 吗？不需要。

重建只关心 `data/` 和 `knowledge_base/`。**换模型与索引无关**，不碰这两个目录就不用重建。

**什么时候才需要重建**：换了 `data/` 或 `knowledge_base/`（例如评测第 3 步换成你们手里那份）。
那时跑 `make rebuild` 即可，知识和索引都是跟着内容走的，没有任何数字或文档内容写死在代码里。

### 验证切过去了没有

```bash
curl -s http://localhost:8000/api/health | python -m json.tool
```

看 `llm_mode`：

- `"live"` = 已经用上真实模型；
- `"mock"` = 还在降级模式，`llm.missing` 会列出缺哪个变量。

更详细的状态（**不含 Key 明文**）在 `GET /api/debug/config`：

```json
{
  "llm": {
    "mode": "live",
    "missing": [],
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-flash",
    "api_key_set": true,
    "dotenv": null,
    "hint": "已配置，问答会调用真实模型。"
  },
  "llm_timeout": 120.0,
  "chat_budget": 150.0
}
```

---

## 4. 怎么看到发给模型的请求

有三种办法，从推荐到备用。

### 办法一（推荐，评测时用的）：`llm_gateway.py proxy`

把 `LLM_BASE_URL` 指向代理即可，请求与响应原文逐条落成 JSONL：

```bash
python3 eval/llm_gateway.py proxy --upstream https://api.deepseek.com --log llm_traffic.jsonl
# 用它打印出来的地址作为 LLM_BASE_URL 启动服务
```

我的实现**不做任何地址改写**（不补 `/v1`、不截路径），所以带前缀的代理地址可以直接用 ——
预检 P1 就是专门验证这一点的（见 §7：`共观察到 60 次 POST /ds-gw/chat/completions`）。

### 办法二：服务自己的 trace（默认开着，不用配）

每一次模型调用的完整请求都写进 trace，**不需要打开任何开关**：

```bash
curl -s http://localhost:8000/api/trace/<trace_id> | python -m json.tool
```

`llm_calls[]` 每一条长这样（真实抓取，Key 不落进 trace）：

```json
{
  "endpoint": "http://127.0.0.1:5399/ds-gw/chat/completions",
  "model": "preflight-model-7f3a",
  "messages": 2,
  "tools": 10,
  "prompt": "[{\"role\": \"system\", \"content\": \"你是一家连锁餐饮公司的经营分析助手…\"}, …]",
  "status": 200,
  "finish_reason": "tool_calls",
  "content_chars": 0,
  "tool_calls": ["query_metrics", "daily_metrics"],
  "has_reasoning": true,
  "usage": {"prompt_tokens": 144, "completion_tokens": 29, "total_tokens": 173},
  "raw_content": "",
  "raw_reasoning": "（思考过程，只留在 trace 里，不进任何对外字段）",
  "took_ms": 155.7
}
```

字段含义：

| 字段 | 说明 |
|---|---|
| `prompt` | 发给模型的**完整 messages**（JSON 字符串），含 system 提示词与每一轮消息 |
| `raw_content` | 模型返回的 `message.content` 原文 |
| `raw_reasoning` | 模型返回的 `message.reasoning_content`（思考过程）**只在这里出现**，绝不进入 `answer` / `citations` / `data_evidence` |
| `tool_calls` | 本次请求的工具名列表 |
| `usage` | 原样透传的 token 用量 |

**第三个办法是界面**：调试面板（对话页右侧）会把上面的内容画成可回放的卡片 ——
检索命中与分数、被过滤的文档及原因、每次工具调用的参数、以及发给模型的完整提示词。
点历史记录就能重放任意一次问答。

### 一处必须说明的限制

`prompt` 是**截断到 4000 字的预览**（`llm.py:184-186`）。对话变长后会被截断，
末尾会带 `…（截断，共 N 字）`，此时它**不再是合法 JSON**，不能再 `json.loads`。

实测：同一次问答的第 3 轮模型调用，原始 5039 字被截到 4014 字。
**要看完整原文请用办法一（proxy）的 JSONL**，那里不做截断。

---

## 5. 没有 Key 时会怎样

**服务照常启动**，四个契约接口全部正常工作，`/api/chat` 进入降级模式，
**任何情况下都不会返回 HTTP 500**（契约 §7.2 第三条）。

| 接口 | 没有 Key 时的行为 |
|---|---|
| `GET /api/health` | 正常 200，`llm_mode` = `"mock"`，`llm.missing` 列出缺少的变量名 |
| `GET /api/metrics/summary` | 正常 200，指标口径与有 Key 时**完全一致** |
| `GET /api/metrics/daily` | 正常 200 |
| `POST /api/retrieve` | 正常 200，检索完全不受影响（不依赖模型） |
| `POST /api/chat` | 正常 200，`answer_type` 为 `data` / `doc` / `hybrid` / `refusal` 之一，走**模板作答** |

### 降级策略：为什么模板作答的数字也是对的

这不是"降级到随便答"，而是**换一个回答生成器**：

- **数字**本来就来自 `tools.py` 的 SQL 查询，由 `render.py` 排版，**从不经过模型**。
  所以 mock 与 live 算出来的营业额、订单数、客单价**一模一样**；
- **文档事实**来自 `docfacts.py` 从命中片段里挑的句子，`quote` 保证是原文连续文字，
  也不需要模型；
- **模型只负责组织语言**。没有模型时改用固定句式，信息量不变，措辞生硬一些。

因此公开题库在**完全没有 Key** 的情况下也能拿到与配置了 Key 时相同的分数 ——
这也是能把 `EVAL_REPORT.md` 的最终成绩写成无 Key 成绩的原因。

`starter/.env.example` 里有三个变量的占位符样例，可以直接复制成 `.env`。
仓库里**没有任何真实 Key**（`git log --all -S` 已核对过历史）。

---

## 6. 依赖与安装

| 项 | 值 |
|---|---|
| Python | **3.12**（开发与自测用 `3.12.0`） |
| 第三方依赖 | `fastapi` `uvicorn` `httpx` `pytest`，共 4 个，见 `starter/requirements.txt` |
| 实际版本 | fastapi 0.141.1 · uvicorn 0.53.0 · httpx 0.28.1 · pydantic 2.13.5 · starlette 1.7.0 · pytest 9.1.1 |
| 模型文件下载 | **无**。不用向量模型、不用本地推理，没有大文件要下 |
| 首次启动耗时 | 见下表 |

安装：

```bash
cd starter
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
make rebuild
```

首次耗时实测（本机，`make rebuild`）：

| 步骤 | 耗时 |
|---|---|
| 装依赖 | 约 20 秒（纯 Python 包，无编译） |
| 清洗 18628 行 → `var/clean.db` | 约 1 秒 |
| 建索引 35 份文档 / 148 片段 | 约 1 秒 |
| 服务启动 | 约 2 秒（索引缓存在仓库里，且缓存有效时不重算） |

**索引缓存**：`.cache/index.json` 随仓库提供，缓存键包含每个文件的大小、mtime 与内容 sha256。
知识库变了会自动重建；想强制重建就删掉这个文件。

---

## 7. 自测结果

### 预检输出（`eval/llm_gateway.py preflight`）

运行方式（`--no-wait` 是为了写进脚本；端口 5399 是显式指定的，便于服务提前用同一组值启动）：

```bash
# 终端 1：用预检约定的三个值启动服务
export LLM_BASE_URL=http://127.0.0.1:5399/ds-gw
export LLM_API_KEY=preflight-key-3b9c1f
export LLM_MODEL=preflight-model-7f3a
cd starter && python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000

# 终端 2：
python3 eval/llm_gateway.py preflight --service-url http://127.0.0.1:8000 --port 5399 --no-wait
```

结果：**14/14 全部通过，退出码 0**。

```
==============================================================================
预检假模型已启动：http://127.0.0.1:5399/ds-gw
它只提供 POST http://127.0.0.1:5399/ds-gw/chat/completions，其余任何路径都会返回 404 并被记下来。

请用下面三个环境变量重启你的服务（模型名是故意取的怪名字，写死模型名会被查出来）：

  export LLM_BASE_URL=http://127.0.0.1:5399/ds-gw
  export LLM_API_KEY=preflight-key-3b9c1f
  export LLM_MODEL=preflight-model-7f3a
==============================================================================

开始检查 http://127.0.0.1:8000 ……
  [normal] 你们的退款规则是怎么规定的？ → HTTP 200，0.53 秒
  [normal] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.44 秒
  [thinking_starved] 你们的退款规则是怎么规定的？ → HTTP 200，0.45 秒
  [thinking_starved] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.45 秒
  [empty_content] 你们的退款规则是怎么规定的？ → HTTP 200，0.86 秒
  [empty_content] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.81 秒
  [json_empty] 你们的退款规则是怎么规定的？ → HTTP 200，0.50 秒
  [json_empty] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.44 秒
  [bad_tool_args] 你们的退款规则是怎么规定的？ → HTTP 200，0.30 秒
  [bad_tool_args] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.33 秒
  [content_filter] 你们的退款规则是怎么规定的？ → HTTP 200，0.16 秒
  [content_filter] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.14 秒
  [insufficient_resource] 你们的退款规则是怎么规定的？ → HTTP 200，0.83 秒
  [insufficient_resource] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.78 秒
  [aborted] 你们的退款规则是怎么规定的？ → HTTP 200，0.14 秒
  [aborted] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.16 秒
  [http_401] 你们的退款规则是怎么规定的？ → HTTP 200，0.17 秒
  [http_401] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.17 秒
  [http_402] 你们的退款规则是怎么规定的？ → HTTP 200，0.17 秒
  [http_402] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.19 秒
  [http_422] 你们的退款规则是怎么规定的？ → HTTP 200，0.17 秒
  [http_422] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.17 秒
  [http_429] 你们的退款规则是怎么规定的？ → HTTP 200，0.81 秒
  [http_429] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.81 秒
  [http_500] 你们的退款规则是怎么规定的？ → HTTP 200，0.80 秒
  [http_500] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.81 秒
  [http_503] 你们的退款规则是怎么规定的？ → HTTP 200，0.80 秒
  [http_503] 最近一段时间的整体经营情况怎么样？ → HTTP 200，0.76 秒
  [slow] 你们的退款规则是怎么规定的？ → HTTP 200，18.50 秒
  [slow] 最近一段时间的整体经营情况怎么样？ → HTTP 200，18.50 秒
  [hang] 你们的退款规则是怎么规定的？ → HTTP 200，120.16 秒
  [hang] 最近一段时间的整体经营情况怎么样？ → HTTP 200，120.14 秒

编号  检查项                                                            结果  说明
----------------------------------------------------------------------------------
P1    服务确实把请求发到了注入的 LLM_BASE_URL（含路径前缀）             通过  共观察到 60 次 POST /ds-gw/chat/completions。
P2    请求里的 model 等于注入的 LLM_MODEL                               通过  全部请求都用了 preflight-model-7f3a。
P3    注入的 Key 以 Authorization: Bearer 发送                          通过  全部请求都带了正确的 Bearer Key。
P4    只用了 DeepSeek 文档列出的顶层参数                                通过  只出现了 DeepSeek 文档列出的顶层参数。
P5    max_tokens 不设，或不小于 2048                                    通过  max_tokens 都不小于 2048。
P6    没有访问 {prefix}/chat/completions 之外的任何路径                 通过  只访问了 POST /ds-gw/chat/completions，没有碰任何别的路径。
P7    工具定义规范，且每一个工具调用都以 role=tool + tool_call_id 回传  通过  工具定义规范，44 个工具调用的结果都正确回传了。
P8    每个场景下 /api/chat 都返回 HTTP 200 与字段完整的合法 JSON        通过  32 次问答全部返回 200 和字段完整的 JSON。
P9    模型不可用时给出结构化 refusal，answer 从不是空串                 通过  模型不可用的场景下都给了结构化 refusal 或有据可查的回答，answer 从不是空串。
P10   思考内容没有漏进 answer / citations / data_evidence               通过  32 次回答里，思考标记都没有出现在任何对外字段里。
P11   /api/chat 在时限内返回（含长时间无响应的场景）                    通过  最慢的一次是 120.16 秒，都在 180 秒以内。
P12   注入环境变量后 /api/health 报告 llm_mode = live                   通过  llm_mode = live。
P13   多轮工具调用之间 reasoning_content 原样回传（没有触发 400）       通过  18 次多轮请求都原样回传了 reasoning_content。
P14   保持连接的空行与 SSE 注释没有把服务弄坏                           通过  正文前的空行和 SSE 的 `: keep-alive` 注释都被正确跳过了，slow 场景照常给出回答。

预检通过：在 OpenAI 兼容这条路线上，我们能原样接上你的服务。
```

报告文件也留在仓库里：`starter/var/preflight/preflight_report.md` 与 `.json`。

### 逐条对照 §7.3 的需求

| §7.3 要求 | 实现位置 | 预检项 |
|---|---|---|
| `reasoning_content` 不回显给用户，也不当答案 | 只在 trace 的 `raw_reasoning` 留存；`answer` / `citations` / `data_evidence` 都不取它 | P10 |
| 带 `tools` 时必须把 assistant 消息（含 `reasoning_content`）**整条**回传 | `llm.py:43` 的 `LLMReply.message` 存的就是收到的 `message` 原文，`live.py` 整条 append 进 `messages`，**不挑字段重组** | P13 |
| `max_tokens` 不设或 ≥ 2048 | 设 `4096`（`llm.py:18`） | P5 |
| `finish_reason` 非 `stop`/`tool_calls` 一律按错误处理 | `llm.py:146-148`：`length` / `content_filter` / `insufficient_system_resource` / `aborted` 都抛结构化错误 | 8 项场景全绿 |
| 空正文且无 `tool_calls` 按错误处理 | `llm.py:149-150`；注意带 `tool_calls` 时 `content` 为空串是正常的，不报错 | P8/P9 |
| 工具参数是 JSON 字符串，解析失败要处理 | `live.py` 解析失败时记 `tool_arguments_invalid` 步骤，把错误作为 `role: tool` 结果回传，让模型自我修正 | P7（`bad_tool_args` 场景） |
| 一次可能返回多个工具调用 | `live.py` 遍历 `tool_calls` 全部执行，每个都用对应的 `tool_call_id` 回传 | P7（实测一轮返回过 `query_metrics` + `daily_metrics`） |
| 不用文档之外的参数 | 顶层只有 `model` / `messages` / `max_tokens` / `tools` / `tool_choice` | P4 |
| 错误码 400/401/402/422/429/500/503 不能让 `/api/chat` 落 500 | `llm.py:109-114` 统一抛 `LLMError`；`service.py` 兜底成结构化 `refusal`，真实原因写 trace | P8/P9 |
| 保持连接的空行、SSE 注释要能跳过 | `llm.py:116-118` 用 `json.loads(response.text.strip() or "{}")` | P14 |
| `/api/chat` 180 秒内必须返回；单次调用超时取 120 秒与剩余预算的较小值 | `CHAT_BUDGET=150`、`LLM_TIMEOUT=120`；`chat_with_retry` 用 `min(self.timeout, budget)` | P11（`hang` 场景 120.16 秒返回） |
| 思考模式下 `temperature` 等参数不生效，数字必须由代码渲染 | 数字一律来自 SQL + `render.py`，**从不经过模型**；也没有传 `temperature` | P9 |

---

## 8. 已知限制

1. **trace 里的提示词截断到 4000 字**（`llm.py:184`）。长对话的第 3 轮之后会被截断，
   末尾带 `…（截断，共 N 字）`，此时 `llm_calls[].prompt` 不再是合法 JSON。
   要看完整原文用 `proxy` 模式的 JSONL。我在 §4 也写了一遍，因为这一条最容易误导排查。

2. **`reasoning_content` 只在 trace 里留存，没有持久化。** trace 是内存里的环形缓冲
   （最近若干条），进程重启就没了。要长期留档得用 `proxy` 的 JSONL。

3. **流式输出没有逐 token 透传。** `/api/chat/stream` 推的是**服务自己的每一步**
   （规划、检索、工具调用、作答），最终答案是等模型返回后一次性给出。
   `delta.reasoning_content` 先于 `delta.content` 到达这一条我没有处理，
   因为我没有走流式调用模型。要做到真正的打字机效果，需要把 `llm.py` 改成流式请求
   并把 delta 转发进 SSE —— 前端已经预留了"思考中"的状态位。

4. **重试只有一次、且比较保守。** 只对 429/500/503 和 `empty_content` /
   `insufficient_system_resource` / 传输错误重试一次，且剩余预算不足 5 秒就不重试。
   没有指数退避，没有熔断。

5. **没有做过真实 DeepSeek 端到端的长时间压测。** 预检用的是按文档行为模拟的假模型，
   覆盖了 16 个场景的协议行为，但不等于真实网络的抖动与限流表现。

6. **`LLM_TIMEOUT` / `CHAT_BUDGET` 可以调，但没在真实高延迟链路上验证过边界。**
   预检的 `hang` 场景（120 秒无响应）能正常返回，更长的场景没测。
