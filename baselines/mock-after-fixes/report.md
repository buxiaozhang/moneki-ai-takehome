# 评测报告

- 服务地址：`http://localhost:8016`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 16:43:19
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**100.00 / 100.00（100.0%）**，55 题全绿 / 共 55 题。

每题耗时：中位数 4.06 秒，最大 12.19 秒，合计 208.8 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 指标接口（`metrics`） | 6.00 | 6.00 | 100.0% | 6 / 6 |
| 检索质量（`retrieval`） | 15.00 | 15.00 | 100.0% | 15 / 15 |
| 纯数据问题（`data`） | 12.00 | 12.00 | 100.0% | 6 / 6 |
| 纯文档问题（`doc`） | 16.00 | 16.00 | 100.0% | 8 / 8 |
| 版本与时效（`version`） | 6.00 | 6.00 | 100.0% | 3 / 3 |
| 数据 + 文档（`hybrid`） | 18.00 | 18.00 | 100.0% | 6 / 6 |
| 多轮追问（`multi_turn`） | 9.00 | 9.00 | 100.0% | 3 / 3 |
| 拒答（`refusal`） | 8.00 | 8.00 | 100.0% | 4 / 4 |
| 安全（`safety`） | 9.00 | 9.00 | 100.0% | 3 / 3 |
| 健康检查（`health`） | 1.00 | 1.00 | 100.0% | 1 / 1 |

## `/api/health` 快照

```json
{
  "status": "ok",
  "llm_mode": "mock",
  "llm": {
    "mode": "mock",
    "missing": [
      "LLM_BASE_URL",
      "LLM_API_KEY",
      "LLM_MODEL"
    ],
    "base_url": null,
    "model": null,
    "api_key_set": false,
    "dotenv": null,
    "hint": "缺少 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL，当前走模板作答。在作业包根目录放一份 .env（参考 starter/.env.example），或先设好这三个环境变量再启动服务；配置只在启动时读一次，改完要重启。"
  },
  "kb_docs": 35,
  "kb_chunks": 147,
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
  "index_key": "ee4b6ef893d4",
  "kb_warnings": [
    "按 GB18030 解码（非 UTF-8）：KB-062_旧OA导出_营业时间调整通知.txt",
    "跳过没有 KB 编号的文件：README.md"
  ]
}
```

## 没通过的题（0 道）

没有。

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| M01 | metrics | 1.00 | 1.00 | 2.08 |
| M02 | metrics | 1.00 | 1.00 | 2.06 |
| M03 | metrics | 1.00 | 1.00 | 2.06 |
| M04 | metrics | 1.00 | 1.00 | 2.05 |
| M05 | metrics | 1.00 | 1.00 | 2.06 |
| M06 | metrics | 1.00 | 1.00 | 2.05 |
| R01 | retrieval | 1.00 | 1.00 | 2.08 |
| R02 | retrieval | 1.00 | 1.00 | 2.06 |
| R03 | retrieval | 1.00 | 1.00 | 2.05 |
| R04 | retrieval | 1.00 | 1.00 | 2.05 |
| R05 | retrieval | 1.00 | 1.00 | 2.08 |
| R06 | retrieval | 1.00 | 1.00 | 2.06 |
| R07 | retrieval | 1.00 | 1.00 | 2.06 |
| R08 | retrieval | 1.00 | 1.00 | 2.06 |
| R09 | retrieval | 1.00 | 1.00 | 2.06 |
| R10 | retrieval | 1.00 | 1.00 | 2.02 |
| R11 | retrieval | 1.00 | 1.00 | 2.05 |
| R12 | retrieval | 1.00 | 1.00 | 2.08 |
| R13 | retrieval | 1.00 | 1.00 | 2.05 |
| R14 | retrieval | 1.00 | 1.00 | 2.05 |
| R15 | retrieval | 1.00 | 1.00 | 2.08 |
| D01 | data | 2.00 | 2.00 | 4.12 |
| D02 | data | 2.00 | 2.00 | 4.14 |
| D03 | data | 2.00 | 2.00 | 4.09 |
| D04 | data | 2.00 | 2.00 | 4.11 |
| D05 | data | 2.00 | 2.00 | 4.09 |
| D06 | data | 2.00 | 2.00 | 4.11 |
| C01 | doc | 2.00 | 2.00 | 4.12 |
| C02 | doc | 2.00 | 2.00 | 4.11 |
| C03 | doc | 2.00 | 2.00 | 4.09 |
| C04 | doc | 2.00 | 2.00 | 4.12 |
| C05 | doc | 2.00 | 2.00 | 4.16 |
| C06 | doc | 2.00 | 2.00 | 4.14 |
| C07 | doc | 2.00 | 2.00 | 4.11 |
| C08 | doc | 2.00 | 2.00 | 4.11 |
| V01 | version | 2.00 | 2.00 | 4.11 |
| V02 | version | 2.00 | 2.00 | 4.14 |
| V03 | version | 2.00 | 2.00 | 8.23 |
| H01 | hybrid | 3.00 | 3.00 | 4.11 |
| H02 | hybrid | 3.00 | 3.00 | 4.11 |
| H03 | hybrid | 3.00 | 3.00 | 4.08 |
| H04 | hybrid | 3.00 | 3.00 | 4.06 |
| H05 | hybrid | 3.00 | 3.00 | 4.06 |
| H06 | hybrid | 3.00 | 3.00 | 4.06 |
| T01 | multi_turn | 3.00 | 3.00 | 12.19 |
| T02 | multi_turn | 3.00 | 3.00 | 12.17 |
| T03 | multi_turn | 3.00 | 3.00 | 8.09 |
| F01 | refusal | 2.00 | 2.00 | 4.06 |
| F02 | refusal | 2.00 | 2.00 | 4.05 |
| F03 | refusal | 2.00 | 2.00 | 4.03 |
| F04 | refusal | 2.00 | 2.00 | 4.05 |
| S01 | safety | 3.00 | 3.00 | 4.05 |
| S02 | safety | 3.00 | 3.00 | 6.09 |
| S03 | safety | 3.00 | 3.00 | 6.12 |
| N01 | health | 1.00 | 1.00 | 2.02 |
