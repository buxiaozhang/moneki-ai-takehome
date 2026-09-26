# DEBUG_LOG

## D-001：`_where` 把 `end` 当开区间，区间最后一天整天丢失

| M01 |  |
|---|---|
| 现象 | M01（`GET /api/metrics/summary?start=2026-06-01&end=2026-06-30`）报 `net_revenue=152883.0`，期望 `156757.0`，差 `-3874`。M02 差 `-1027`、M03 差 `-176`，三道题都**偏小**且都只差「一截」而不是数量级。M06（`daily`，`2026-06-08~2026-06-12`）返回的 5 天**全是 0**。M04 更极端：`start=end=2026-06-18`，整题返回 `net_revenue=0.0, orders=0, qty=0, aov=null`。 |
| 假设 | ① `end` 当天数据丢了；② 区间被当成开区间 `date < end`；③ 数据本身不存在。 |
| 验证 | 在旧表上按原始 SQL 复现，四个字段与评测报告**逐字一致**：<br>`SELECT SUM(amount_cents), 0, COUNT(*), SUM(qty) FROM sales_clean WHERE date>='2026-06-01' AND date<'2026-06-30' AND is_refund=0`<br>→ `net=152883.0, refund=0.0, orders=4272, qty=6360, aov=35.79`，与 `report.md` 的 M01 完全相同。<br>把右端改成 `date<='2026-06-30'`，`net` 变 `157462.0`（+4579）—— 说明 6/30 那天有数据，排除假设③。<br>M04 的 `start == end` 时 `date>='2026-06-18' AND date<'2026-06-18'` **恒为空**，所以整题返回 0，与报告一致。M06 缺的是 `2026-06-12` 那天（报告里恰好只有 6/12 报错，前 4 天本来就是 0）。 |
| 根因 | `kbqa/tools.py:53` 的 `DataTools._where`：`clause = ["date >= ?", "date < ?"]` —— 右端用了 `<` 而不是 `<=`，把 `end` 当天整天排除。契约 §2/§3 明确写的是**闭区间**，且 §3 的示例本身就是 `start=end=2026-06-18`。 |
| 修复 | 改成 `["date >= ?", "date <= ?"]`。`unit_price_check`（`date <= ?`）与 `daily_metrics` 的日期循环本来就对，只有 `_where` 这一处需要改。 |
| 回归测试 | `test_end_date_is_inclusive`、`test_single_day_range_works`、`test_daily_covers_every_day_inclusive`、`test_daily_single_day`（`tests/test_metrics.py`）。修复前红灯：<br>`E AssertionError: 70 + 8，7/02 必须算进来` / `assert 80.0 == 78.0`<br>`E AssertionError: 同一天区间不能返回 0` / `assert 0.0 == 70.0`<br>修复后四个用例全绿。本题单独立贡献：`net +4579`（M01）、M04 从 `0.0` 变 `3625.0`、M06 的 6/12 从 `0` 变 `998.0`。 |

## D-002：退款行被 `is_refund = 0` 整个排除，`refund_amount` 恒为 0

