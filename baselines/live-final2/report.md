# 评测报告

- 服务地址：`http://localhost:8000`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 14:48:06
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**90.00 / 100.00（90.0%）**，51 题全绿 / 共 55 题。

每题耗时：中位数 6.14 秒，最大 38.70 秒，合计 383.0 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 指标接口（`metrics`） | 6.00 | 6.00 | 100.0% | 6 / 6 |
| 检索质量（`retrieval`） | 15.00 | 15.00 | 100.0% | 15 / 15 |
| 纯数据问题（`data`） | 10.00 | 12.00 | 83.3% | 5 / 6 |
| 纯文档问题（`doc`） | 14.00 | 16.00 | 87.5% | 7 / 8 |
| 版本与时效（`version`） | 6.00 | 6.00 | 100.0% | 3 / 3 |
| 数据 + 文档（`hybrid`） | 15.00 | 18.00 | 83.3% | 5 / 6 |
| 多轮追问（`multi_turn`） | 6.00 | 9.00 | 66.7% | 2 / 3 |
| 拒答（`refusal`） | 8.00 | 8.00 | 100.0% | 4 / 4 |
| 安全（`safety`） | 9.00 | 9.00 | 100.0% | 3 / 3 |
| 健康检查（`health`） | 1.00 | 1.00 | 100.0% | 1 / 1 |

## `/api/health` 快照

```json
{
  "status": "ok",
  "llm_mode": "live",
  "llm": {
    "mode": "live",
    "missing": [],
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-flash",
    "api_key_set": true,
    "dotenv": "D:\\评测作业\\moneki-ai-takehome\\.env",
    "hint": "已配置，问答会调用真实模型。"
  },
  "kb_docs": 35,
  "kb_chunks": 148,
  "valid_sales_rows": 18290,
  "today": "2026-09-01",
  "data_period": {
    "start": "2026-05-01",
    "end": "2026-08-31"
  },
  "cleaning_report": {
    "raw_rows": 18628,
    "removed": {
      "1_unparseable_date": 8,
      "2_empty_amount": 150,
      "3_qty_le_zero": 30,
      "4_store_not_in_stores": 10,
      "5_product_not_in_products": 40,
      "6_duplicate_row": 100,
      "note_unparseable_amount": 0
    },
    "kept_rows": 18290,
    "kept_sales_rows": 18196,
    "kept_refund_rows": 94
  },
  "index_key": "d2d97bd9f1e3",
  "kb_warnings": [
    "按 GB18030 解码（非 UTF-8）：KB-062_旧OA导出_营业时间调整通知.txt",
    "跳过没有 KB 编号的文件：README.md"
  ]
}
```

## 没通过的题（4 道）

### D03（data，0.00 / 2.00 分）

- 第 1 轮（未通过）：牛肉poke 六月一共卖了多少钱？
  - 回答：抱歉，我暂时无法回答。
  - ❌ `answer_type_in`：answer_type 应是 data/hybrid 之一
    - 期望：["data", "hybrid"]
    - 实际：refusal
  - ❌ `numbers_all`：回答里没有出现 21265
    - 期望：[21265.0]
    - 实际：[]
  - ❌ `evidence_required`：回答里的数字没有给出对应的数据库查询
    - 期望：非空的 data_evidence
    - 实际：[]

### C07（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：S04 为什么不卖吞拿鱼三明治了？
  - 回答：抱歉，我暂时无法回答。
  - ❌ `answer_type_in`：answer_type 应是 doc/hybrid 之一
    - 期望：["doc", "hybrid"]
    - 实际：refusal
  - ❌ `fact_all`：回答里没提到，KB-029 的 quote 里也没有：35
    - 期望：{"docs": ["KB-029"], "all_of": ["35"]}
    - 实际：{"answer": "抱歉，我暂时无法回答。", "quoted": []}
  - ❌ `fact_any`：回答里没提到，KB-029 的 quote 里也没有：毛利率
    - 期望：{"docs": ["KB-029"], "any_of": ["毛利率"]}
    - 实际：{"answer": "抱歉，我暂时无法回答。", "quoted": []}
  - ❌ `cite_all`：没有引用 KB-029
    - 期望：["KB-029"]
    - 实际：[]

### H06（hybrid，0.00 / 3.00 分）

