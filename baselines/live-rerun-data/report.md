# 评测报告

- 服务地址：`http://localhost:8000`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 14:22:37
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**10.00 / 12.00（83.3%）**，5 题全绿 / 共 6 题。

每题耗时：中位数 7.99 秒，最大 11.17 秒，合计 50.1 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 纯数据问题（`data`） | 10.00 | 12.00 | 83.3% | 5 / 6 |

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
    "dotenv": null,
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

## 没通过的题（1 道）

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

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| D01 | data | 2.00 | 2.00 | 7.16 |
| D02 | data | 2.00 | 2.00 | 9.17 |
| D03 | data | 0.00 | 2.00 | 11.17 |
| D04 | data | 2.00 | 2.00 | 6.75 |
| D05 | data | 2.00 | 2.00 | 6.99 |
| D06 | data | 2.00 | 2.00 | 8.83 |