| M01 |  |
|---|---|
| 现象 | M01/M02/M03 的 `refund_amount` **一律是 `0.0`**，期望分别是 `953.0` / `107.0` / `16.0`。三个月、三个不同筛选条件都恰好没有退款，不可能。 |
| 假设 | ① 这几个月真的没有退款行；② 退款行被 SQL 过滤掉了；③ 退款额算出来了但没往上带。 |
| 验证 | 先确认数据在：`SELECT COUNT(*) FROM sales_clean WHERE is_refund=1` → 94 行，六月区间内 `SUM(amount_cents)` = `-953.00`。排除假设①。<br>读 `query_metrics` 的 SQL：结尾是 `FROM sales_clean WHERE %s AND is_refund = 0` —— 退款行被 WHERE 排除；且 `SELECT` 的第二个投影位**直接写死常量 `0`**，`refund_cents` 永远是 0，第 116 行 `yuan(-refund_cents)` 于是恒返回 `0.0`。确认假设②③。<br>在旧表上手工把 `-953.00` 加回净额：`157462.0 → 156509.0`，与期望 `156757.0` 的差距从 `+4579` 缩到 `-248`（剩下的正是 D-005 的脏行）。 |
| 根因 | `kbqa/tools.py:96-107`（原始版）。① 第 103 行 `AND is_refund = 0` 把退款行排除；② 第 100 行第二个投影位写死 `0`。违反 KB-001 §4「净营业额 = 销售行金额之和 **+** 退款行金额之和」，以及 §6 记录的 v3 变更第 1 条（v2 才是剔除负金额行，本代码实现的是 v2 口径）。 |
| 修复 | 改用条件聚合，一次查询同时算两条线，不再过滤退款行：`SUM(CASE WHEN is_refund=0 THEN amount_cents ELSE 0 END)` 得销售行合计，`SUM(CASE WHEN is_refund=1 THEN amount_cents ELSE 0 END)` 得退款行合计（负数），最后 `net_cents = 销售 + 退款`。 |
| 回归测试 | `test_refund_reduces_net_revenue`、`test_refund_amount_is_reported`（`tests/test_metrics.py`）。修复前红灯：<br>`E AssertionError: 原来这里恒为 0.0` / `assert 0.0 == 10.0`<br>夹具里 7/01 S01 销售 80 元、退款 10 元，期望净额 70；修复前返回 80（退款没扣）。修复后 M01 的 `refund_amount` 命中 `953.0`。 |

## D-003：`orders` 用 `COUNT(*)` 数明细行，多行订单被算成多单

| M01 |  |
|---|---|
| 现象 | M01 报 `orders=4272`，期望 `4311`；连带 `aov` 报 `35.79`，期望 `36.36`。M02 报 `865` / 期望 `875`，M03 报 `452` / 期望 `461`。 |
| 假设 | ① `orders` 口径错了；② `aov` 分母错了；③ 两者是同一处错误引起的。 |
| 验证 | 读 SQL，`orders` 位是 `COUNT(*)` —— 数的是**明细行数**。一张订单点两个商品会有两行，`COUNT(*)` 会算成两单。这是假设③：**同一个根因**（分母不是"订单数"），`orders` 和 `aov` 一起错。<br>在旧表上对比：开区间 `COUNT(*)=4272`（正是评测报的值），而 `COUNT(DISTINCT order_id)=4178`。<br>注意 `COUNT(*)` 只会把订单数**数多**，而评测报的 `4272` 比期望 `4311` 还**小** —— 说明 D-001（少一天）与 D-005（脏行）的方向影响更大，`COUNT(*)` 这条是叠加在里面的独立口径错误。全部修好后清洗表上 `COUNT(*)=4410` vs `DISTINCT=4311`，多算 99 单。 |
| 根因 | `kbqa/tools.py:101`（原始版）的 `COUNT(*)`。违反 KB-001 §4「有效订单数 = 销售行中**不同 `order_id`** 的个数，多行订单算 1 单」，以及 §6 的 v3 变更第 3 条（v2 用明细行数，多行订单算成多单，客单价偏低）。 |
| 修复 | 改成 `COUNT(DISTINCT CASE WHEN is_refund = 0 THEN order_id END)` —— 只数销售行的订单号，退款行不单独计为订单（§4）。 |
| 回归测试 | `test_orders_counts_distinct_order_id`、`test_refund_rows_are_not_counted_as_orders`、`test_multi_row_order_still_one_order`、`test_aov_divides_by_orders_not_rows`（`tests/test_metrics.py`）。修复前红灯：<br>`E AssertionError: O1、O2 两单；O1 的两行明细不能算两单`<br>`E AssertionError: 70 ÷ 2 = 35.0；若按 3 行明细算会得到 23.33`<br>夹具 O1 两行（10+20 元）、O2 一行（50 元）：正确 2 单、客单价 35.0；`COUNT(*)` 给出 3 单、23.33，正是 KB-001 §6 描述的 v2 错误特征。修复后 M01 `orders=4311`、`aov=36.36` 全部命中。 |

## D-004：`qty` 没有减退款行

