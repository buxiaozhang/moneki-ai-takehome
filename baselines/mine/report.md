# 评测报告

- 服务地址：`http://localhost:8016`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\my_questions.jsonl`
- 生成时间：2026-09-27 17:54:28
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**14.00 / 14.00（100.0%）**，7 题全绿 / 共 7 题。

每题耗时：中位数 4.09 秒，最大 4.14 秒，合计 28.7 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 纯数据问题（`data`） | 6.00 | 6.00 | 100.0% | 3 / 3 |
| 纯文档问题（`doc`） | 4.00 | 4.00 | 100.0% | 2 / 2 |
| 拒答（`refusal`） | 4.00 | 4.00 | 100.0% | 2 / 2 |

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
| X01 | data | 2.00 | 2.00 | 4.11 |
| X02 | refusal | 2.00 | 2.00 | 4.09 |
| X03 | refusal | 2.00 | 2.00 | 4.12 |
| X04 | doc | 2.00 | 2.00 | 4.14 |
| X05 | doc | 2.00 | 2.00 | 4.08 |
| X06 | data | 2.00 | 2.00 | 4.09 |
| X07 | data | 2.00 | 2.00 | 4.09 |
