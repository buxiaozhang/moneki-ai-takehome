# 评测报告

- 服务地址：`http://localhost:8000`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 14:23:54
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**10.00 / 16.00（62.5%）**，5 题全绿 / 共 8 题。

每题耗时：中位数 7.76 秒，最大 14.58 秒，合计 74.6 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 纯文档问题（`doc`） | 10.00 | 16.00 | 62.5% | 5 / 8 |

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

## 没通过的题（3 道）

### C01（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：外卖订单多久内可以申请退款？
  - 回答：**外卖订单：送达后 24 小时内提出，超过 24 小时不再受理** 。 补充几点同一条政策里的口径 ： - 堂食订单须当场提出，顾客离店后不再受理；自提订单比照堂食处理，取餐离店后不再受理。 - 无论哪种渠道，都要能在 POS 或小程序里查到对应订单。 - 审批门槛：单笔退款金额不超过 ¥200 的，当班店员核实后即可操作；超过 ¥200 需店长审批。 提醒一下：网上/旧资料里可能还写着“购买后 7 天内可退款”，那是已废止的 v1 版本，不要再按它执行 。现行版本是 2026-06-15 生效的 v2 。
  - ❌ `cite_none`：引用了不该引用的 KB-012
    - 期望：["KB-012"]
    - 实际：["KB-013", "KB-012"]

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

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| C01 | doc | 0.00 | 2.00 | 9.92 |
| C02 | doc | 2.00 | 2.00 | 7.20 |
| C03 | doc | 2.00 | 2.00 | 7.92 |
| C04 | doc | 0.00 | 2.00 | 14.58 |
| C05 | doc | 2.00 | 2.00 | 7.34 |
| C06 | doc | 2.00 | 2.00 | 13.12 |
| C07 | doc | 0.00 | 2.00 | 7.59 |
| C08 | doc | 2.00 | 2.00 | 6.95 |
