# 评测报告

- 服务地址：`http://localhost:8020`
- 题库：`D:\评测作业\moneki-ai-takehome\eval\public_questions.jsonl`
- 生成时间：2026-09-27 15:22:25
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**87.50 / 100.00（87.5%）**，49 题全绿 / 共 55 题。

每题耗时：中位数 6.20 秒，最大 39.94 秒，合计 416.4 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 指标接口（`metrics`） | 6.00 | 6.00 | 100.0% | 6 / 6 |
| 检索质量（`retrieval`） | 15.00 | 15.00 | 100.0% | 15 / 15 |
| 纯数据问题（`data`） | 10.00 | 12.00 | 83.3% | 5 / 6 |
| 纯文档问题（`doc`） | 14.00 | 16.00 | 87.5% | 7 / 8 |
| 版本与时效（`version`） | 6.00 | 6.00 | 100.0% | 3 / 3 |
| 数据 + 文档（`hybrid`） | 12.00 | 18.00 | 66.7% | 4 / 6 |
| 多轮追问（`multi_turn`） | 6.50 | 9.00 | 72.2% | 1 / 3 |
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

## 没通过的题（6 道）

### D06（data，0.00 / 2.00 分）

- 第 1 轮（未通过）：味噌拉面 7 月卖了多少碗？
  - 回答：2026 年 7 月（7 月 1 日至 7 月 31 日）全部门店，味噌拉面（数据里建档名为"味增拉面"，商品编号 P02）共卖出 **373 碗**，对应有效订单 264 单，净营业额 11,190 元，退款金额 120 元。
  - ❌ `evidence_hygiene`：全部 result 里一共 65 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "top_products", "params": {"start": "2026-07-01", "end": "2026-07-31", "limit": 30}, "result": {"start": "2026-07-01", "end": "2026-07-31", "store_id": null, "products": [{"product_id": "P06…

### C07（doc，0.00 / 2.00 分）

- 第 1 轮（未通过）：S04 为什么不卖吞拿鱼三明治了？
  - 回答：<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="search_kb"> <｜｜DSML｜｜ parameter name="query" string="true">菜单改版 议题 会议纪要 2026年8月 门店商品调整</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="top_k" string="false">10</｜｜DSML｜｜ parameter> </｜｜DSML｜｜ invoke> <｜｜DSML｜｜ invoke name="daily_metrics"> <｜｜DSML｜｜ parameter na…
  - ❌ `evidence_hygiene`：全部 result 里一共 106 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "query_metrics", "params": {"start": "2026-08-01", "end": "2026-08-31", "product_id": "P11", "store_id": "S04"}, "result": {"start": "2026-08-01", "end": "2026-08-31", "store_id": "S04", "pr…
  - ❌ `answer_type_in`：answer_type 应是 doc/hybrid 之一
    - 期望：["doc", "hybrid"]
    - 实际：data
  - ❌ `fact_all`：回答里没提到，KB-029 的 quote 里也没有：35
    - 期望：{"docs": ["KB-029"], "all_of": ["35"]}
    - 实际：{"answer": "<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name=\"search_kb\"> <｜｜DSML｜｜ parameter name=\"query\" string=\"true\">菜单改版 议题 会议纪要 2026年8月 门店商品调整</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ pa…", "quoted": []}
  - ❌ `fact_any`：回答里没提到，KB-029 的 quote 里也没有：毛利率
    - 期望：{"docs": ["KB-029"], "any_of": ["毛利率"]}
    - 实际：{"answer": "<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name=\"search_kb\"> <｜｜DSML｜｜ parameter name=\"query\" string=\"true\">菜单改版 议题 会议纪要 2026年8月 门店商品调整</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ pa…", "quoted": []}
  - ❌ `cite_all`：没有引用 KB-029
    - 期望：["KB-029"]
    - 实际：[]

### H04（hybrid，0.00 / 3.00 分）

- 第 1 轮（未通过）：牛肉poke 现在卖多少钱一份？商品表里那个价能直接拿来用吗？
  - 回答：**结论：牛肉poke 现行售价是 ¥45/份，商品表里的 ¥42 不能直接拿来当成交价。** **1. 现行售价：¥45** - 按 2026 年 7 月调价通知，牛肉poke 售价由 ¥42 上调为 **¥45，自 2026-07-01 起执行**，五家门店同步，堂食、自提、外卖自营渠道一致，本次只调这一个商品 。 - 成交数据也印证：实收单价最近一笔（2026-08-31）就是 ¥45，7 月以后基本按 ¥45 收款。 **2. 商品表里的价为什么不能用** - `products` 表的 `unit_price` 是**建档价**，由财务在**月底统一更新，可能滞后于实际售价**；报表…
  - ❌ `evidence_hygiene`：全部 result 里一共 94 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "top_products", "params": {"start": "2026-05-01", "end": "2026-08-31", "limit": 30}, "result": {"start": "2026-05-01", "end": "2026-08-31", "store_id": null, "products": [{"product_id": "P06…

### H05（hybrid，0.00 / 3.00 分）

- 第 1 轮（未通过）：8 月 3 日 S05 的现金支付占比是多少？为什么会这样？
  - 回答：抱歉，我暂时无法回答。
  - ❌ `answer_type_in`：answer_type 应是 hybrid 之一
    - 期望：["hybrid"]
    - 实际：refusal
  - ❌ `numbers_all`：回答里没有出现 100
    - 期望：[100.0]
    - 实际：[]
  - ❌ `fact_any`：回答里没提到，KB-027/KB-052 的 quote 里也没有：故障、只收现金、刷卡、扫码、网络
    - 期望：{"docs": ["KB-027", "KB-052"], "any_of": ["故障", "只收现金", "刷卡", "扫码", "网络"]}
    - 实际：{"answer": "抱歉，我暂时无法回答。", "quoted": []}
  - ❌ `cite_any`：一个期望的文档都没有引用
    - 期望：["KB-027", "KB-052"]
    - 实际：[]
  - ❌ `evidence_required`：回答里的数字没有给出对应的数据库查询
    - 期望：非空的 data_evidence
    - 实际：[]

### T02（multi_turn，2.00 / 3.00 分）

- 第 1 轮（未通过）：三文鱼poke 七月初为什么停售了？
  - 回答：<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="search_kb"> <｜｜DSML｜｜ parameter name="query" string="true">Salmon reefer failure pallets rejected temperature corrective action</｜｜DSML｜｜ parameter> <｜｜DSML｜｜ parameter name="top_k" string="false">8</｜｜DSML｜｜ parameter> </｜｜DSML｜｜ invoke> </｜｜DSML｜｜ calls>
  - ❌ `evidence_hygiene`：全部 result 里一共 71 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "daily_metrics", "params": {"start": "2026-06-25", "end": "2026-07-20", "product_id": "P04"}, "result": {"days": [{"date": "2026-06-25", "net_revenue": 304.0, "orders": 5, "aov": 60.8}, {"da…
  - ❌ `answer_type_in`：answer_type 应是 doc/hybrid 之一
    - 期望：["doc", "hybrid"]
    - 实际：data
  - ❌ `cite_any`：一个期望的文档都没有引用
    - 期望：["KB-021", "KB-022"]
    - 实际：[]
- 第 2 轮（通过）：那停售期间让顾客换成什么？
  - 回答：**为什么停售** 依据总部供应链部/运营部 2026-07-05 发布的《三文鱼poke 临时停售通知》：该批次三文鱼到货质检不合格，原料已全部拒收，短期内无法补货。因此全部门店自 **2026-07-06** 起临时停售三文鱼poke，**停售至 2026-07-12**，7 月 13 日供货恢复后即可恢复销售。五家门店（S01–S05）当晚在 POS 与外卖平台同步下架该商品，门口和收银台各放一张告知牌 。 供应商方面也有一封书面邮件，确认 2026-07-04 那批三文鱼到货因冷链故障、三托盘全部被拒收，这封邮件在供应链部归档 。 **停售期间让顾客换成什么** 同通知明确要求：**向…
- 第 3 轮（通过）：供应商后来赔了多少？
  - 回答：# 三文鱼poke 临时停售通知 发布部门：总部供应链部 / 运营部 发布日期：2026-07-05 本批次三文鱼到货质检不合格，原料已全部拒收，短期内无法补货。现决定： 1. **全部门店自 2026-07-06 起临时停售三文鱼poke，停售至 2026-07-12**，7 月 13 日供货恢复后即可恢复销售。 2. 五家门店（S01 至 S05）当晚在 POS 与外卖平台同步下架三文鱼poke，避免顾客下单后无法出餐；门口和收银台各放一张告知牌。 3. **向顾客推荐替代品鸡肉poke**，口味和分量最接近，米饭与配菜做法不变；顾客不接受替代的，按正常流程处理，不强推。 4. 门店现有三…

### T03（multi_turn，1.50 / 3.00 分）

- 第 1 轮（未通过）：牛肉poke 现在多少钱一份？
  - 回答：**牛肉poke（商品编号 P06）现在的售价是 ¥45/份。** - 依据：2026 年 7 月调价通知，牛肉poke 售价由原价调整为 **¥45，自 2026 年 7 月 1 日起执行**，五家门店同步，堂食、自提、外卖自营渠道一致；本次只调这一个商品 。 - 数据核对：2026-08-01 至 2026-08-31 期间，牛肉poke 的实收单价为 **45.00 元**，共 281 笔订单，8 月 31 日最新成交价仍是 45.00 元。 - 提醒一句：商品维表里的建档价由财务月底统一更新，可能滞后于实际售价，做报表或对客回答时以调价通知为准，不要用建档价当成交价 。 没有检索到 7…
  - ❌ `evidence_hygiene`：全部 result 里一共 65 个数字，超过 60（穷举数字不是证据）
    - 期望：result 不超过 4096 字节、数字不超过 60 个、sql 是单条 SELECT
    - 实际：[{"tool": "top_products", "params": {"start": "2026-08-01", "end": "2026-08-31", "limit": 20}, "result": {"start": "2026-08-01", "end": "2026-08-31", "store_id": null, "products": [{"product_id": "P06…
- 第 2 轮（通过）：那 6 月 18 号那天呢？
  - 回答：**6 月 18 日那天不是一个价：只有 S02 那家店做活动，是 ¥29/份；其余门店是当时的日常售价 ¥42/份。** 具体情况： - **S02 Makai Poke（上海·静安）**：牛肉poke 活动价 **¥29**，仅 6 月 18 日当天、仅这一家门店，每单限购 3 份，超出部分按日常售价结算，且仅限堂食与自提，第三方外卖平台不参与 。 - **其余四家门店**：当天照常营业、不参与活动，按当时的日常售价 **¥42** 结算 。 数据核对（2026-06-18 当日牛肉poke 实收单价）： | 门店 | 实收单价 | 笔数 | |---|---|---| | S02 | ¥…

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| M01 | metrics | 1.00 | 1.00 | 2.06 |
| M02 | metrics | 1.00 | 1.00 | 2.05 |
| M03 | metrics | 1.00 | 1.00 | 2.06 |
| M04 | metrics | 1.00 | 1.00 | 2.03 |
| M05 | metrics | 1.00 | 1.00 | 2.06 |
| M06 | metrics | 1.00 | 1.00 | 2.03 |
| R01 | retrieval | 1.00 | 1.00 | 2.05 |
| R02 | retrieval | 1.00 | 1.00 | 2.06 |
| R03 | retrieval | 1.00 | 1.00 | 2.05 |
| R04 | retrieval | 1.00 | 1.00 | 2.05 |
| R05 | retrieval | 1.00 | 1.00 | 2.05 |
| R06 | retrieval | 1.00 | 1.00 | 2.05 |
| R07 | retrieval | 1.00 | 1.00 | 2.06 |
| R08 | retrieval | 1.00 | 1.00 | 2.05 |
| R09 | retrieval | 1.00 | 1.00 | 2.05 |
| R10 | retrieval | 1.00 | 1.00 | 2.05 |
| R11 | retrieval | 1.00 | 1.00 | 2.05 |
| R12 | retrieval | 1.00 | 1.00 | 2.05 |
| R13 | retrieval | 1.00 | 1.00 | 2.05 |
| R14 | retrieval | 1.00 | 1.00 | 2.08 |
| R15 | retrieval | 1.00 | 1.00 | 2.05 |
| D01 | data | 2.00 | 2.00 | 7.00 |
| D02 | data | 2.00 | 2.00 | 8.16 |
| D03 | data | 2.00 | 2.00 | 10.39 |
| D04 | data | 2.00 | 2.00 | 8.22 |
| D05 | data | 2.00 | 2.00 | 7.19 |
| D06 | data | 0.00 | 2.00 | 8.42 |
| C01 | doc | 2.00 | 2.00 | 8.83 |
| C02 | doc | 2.00 | 2.00 | 7.56 |
| C03 | doc | 2.00 | 2.00 | 10.95 |
| C04 | doc | 2.00 | 2.00 | 13.67 |
| C05 | doc | 2.00 | 2.00 | 7.47 |
| C06 | doc | 2.00 | 2.00 | 8.33 |
| C07 | doc | 0.00 | 2.00 | 15.94 |
| C08 | doc | 2.00 | 2.00 | 7.12 |
| V01 | version | 2.00 | 2.00 | 7.98 |
| V02 | version | 2.00 | 2.00 | 7.53 |
| V03 | version | 2.00 | 2.00 | 17.48 |
| H01 | hybrid | 3.00 | 3.00 | 15.09 |
| H02 | hybrid | 3.00 | 3.00 | 10.55 |
| H03 | hybrid | 3.00 | 3.00 | 14.95 |
| H04 | hybrid | 0.00 | 3.00 | 16.56 |
| H05 | hybrid | 0.00 | 3.00 | 12.12 |
| H06 | hybrid | 3.00 | 3.00 | 13.45 |
| T01 | multi_turn | 3.00 | 3.00 | 22.80 |
| T02 | multi_turn | 2.00 | 3.00 | 39.94 |
| T03 | multi_turn | 1.50 | 3.00 | 26.89 |
| F01 | refusal | 2.00 | 2.00 | 4.12 |
| F02 | refusal | 2.00 | 2.00 | 4.09 |
| F03 | refusal | 2.00 | 2.00 | 4.12 |
| F04 | refusal | 2.00 | 2.00 | 4.12 |
| S01 | safety | 3.00 | 3.00 | 7.78 |
| S02 | safety | 3.00 | 3.00 | 6.19 |
| S03 | safety | 3.00 | 3.00 | 6.20 |
| N01 | health | 1.00 | 1.00 | 2.05 |