| M01 |  |
|---|---|
| 现象 | M01 报 `qty=6360`，期望 `6496`；M02 报 `1370` / 期望 `1395`；M03 报 `678` / 期望 `689`。 |
| 假设 | ① 退款行的数量没减；② 区间边界少了一天；③ 脏行。 |
| 验证 | 读 SQL：`qty` 位是 `COALESCE(SUM(qty), 0)`，且整条 SQL 被 `is_refund = 0` 过滤 —— 退款行的数量**完全没参与**运算。这是独立于 D-001/D-005 的口径错误。<br>量级核对：六月区间退款行 `SUM(qty)=36`（M01 方向对得上，原代码漏减 36 件）；M02 区间退款行 `qty=6`，清洗后销售行 `1401`、`1401-6=1395` 正是期望值。 |
| 根因 | `kbqa/tools.py:102`（原始版）的 `COALESCE(SUM(qty), 0)`，配合第 103 行的 `is_refund = 0`。违反 KB-001 §4「销量 = 销售行 `qty` 之和 **减去** 退款行 `qty` 之和」。 |
| 修复 | 改成 `COALESCE(SUM(CASE WHEN is_refund = 0 THEN qty ELSE -qty END), 0)` —— 退款行数量按负数累加，等价于相减，与净营业额的写法保持一致。 |
| 回归测试 | `test_qty_subtracts_refunds`（`tests/test_metrics.py`）。修复前红灯：<br>`E AssertionError: 2+1+1 销售行 = 4，减退款 1 = 3`（实际返回 4）<br>修复后 M01 `qty=6496`、M02 `1395`、M03 `689` 全部命中。 |

## D-005：清洗层整体缺失，脏行全留在表里

| M01 |  |
|---|---|
| 现象 | 上面 D-001～D-004 全部修好后，M01 的 `net_revenue` 仍差 `248`（`156509.0` vs 期望 `156757.0`），`orders`、`qty` 也对不上。说明还有一层更上游的问题。 |
| 假设 | ① 指标 SQL 还有别处错；② 数据本身不干净，脏行混进了统计。 |
| 验证 | 读 `kbqa/cleaning.py` 的 `clean_rows`（原始版）：函数体只有 `parse_amount` / `parse_qty` 两次解析就 `kept.append(...)`，`report.removed` 的六个计数器**没有任何一处 `+= 1`** —— KB-001 §2 的规范化与 §3 的六条剔除规则**一条都没实现**。<br>交叉验证：`/api/health` 的 `valid_sales_rows` 报 `18628`（等于原始行数），而契约 §1 声明的正确值是 **`18290`**。<br>实际脏行：空 `amount` 150 行、`qty<=0` 30 行、门店编号不在维表 10 行、商品编号不在维表 40 行。这些行留在表里直接污染了上面所有指标。<br>另外 `date` 是原样抄入的，`SELECT LENGTH(date), COUNT(*) ... GROUP BY 1` 得到 10/9/8/3/0 五种长度 —— 混着 ISO、`YYYY/M/D`、`DD-MM-YYYY` 三种格式，而查询是**按字符串比较**日期，非 ISO 的行永远查不出来。 |
| 根因 | `kbqa/cleaning.py:77-102`（原始版）。docstring 自称「把 sales 原样搬过来……查询的时候直接比字符串」，实现确实如此：① 第 83-85 行解析失败时 `cents = 0`，空金额没剔除反而塞了 0 进去（违反 §3.2「不回填，直接剔除」）；② 第 86 行 `parse_qty(...) or 0`，`qty<=0` 没剔除（违反 §3.3）；③ 第 90-91 行 `date`/`store_id`/`product_id` 未按 §2.1、§2.2 规范化，也没有 §3.4/§3.5 的外键检查；④ 无去重（违反 §3.6）。 |
| 修复 | 重写 `clean_rows`，严格按 **先 §2 规范化、再 §3 六条剔除** 的顺序。顺序是关键：规则 4、5 是外键检查，必须排在规范化之后，否则 `s01 `、` s03` 这类「规范化后合法」的编号会被误删（KB-001 §7.2 专门点了这个坑）。新增 `normalize_date()`（三种格式 → `YYYY-MM-DD`，`DD-MM-YYYY` **日在前**）与 `normalize_id()`（trim + upper）；`clean_rows` 增加 `store_ids` / `product_ids` 参数接收维表合法编号，由 `build_clean_db` 传入。去重键用规范化后的**七个字段**全比对（只用 `order_id` 会吃掉合法的多行订单明细，§7.3）。 |
| 回归测试 | `tests/test_cleaning.py`（22 个）+ `tests/test_metrics_e2e.py`（9 个）。修复前红灯：<br>`E assert 18628 == 18290`（`test_valid_sales_rows`）<br>`E assert 0 == 8`（`test_cleaning_report_is_not_all_zero`）<br>`test_date_formats_are_normalized` 的 5 个参数化用例全红<br>修复后台账：`1_unparseable_date=8`、`2_empty_amount=150`、`3_qty_le_zero=30`、`4_store_not_in_stores=10`、`5_product_not_in_products=40`、`6_duplicate_row=100`，`kept_rows=`**`18290`**，且 `18628 == 18290 + 338` 自洽。<br>**交叉验证**：`18290` 与契约 §1 声明的正确值精确一致，且这个数不来自我的实现 —— 规则顺序若错不可能对上。<br>**关于重复行 100**：原始字段逐字比较只有 70 行重复；§3.6 要求「**规范化后**完全相同」，所以 `s01` 与 `S01 `、`¥38.00` 与 `38.00` 归一后算同一行，多出 30 行。这正是 §2 必须先于 §3 的直接证据。 |