- 第 1 轮（未通过）：S02 在 8 月 17 日到 19 日为什么一分钱营业额都没有？
  - 回答：<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="daily_metrics"> <｜｜DSML｜｜ parameter name="store_id" string="true">S02</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="start" string="true">2026-08-01</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="end" string="true">2026-08-31</｜｜DSML｜｜ parameter> </｜｜DSML｜｜ in…
  - ❌ `evidence_hygiene`：第 3 条的 result 超过 4096 字节；全部 result 里一共 414 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "daily_metrics", "params": {"start": "2026-08-14", "end": "2026-08-22", "store_id": "S02"}, "result": {"days": [{"date": "2026-08-14", "net_revenue": 979.0, "orders": 25, "aov": 39.16}, {"da…
  - ❌ `numbers_all`：回答里没有出现 0
    - 期望：[0.0]
    - 实际：[15.0, 15.0]
  - ❌ `text_any`：回答里一个期望说法都没有
    - 期望：["没有找到", "未找到", "没有查到", "未查到", "找不到", "没有说明", "没有记录", "未说明", "无法确定", "没有相关", "查不到", "不清楚", "没有任何", "无法解释", "不知道"]
    - 实际：<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="daily_metrics"> <｜｜DSML｜｜ parameter name="store_id" string="true">S02</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="start" string="true">2026-08-01</｜｜DSML｜｜ p…

### T03（multi_turn，0.00 / 3.00 分）

- 第 1 轮（未通过）：牛肉poke 现在多少钱一份？
  - 回答：抱歉，我暂时无法回答。
  - ❌ `answer_type_in`：answer_type 应是 hybrid/doc 之一
    - 期望：["hybrid", "doc"]
    - 实际：refusal
  - ❌ `fact_all`：回答里没提到，KB-025 的 quote 里也没有：45
    - 期望：{"docs": ["KB-025"], "all_of": ["45"]}
    - 实际：{"answer": "抱歉，我暂时无法回答。", "quoted": []}
  - ❌ `cite_all`：没有引用 KB-025
    - 期望：["KB-025"]
    - 实际：[]
- 第 2 轮（未通过）：那 6 月 18 号那天呢？
  - 回答：您这条问题没有带上文，我先按**全部门店、全部商品**给您 2026-06-18 当天的情况： - 净营业额：8,308.00 元 - 有效订单数：182 单 - 客单价：45.65 元 如果您想看的其实是某个门店或某个商品（比如之前提到的那个编号）那天的表现，麻烦告诉我门店/商品编号，我再单独拉一次。另外当天没有提及退款数据的话，我也可以按需要补上退款金额和销量。
  - ❌ `fact_all`：回答里没提到，KB-023 的 quote 里也没有：29
    - 期望：{"docs": ["KB-023"], "all_of": ["29"]}
    - 实际：{"answer": "您这条问题没有带上文，我先按**全部门店、全部商品**给您 2026-06-18 当天的情况： - 净营业额：8,308.00 元 - 有效订单数：182 单 - 客单价：45.65 元 如果您想看的其实是某个门店或某个商品（比如之前提到的那个编号）那天的表现，麻烦告诉我门店/商品编号，我再单独拉一次。另外当天没有提及…", "quoted": []}
  - ❌ `cite_any`：一个期望的文档都没有引用
    - 期望：["KB-023"]
    - 实际：[]

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| M01 | metrics | 1.00 | 1.00 | 2.05 |
| M02 | metrics | 1.00 | 1.00 | 2.05 |
| M03 | metrics | 1.00 | 1.00 | 2.05 |
| M04 | metrics | 1.00 | 1.00 | 2.05 |
| M05 | metrics | 1.00 | 1.00 | 2.05 |
| M06 | metrics | 1.00 | 1.00 | 2.06 |
| R01 | retrieval | 1.00 | 1.00 | 2.06 |
| R02 | retrieval | 1.00 | 1.00 | 2.05 |
| R03 | retrieval | 1.00 | 1.00 | 2.05 |
| R04 | retrieval | 1.00 | 1.00 | 2.08 |
| R05 | retrieval | 1.00 | 1.00 | 2.03 |
| R06 | retrieval | 1.00 | 1.00 | 2.05 |
| R07 | retrieval | 1.00 | 1.00 | 2.06 |
| R08 | retrieval | 1.00 | 1.00 | 2.06 |
| R09 | retrieval | 1.00 | 1.00 | 2.06 |
| R10 | retrieval | 1.00 | 1.00 | 2.08 |
| R11 | retrieval | 1.00 | 1.00 | 2.06 |
| R12 | retrieval | 1.00 | 1.00 | 2.06 |
| R13 | retrieval | 1.00 | 1.00 | 2.05 |
| R14 | retrieval | 1.00 | 1.00 | 2.06 |
| R15 | retrieval | 1.00 | 1.00 | 2.03 |
| D01 | data | 2.00 | 2.00 | 6.34 |
| D02 | data | 2.00 | 2.00 | 8.02 |
| D03 | data | 0.00 | 2.00 | 5.31 |
| D04 | data | 2.00 | 2.00 | 7.39 |
| D05 | data | 2.00 | 2.00 | 6.81 |
| D06 | data | 2.00 | 2.00 | 8.39 |
| C01 | doc | 2.00 | 2.00 | 9.00 |
| C02 | doc | 2.00 | 2.00 | 9.55 |
| C03 | doc | 2.00 | 2.00 | 8.95 |
| C04 | doc | 2.00 | 2.00 | 14.06 |
| C05 | doc | 2.00 | 2.00 | 9.36 |
| C06 | doc | 2.00 | 2.00 | 7.88 |
| C07 | doc | 0.00 | 2.00 | 7.91 |
| C08 | doc | 2.00 | 2.00 | 8.81 |
| V01 | version | 2.00 | 2.00 | 6.89 |
| V02 | version | 2.00 | 2.00 | 6.53 |
| V03 | version | 2.00 | 2.00 | 17.12 |
| H01 | hybrid | 3.00 | 3.00 | 14.31 |
| H02 | hybrid | 3.00 | 3.00 | 12.62 |
| H03 | hybrid | 3.00 | 3.00 | 10.20 |
| H04 | hybrid | 3.00 | 3.00 | 12.34 |
| H05 | hybrid | 3.00 | 3.00 | 12.42 |
| H06 | hybrid | 0.00 | 3.00 | 15.36 |
| T01 | multi_turn | 3.00 | 3.00 | 21.91 |
| T02 | multi_turn | 3.00 | 3.00 | 38.70 |
| T03 | multi_turn | 0.00 | 3.00 | 15.72 |
| F01 | refusal | 2.00 | 2.00 | 4.09 |
| F02 | refusal | 2.00 | 2.00 | 4.11 |
| F03 | refusal | 2.00 | 2.00 | 4.08 |
| F04 | refusal | 2.00 | 2.00 | 4.09 |
| S01 | safety | 3.00 | 3.00 | 7.17 |
| S02 | safety | 3.00 | 3.00 | 6.22 |
| S03 | safety | 3.00 | 3.00 | 6.14 |
| N01 | health | 1.00 | 1.00 | 2.06 |
