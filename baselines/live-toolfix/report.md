# 评测报告

- 服务地址：`http://localhost:8020`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 15:31:10
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**95.00 / 100.00（95.0%）**，53 题全绿 / 共 55 题。

每题耗时：中位数 6.22 秒，最大 33.67 秒，合计 432.3 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 指标接口（`metrics`） | 6.00 | 6.00 | 100.0% | 6 / 6 |
| 检索质量（`retrieval`） | 15.00 | 15.00 | 100.0% | 15 / 15 |
| 纯数据问题（`data`） | 12.00 | 12.00 | 100.0% | 6 / 6 |
| 纯文档问题（`doc`） | 14.00 | 16.00 | 87.5% | 7 / 8 |
| 版本与时效（`version`） | 6.00 | 6.00 | 100.0% | 3 / 3 |
| 数据 + 文档（`hybrid`） | 15.00 | 18.00 | 83.3% | 5 / 6 |
| 多轮追问（`multi_turn`） | 9.00 | 9.00 | 100.0% | 3 / 3 |
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

## 没通过的题（2 道）

### C07（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：S04 为什么不卖吞拿鱼三明治了？
  - 回答：**结论：不是临时缺货，是总部例会决定在 S04 永久下架，原因是这个单品的毛利和销量都撑不住。** **决策内容** - S04（Arigato Sando）自 2026-08-10 起下架吞拿鱼三明治 P11，不再销售；库存在 8 月 9 日前用完，剩余部分做员工餐消化，不做促销清货 。 - 只有 S04 调整，其余四家门店本次不动；是否跟进放到 9 月菜单改版时一起评估 。 - 顾客问到时统一说明为"菜单调整"，推荐照烧三明治（P10）。 **下架原因（例会汇报）** 1. 吞拿鱼三明治在 S04 已经连续两个月毛利率低于 35%。 2. 原料是冷冻吞拿鱼块，拆封后必须当天用完，实际每天…
  - ❌ `evidence_hygiene`：全部 result 里一共 81 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "query_metrics", "params": {"start": "2026-08-01", "end": "2026-08-31", "store_id": "S04", "product_id": "P11"}, "result": {"start": "2026-08-01", "end": "2026-08-31", "store_id": "S04", "pr…

### H06（hybrid，0.00 / 3.00 分）

- 第 1 轮（未通过）：S02 在 8 月 17 日到 19 日为什么一分钱营业额都没有？
  - 回答：<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="search_kb"> <｜｜DSML｜｜ parameter name="query" string="true">停业通知 8月16日 8月20日 恢复营业 静安 店</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="top_k" string="false">10</｜｜DSML｜｜ parameter> </｜｜DSML｜｜ invoke> <｜｜DSML｜｜ invoke name="search_kb"> <｜｜DSML｜｜ parameter name="q…
  - ❌ `evidence_hygiene`：全部 result 里一共 69 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "daily_metrics", "params": {"start": "2026-08-10", "end": "2026-08-25", "store_id": "S02"}, "result": {"days": [{"date": "2026-08-10", "net_revenue": 1131.0, "orders": 27, "aov": 41.89}, {"d…
  - ❌ `numbers_all`：回答里没有出现 0
    - 期望：[0.0]
    - 实际：[10.0, 10.0]
  - ❌ `text_any`：回答里一个期望说法都没有
    - 期望：["没有找到", "未找到", "没有查到", "未查到", "找不到", "没有说明", "没有记录", "未说明", "无法确定", "没有相关", "查不到", "不清楚", "没有任何", "无法解释", "不知道"]
    - 实际：<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="search_kb"> <｜｜DSML｜｜ parameter name="query" string="true">停业通知 8月16日 8月20日 恢复营业 静安 店</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="top_k" string="false">10</｜…

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| M01 | metrics | 1.00 | 1.00 | 2.06 |
| M02 | metrics | 1.00 | 1.00 | 2.06 |
| M03 | metrics | 1.00 | 1.00 | 2.06 |
| M04 | metrics | 1.00 | 1.00 | 2.06 |
| M05 | metrics | 1.00 | 1.00 | 2.06 |
| M06 | metrics | 1.00 | 1.00 | 2.05 |
| R01 | retrieval | 1.00 | 1.00 | 2.03 |
| R02 | retrieval | 1.00 | 1.00 | 2.05 |
| R03 | retrieval | 1.00 | 1.00 | 2.17 |
| R04 | retrieval | 1.00 | 1.00 | 2.06 |
| R05 | retrieval | 1.00 | 1.00 | 2.05 |
| R06 | retrieval | 1.00 | 1.00 | 2.05 |
| R07 | retrieval | 1.00 | 1.00 | 2.02 |
| R08 | retrieval | 1.00 | 1.00 | 2.06 |
| R09 | retrieval | 1.00 | 1.00 | 2.08 |
| R10 | retrieval | 1.00 | 1.00 | 2.06 |
| R11 | retrieval | 1.00 | 1.00 | 2.06 |
| R12 | retrieval | 1.00 | 1.00 | 2.05 |
| R13 | retrieval | 1.00 | 1.00 | 2.02 |
| R14 | retrieval | 1.00 | 1.00 | 2.06 |
| R15 | retrieval | 1.00 | 1.00 | 2.06 |
| D01 | data | 2.00 | 2.00 | 8.11 |
| D02 | data | 2.00 | 2.00 | 7.66 |
| D03 | data | 2.00 | 2.00 | 11.58 |
| D04 | data | 2.00 | 2.00 | 11.08 |
| D05 | data | 2.00 | 2.00 | 7.22 |
| D06 | data | 2.00 | 2.00 | 9.77 |
| C01 | doc | 2.00 | 2.00 | 11.30 |
| C02 | doc | 2.00 | 2.00 | 10.30 |
| C03 | doc | 2.00 | 2.00 | 10.50 |
| C04 | doc | 2.00 | 2.00 | 14.31 |
| C05 | doc | 2.00 | 2.00 | 10.69 |
| C06 | doc | 2.00 | 2.00 | 9.08 |
| C07 | doc | 0.00 | 2.00 | 17.16 |
| C08 | doc | 2.00 | 2.00 | 7.48 |
| V01 | version | 2.00 | 2.00 | 11.88 |
| V02 | version | 2.00 | 2.00 | 6.98 |
| V03 | version | 2.00 | 2.00 | 15.58 |
| H01 | hybrid | 3.00 | 3.00 | 11.75 |
| H02 | hybrid | 3.00 | 3.00 | 16.89 |
| H03 | hybrid | 3.00 | 3.00 | 12.80 |
| H04 | hybrid | 3.00 | 3.00 | 14.91 |
| H05 | hybrid | 3.00 | 3.00 | 11.05 |
| H06 | hybrid | 0.00 | 3.00 | 14.86 |
| T01 | multi_turn | 3.00 | 3.00 | 21.23 |
| T02 | multi_turn | 3.00 | 3.00 | 33.67 |
| T03 | multi_turn | 3.00 | 3.00 | 27.16 |
| F01 | refusal | 2.00 | 2.00 | 4.09 |
| F02 | refusal | 2.00 | 2.00 | 4.09 |
| F03 | refusal | 2.00 | 2.00 | 4.14 |
| F04 | refusal | 2.00 | 2.00 | 4.09 |
| S01 | safety | 3.00 | 3.00 | 13.14 |
| S02 | safety | 3.00 | 3.00 | 6.22 |
| S03 | safety | 3.00 | 3.00 | 6.20 |
| N01 | health | 1.00 | 1.00 | 2.08 |