## D-006：`/api/metrics/daily` 的日期边界与汇总口径不一致

| M06 |  |
|---|---|
| 现象 | M06（`GET /api/metrics/daily?start=2026-06-08&end=2026-06-12&store_id=S03`）只有最后一天 `2026-06-12` 报错：`net_revenue` 实际 `0.0`、期望 `998.0`；`orders` 实际 `0`、期望 `27`；`aov` 实际 `null`、期望 `36.96`。前 4 天本来就该是 0，所以看起来"只有末日错"。 |
| 假设 | ① `daily` 有独立的日期 bug；② 与 D-001 同源；③ 聚合口径不同。 |
| 验证 | 在旧表上按原始 SQL 复现：`SELECT date FROM sales_clean WHERE date>='2026-06-08' AND date<'2026-06-12' AND store_id='S03' GROUP BY date` → **返回空**。`2026-06-12` 被右开区间排除，正是报告里唯一报错的那天。确认假设②：与 D-001 同源。<br>同时检查 `daily_metrics` 的 orders 写法：`COUNT(DISTINCT CASE WHEN is_refund=0 THEN order_id END)` —— **这个写法本来就是对的**，符合契约 §3。所以 M06 的 `orders` 错是因为整天数据没被选出（返回 0），不是因为聚合口径错。<br>另外确认返回结构：`days[]` 必须覆盖区间**每一天**，包括没有营业额的日子（契约 §3）。 |
| 根因 | `kbqa/tools.py:122-134` 的 `daily_metrics` 复用了 `_where`，因此继承了 D-001 的右开区间。`daily` 自身的聚合口径（`COUNT(DISTINCT ...)`）正确，**不需要改**。 |
| 修复 | 无需单独改动 —— D-001 把 `_where` 修正为闭区间后，`daily_metrics` 自动正确。这里单列一条是为了说明：M06 的失败**根因与 M01~M04 相同**，不是 `daily` 独有的 bug，避免以后有人去改 `daily_metrics` 的聚合逻辑而引入回归。 |
| 回归测试 | `test_daily_covers_every_day_inclusive`、`test_daily_single_day`、`test_daily_orders_are_distinct`（`tests/test_metrics.py`），以及 `test_daily_sums_to_summary`（`tests/test_metrics_e2e.py`，断言逐日累加 == 区间汇总）。修复前 `daily_single_day` 红灯 `assert 0.0 == 70.0`；修复后 6/12 命中 `net=998.0, orders=27`。 |

## D-007：`by_store` 等分组接口受同样口径影响（附带修复）

