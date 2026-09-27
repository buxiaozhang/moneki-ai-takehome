# 评测报告

- 服务地址：`http://localhost:8000`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 14:26:06
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**15.00 / 18.00（83.3%）**，5 题全绿 / 共 6 题。

每题耗时：中位数 13.41 秒，最大 18.48 秒，合计 83.7 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 数据 + 文档（`hybrid`） | 15.00 | 18.00 | 83.3% | 5 / 6 |

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

### H06（hybrid，0.00 / 3.00 分）

- 第 1 轮（未通过）：S02 在 8 月 17 日到 19 日为什么一分钱营业额都没有？
  - 回答：模型服务这次没有正常返回（工具调用没有收敛），为了不给出没有依据的数字，这个问题先不回答。可以稍后重试；失败的真实原因记在 trace 里。
  - ❌ `numbers_all`：回答里没有出现 0
    - 期望：[0.0]
    - 实际：[]
  - ❌ `text_any`：回答里一个期望说法都没有
    - 期望：["没有找到", "未找到", "没有查到", "未查到", "找不到", "没有说明", "没有记录", "未说明", "无法确定", "没有相关", "查不到", "不清楚", "没有任何", "无法解释", "不知道"]
    - 实际：模型服务这次没有正常返回（工具调用没有收敛），为了不给出没有依据的数字，这个问题先不回答。可以稍后重试；失败的真实原因记在 trace 里。
  - ❌ `evidence_required`：回答里的数字没有给出对应的数据库查询
    - 期望：非空的 data_evidence
    - 实际：[]

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| H01 | hybrid | 3.00 | 3.00 | 14.86 |
| H02 | hybrid | 3.00 | 3.00 | 11.95 |
| H03 | hybrid | 3.00 | 3.00 | 11.31 |
| H04 | hybrid | 3.00 | 3.00 | 16.08 |
| H05 | hybrid | 3.00 | 3.00 | 10.98 |
| H06 | hybrid | 0.00 | 3.00 | 18.48 |
