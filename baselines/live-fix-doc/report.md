# 评测报告

- 服务地址：`http://localhost:8000`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 14:31:19
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**12.00 / 16.00（75.0%）**，6 题全绿 / 共 8 题。

每题耗时：中位数 11.96 秒，最大 27.02 秒，合计 105.8 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 纯文档问题（`doc`） | 12.00 | 16.00 | 75.0% | 6 / 8 |

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

## 没通过的题（2 道）

### C04（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：三文鱼那次断供，供应商最后赔了我们多少钱？
  - 回答：模型服务这次没有正常返回（工具调用没有收敛），为了不给出没有依据的数字，这个问题先不回答。可以稍后重试；失败的真实原因记在 trace 里。
  - ❌ `answer_type_in`：answer_type 应是 doc/hybrid 之一
    - 期望：["doc", "hybrid"]
    - 实际：refusal
  - ❌ `fact_all`：回答里没提到，KB-022 的 quote 里也没有：8600
    - 期望：{"docs": ["KB-022"], "all_of": ["8600"]}
    - 实际：{"answer": "模型服务这次没有正常返回（工具调用没有收敛），为了不给出没有依据的数字，这个问题先不回答。可以稍后重试；失败的真实原因记在 trace 里。", "quoted": []}
  - ❌ `cite_all`：没有引用 KB-022
    - 期望：["KB-022"]
    - 实际：[]

### C07（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：S04 为什么不卖吞拿鱼三明治了？
  - 回答：## 原因 S04 从 2026-08-10 起下架吞拿鱼三明治（P11），是 8 月经营会议上定的，属于菜单调整，不是临时缺货 。会上给的理由有三点： 1. **毛利不达标**：该商品在 S04 已连续两个月毛利率低于 35%。 2. **损耗偏高**：原料是冷冻吞拿鱼块，拆封后必须当天用完，实际每天都有剩余，备货损耗明显高于其他三明治；而且原料价格短期没有下行空间，靠减分量拉毛利会影响口感，会上否决了这个做法。 3. **销量偏弱**：销量在三明治类里一直排末位，起不到带客流的作用。 会上同时要求：库存 8 月 9 日前用完，剩余做员工餐消化、不做促销清货；8 月 10 日当天在 POS …
  - ❌ `evidence_hygiene`：全部 result 里一共 76 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "query_metrics", "params": {"start": "2026-05-01", "end": "2026-08-31", "store_id": "S04", "product_id": "P11"}, "result": {"start": "2026-05-01", "end": "2026-08-31", "store_id": "S04", "pr…

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| C01 | doc | 2.00 | 2.00 | 9.23 |
| C02 | doc | 2.00 | 2.00 | 27.02 |
| C03 | doc | 2.00 | 2.00 | 11.98 |
| C04 | doc | 0.00 | 2.00 | 14.25 |
| C05 | doc | 2.00 | 2.00 | 7.84 |
| C06 | doc | 2.00 | 2.00 | 8.62 |
| C07 | doc | 0.00 | 2.00 | 14.92 |
| C08 | doc | 2.00 | 2.00 | 11.94 |