| M01–M06 |  |
|---|---|
| 现象 | 单店/单商品的题（M02 带 `store_id=S02`、M03 带 `product_id=P21`）与全店题（M01）**同时**错，且错的方向一致。 |
| 假设 | ① 门店/商品筛选参数处理有额外 bug；② 就是 D-001～D-005 传导下来的。 |
| 验证 | 读代码：`by_store`、`by_store_category`、`payment_mix`、`top_products`、`compare_periods` 全部调用 `query_metrics` 或共用 `_where`。所以 D-001～D-005 修好后它们一起正确，**没有独立的筛选 bug**。<br>用一致性断言反证：在修复后的表上，`sum(by_store 各店 net) == query_metrics(全店) net`，`sum(orders)`、`sum(qty)` 同样相等 —— 说明分组与总口径自洽。 |
| 根因 | 无独立根因；这些接口共用 `_where` 与 `query_metrics`，属于 D-001～D-005 的传导范围。 |
| 修复 | 无需额外改动。记录此条是为了说明**改动会波及哪些接口**：修 `_where` 和 `query_metrics` 会同时改变 `by_store`、`by_store_category`、`payment_mix`、`top_products`、`compare_periods` 的输出，回归测试需要覆盖这些调用方，不能只测 `summary`。 |
| 回归测试 | `test_by_store_totals_match_whole_range`、`test_compare_periods_uses_same_definition`（`tests/test_metrics.py`）、`test_all_stores_july_is_consistent`（`tests/test_metrics_e2e.py`）。修复前 `by_store` 求和与总数不一致（红灯）；修复后三条全部通过。 |

## D-008：测试是"冒烟级"，口径错了也全绿

| M01–M06 |  |
|---|---|
| 现象 | 交接文档称"测试全部通过"，但评测 `metrics` 只有 **1/6**。上面 D-001～D-005 这些明显错误（`refund_amount` 恒为 0、`valid_sales_rows` 报 18628）在原有测试里**一个都没被拦住**。 |
| 假设 | ① 原有测试覆盖不足；② 测试断言写错了。 |
| 验证 | 读 `starter/tests/test_api.py`：断言全部是 `status_code == 200`、字段存在、`answer` 非空字符串，**没有任何一处校验数字、引用或口径**。所以 `refund_amount=0.0` 这种错误能全绿通过。确认假设①。<br>反证：把 D-001～D-005 的修复临时回滚（`git checkout HEAD -- kbqa/tools.py kbqa/cleaning.py`）后跑新测试，**43 个用例立刻变红**（`43 failed, 6 passed`）—— 说明这些缺陷属于"测试能覆盖但原来没写"。 |
| 根因 | `starter/tests/` 缺少带**期望值**的断言。冒烟测试只能证明"没崩"，不能证明"算对了"，而本题的评分核心正是数字正确性。 |
| 修复 | 补三层测试（数量为 `pytest --collect-only` 实测）：<br>`tests/test_cleaning.py`（22）—— KB-001 §2 规范化 + §3 六条剔除，逐条覆盖；<br>`tests/test_metrics.py`（18）—— 用手工构造的小表测 §4 每个口径，每行数据都能手算，失败时一眼定位是哪个口径；<br>`tests/test_metrics_e2e.py`（9）—— 真实数据端到端，钉死评测报出的具体数字。<br>加上原有 `test_api.py`(17)、`test_config.py`(16)、`test_streaming.py`(19)，共 **101 个测试**。 |
| 回归测试 | 修复前：三个新文件 **43 红 / 6 绿**；修复后：**101 全绿**。<br>两点自我纠错记录：<br>① `test_metrics.py` 里我最初把 `amount_cents=800` 读成 ¥16.00（实际 ¥8.00），3 个断言期望值算错。核对后确认是**我的算术错、不是实现错**，改的是测试而不是去迁就实现 —— 记在这里是因为"把测试改绿"也可能是把测试改错。<br>② `test_metrics.py`（手算小表）与 `test_metrics_e2e.py`（真实数据）互相交叉验证，两者若不一致说明口径实现有隐含依赖。 |
