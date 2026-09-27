"""指标口径：KB-001 §4 + 契约 §2/§3。

用一张**手工造的小表**，每一行的期望值都能手算出来，这样测试失败时一眼能看出
是哪个口径错了。真实数据（18628 行）只在最后两个端到端用例里用。
"""

from __future__ import annotations

import sqlite3

import pytest

from kbqa.tools import DataTools

SCHEMA = """
CREATE TABLE stores (store_id TEXT PRIMARY KEY, store_name TEXT, category TEXT, district TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT,
                       product_category TEXT, unit_price REAL);
CREATE TABLE sales_clean (
    order_id TEXT, date TEXT, store_id TEXT, product_id TEXT,
    qty INTEGER, amount_cents INTEGER, payment TEXT, is_refund INTEGER
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


@pytest.fixture
def db(tmp_path):
    """造一张干净的小表。

    数据设计（KB-001 §4 的每个口径都有一个专门的样本）：

      O1 两行（多行订单）  7/01 S01  10.00×2 + 20.00×1  → 1 单，30 元
      O2 一行              7/01 S01  50.00×1            → 1 单，50 元
      O3 退款行            7/01 S01  -10.00×1           → 退款 10 元，不计订单
      O4 一行              7/02 S01   8.00×2            → 1 单，8 元
      O5 一行              7/02 S02   5.00×1            → 另一家店

    `amount_cents` 是**分**：`800` 是 8.00 元，不是 16.00 元。

    7/01 S01 合计：净额 10+20+50-10 = 70，退款 10，订单 2（O1、O2），销量 2+1+1-1 = 3
    7/01~7/02 S01 ：净额 70+8 = 78，订单 3，销量 3+2 = 5
    P02 在 7/01~7/02 S01：20 + 8 = 28
    """
    path = tmp_path / "clean.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO stores VALUES (?,?,?,?)",
        [("S01", "一店", "直营", "东区"), ("S02", "二店", "加盟", "西区")],
    )
    conn.executemany(
        "INSERT INTO products VALUES (?,?,?,?)",
        [("P01", "牛肉poke", "主食", 10.0), ("P02", "乌龙茶", "饮品", 8.0)],
    )
    conn.executemany(
        "INSERT INTO sales_clean VALUES (?,?,?,?,?,?,?,?)",
        [
            ("O1", "2026-07-01", "S01", "P01", 2, 1000, "现金", 0),
            ("O1", "2026-07-01", "S01", "P02", 1, 2000, "现金", 0),
            ("O2", "2026-07-01", "S01", "P01", 1, 5000, "微信", 0),
            ("O3", "2026-07-01", "S01", "P01", 1, -1000, "现金", 1),
            ("O4", "2026-07-02", "S01", "P02", 2, 800, "现金", 0),
            ("O5", "2026-07-02", "S02", "P01", 1, 500, "现金", 0),
        ],
    )
    conn.commit()
    conn.close()
    tools = DataTools(path)
    yield tools
    tools.close()


# -- §4 净营业额：退款行要计入 -------------------------------------------------


def test_run_sql_returns_error_instead_of_raising(db):
    """SQL 写错要返回结构化错误，不能抛出去。

    模型自己写 SQL（`run_sql` 工具）时写错表名是常事 —— 实测它就写过
    `FROM kb_chunks`（那是 /api/health 的字段名，不是表）。
    抛出去会把整轮问答打断，最后只剩一句兜底拒答、直接拿 0 分；
    返回错误则能让模型下一轮自己改一版再试。
    """
    bad = db.run_sql("SELECT * FROM kb_chunks")
    assert "error" in bad, "写错表名应该返回 error，而不是抛异常"
    assert "kb_chunks" in bad["error"]
    assert bad["rows"] == []

    # 正常查询照旧能用
    ok = db.run_sql("SELECT COUNT(*) AS n FROM sales_clean")
    assert "error" not in ok
    assert ok["rows"][0]["n"] >= 1


def test_refund_reduces_net_revenue(db):
    """净营业额 = 销售行之和 + 退款行之和（退款行是负数，等于相减）—— §4。

    原来把退款行整个排除，净额会虚高，退款额恒为 0。
    """
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["net_revenue"] == 70.0, "30+50-10，退款必须扣掉"


def test_refund_amount_is_reported(db):
    """退款金额 = 退款行金额之和的绝对值 —— §4。"""
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["refund_amount"] == 10.0, "原来这里恒为 0.0"


# -- §4 有效订单数：不同 order_id，不是明细行数 --------------------------------


def test_orders_counts_distinct_order_id(db):
    """有效订单数 = 销售行中**不同 order_id** 的个数，多行订单算 1 单 —— §4。

    O1 有 2 行明细，只能算 1 单。用 COUNT(*) 会算成 2。
    """
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["orders"] == 2, "O1、O2 两单；O1 的两行明细不能算两单"


def test_refund_rows_are_not_counted_as_orders(db):
    """退款行不单独计为订单 —— §4。"""
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["orders"] == 2, "O3 是退款行，不算订单"


def test_multi_row_order_still_one_order(db):
    """同一订单号在不同商品上各占一行，订单数仍只算 1（§4、§7.3）。"""
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01", "P01")
    assert result["orders"] == 2, "O1 的 P01 行 + O2 的 P01 行 = 2 单"


# -- §4 客单价：分母是有效订单数 -----------------------------------------------


def test_aov_divides_by_orders_not_rows(db):
    """客单价 = 净营业额 ÷ 有效订单数，四舍五入 2 位 —— §4。

    v2 用的是明细行数，会把多行订单算成多单，客单价偏低（§6）。
    """
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["aov"] == 35.0, "70 ÷ 2 = 35.0；若按 3 行明细算会得到 23.33"


def test_aov_is_none_when_no_orders(db):
    """区间内没有数据时数值返 0、aov 返 null，不报错 —— 契约 §2。"""
    result = db.query_metrics("2026-07-09", "2026-07-09", "S01")
    assert result["net_revenue"] == 0.0
    assert result["orders"] == 0
    assert result["aov"] is None


# -- §4 销量：销售行减退款行 ---------------------------------------------------


def test_qty_subtracts_refunds(db):
    """销量 = 销售行 qty 之和 − 退款行 qty 之和 —— §4。"""
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["qty"] == 3, "2+1+1 销售行 = 4，减退款 1 = 3"


# -- 契约 §2 闭区间 ------------------------------------------------------------


def test_end_date_is_inclusive(db):
    """`end` 是**闭区间**（契约 §2）。

    原来用 `date < end`，7/02 的数据会被漏掉。
    """
    result = db.query_metrics("2026-07-01", "2026-07-02", "S01")
    assert result["net_revenue"] == 78.0, "70 + 8，7/02 必须算进来"
    assert result["orders"] == 3


def test_single_day_range_works(db):
    """start == end 时应该返回那一天的数据（契约 §3 的示例就是同一天）。

    原来 `date >= X AND date < X` 恒为空，单日查询永远返回 0。
    """
    result = db.query_metrics("2026-07-01", "2026-07-01", "S01")
    assert result["net_revenue"] == 70.0, "同一天区间不能返回 0"
    assert result["orders"] == 2


# -- 契约 §3 daily -------------------------------------------------------------


def test_daily_covers_every_day_inclusive(db):
    """区间内每一天都要有一条，没有营业额的日期也要出现 —— 契约 §3。"""
    days = db.daily_metrics("2026-07-01", "2026-07-03", "S01")["days"]
    assert [d["date"] for d in days] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert days[-1]["net_revenue"] == 0.0, "没数据的日期返 0"
    assert days[-1]["aov"] is None


def test_daily_single_day(db):
    days = db.daily_metrics("2026-07-01", "2026-07-01", "S01")["days"]
    assert len(days) == 1
    assert days[0]["net_revenue"] == 70.0
    assert days[0]["orders"] == 2


def test_daily_orders_are_distinct(db):
    """daily 的 orders 同样按不同 order_id 算（契约 §3 的字段与 §2 同口径）。"""
    days = db.daily_metrics("2026-07-01", "2026-07-01", "S01")["days"]
    assert days[0]["orders"] == 2, "O1 两行明细只算 1 单"


# -- 门店/商品过滤 -------------------------------------------------------------


def test_store_filter(db):
    result = db.query_metrics("2026-07-01", "2026-07-02", "S02")
    assert result["net_revenue"] == 5.0
    assert result["orders"] == 1


def test_store_id_is_case_insensitive(db):
    """查询参数同样要规范化（§2.1）。"""
    result = db.query_metrics("2026-07-01", "2026-07-02", " s02 ")
    assert result["net_revenue"] == 5.0


def test_product_filter(db):
    result = db.query_metrics("2026-07-01", "2026-07-02", "S01", "P02")
    assert result["net_revenue"] == 28.0, "O1 的 P02 行 20 元 + O4 的 8 元"
    assert result["orders"] == 2


# -- 汇总口径自洽 --------------------------------------------------------------


def test_by_store_totals_match_whole_range(db):
    """按门店拆分再求和，必须等于不拆分的总数 —— 否则分组口径和总口径不一致。"""
    whole = db.query_metrics("2026-07-01", "2026-07-02")
    parts = db.by_store("2026-07-01", "2026-07-02")["stores"]
    assert round(sum(s["net_revenue"] for s in parts), 2) == whole["net_revenue"]
    assert sum(s["orders"] for s in parts) == whole["orders"]
    assert sum(s["qty"] for s in parts) == whole["qty"]


def test_compare_periods_uses_same_definition(db):
    """对比两个区间时，两边的口径必须一致。"""
    result = db.compare_periods(
        "2026-07-01", "2026-07-01", "2026-07-02", "2026-07-02", "S01"
    )
    assert result["period_a"]["net_revenue"] == 70.0
    assert result["period_b"]["net_revenue"] == 8.0
    assert result["delta"]["net_revenue"]["delta"] == -62.0
    assert result["delta"]["net_revenue"]["direction"] == "跌"
