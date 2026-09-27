# 评测报告

- 服务地址：`http://localhost:8017`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\my_questions.jsonl`
- 生成时间：2026-09-27 17:43:28
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**6.00 / 14.00（42.9%）**，3 题全绿 / 共 7 题。

每题耗时：中位数 4.12 秒，最大 4.14 秒，合计 28.8 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 纯数据问题（`data`） | 4.00 | 6.00 | 66.7% | 2 / 3 |
| 纯文档问题（`doc`） | 2.00 | 4.00 | 50.0% | 1 / 2 |
| 拒答（`refusal`） | 0.00 | 4.00 | 0.0% | 0 / 2 |

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

### X01（data，0.00 / 2.00 分）

- 第 1 轮（未通过）：三文鱼销量怎么样？
  - 回答：这句像是追问，但这个会话里没有上文。请把问题补完整，例如“7 月的净营业额是多少”。
  - ❌ `answer_type_in`：answer_type 应是 data 之一
    - 期望：["data"]
    - 实际：clarify
  - ❌ `numbers_all`：回答里没有出现 1567
    - 期望：[1567]
    - 实际：[]
  - ❌ `text_any`：回答里一个期望说法都没有
    - 期望：["三文鱼poke"]
    - 实际：这句像是追问，但这个会话里没有上文。请把问题补完整，例如“7 月的净营业额是多少”。
  - ❌ `evidence_required`：回答里的数字没有给出对应的数据库查询
    - 期望：非空的 data_evidence
    - 实际：[]

### X02（refusal，0.00 / 2.00 分）

- 第 1 轮（未通过）：谁家的三文鱼最好吃
  - 回答：# 三文鱼poke 临时停售通知 发布部门：总部供应链部 / 运营部 发布日期：2026-07-05 本批次三文鱼到货质检不合格，原料已全部拒收，短期内无法补货。现决定： 1. **全部门店自 2026-07-06 起临时停售三文鱼poke，停售至 2026-07-12**，7 月 13 日供货恢复后即可恢复销售。 2. 五家门店（S01 至 S05）当晚在 POS 与外卖平台同步下架三文鱼poke，避免顾客下单后无法出餐；门口和收银台各放一张告知牌。 3. **向顾客推荐替代品鸡肉poke**，口味和分量最接近，米饭与配菜做法不变；顾客不接受替代的，按正常流程处理，不强推。 4. 门店现有三…
  - ❌ `answer_type_in`：answer_type 应是 refusal 之一
    - 期望：["refusal"]
    - 实际：doc
  - ❌ `cite_max`：引用了 2 份文档，最多允许 0 份
    - 期望：0
    - 实际：["KB-021", "KB-031"]

### X03（refusal，0.00 / 2.00 分）

- 第 1 轮（未通过）：适不适合外出？
  - 回答：# 指标口径手册 v3 适用范围：总部运营部、财务部、各门店店长，以及所有基于 POS 导出数据出具的经营报表与对外口径。 本手册自 2026-05-01 起生效，取代 v2（KB-002）。此前的模板、表格、月报里凡与本手册不一致的算法，一律以本手册为准。 ## 1. 数据来源 经营数字的唯一来源是 POS 每日导出的销售明细表 `sales`，配合门店维表 `stores` 与商品维表 `products`。 `sales` 的字段为：`order_id`、`date`、`store_id`、`product_id`、`qty`、`amount`、`payment`。 导出文件不做任何人工…
  - ❌ `answer_type_in`：answer_type 应是 refusal 之一
    - 期望：["refusal"]
    - 实际：doc
  - ❌ `cite_max`：引用了 1 份文档，最多允许 0 份
    - 期望：0
    - 实际：["KB-001"]

### X04（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：三文鱼怎么样？
  - 回答：这句像是追问，但这个会话里没有上文。请把问题补完整，例如“7 月的净营业额是多少”。
  - ❌ `answer_type_in`：answer_type 应是 doc/hybrid 之一
    - 期望：["doc", "hybrid"]
    - 实际：clarify
  - ❌ `text_any`：回答里一个期望说法都没有
    - 期望：["停售"]
    - 实际：这句像是追问，但这个会话里没有上文。请把问题补完整，例如“7 月的净营业额是多少”。
  - ❌ `cite_any`：一个期望的文档都没有引用
    - 期望：["KB-021"]
    - 实际：[]

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| X01 | data | 0.00 | 2.00 | 4.14 |
| X02 | refusal | 0.00 | 2.00 | 4.12 |
| X03 | refusal | 0.00 | 2.00 | 4.12 |
| X04 | doc | 0.00 | 2.00 | 4.11 |
| X05 | doc | 2.00 | 2.00 | 4.14 |
| X06 | data | 2.00 | 2.00 | 4.09 |
| X07 | data | 2.00 | 2.00 | 4.09 |
