"""端到端：真实数据上的数字。

这一组用真实作业数据，把**评测报出来的那组数字**钉死。它们是最终验收标准：
口径改对了，这几个数必然对上；对不上就是还有地方没修。

设计原则：只断言**能独立推导出来的数**（KB-001 手册 + 原始库），不复制实现的中间产物。
"""

from __future__ import annotations

import sqlite3

import pytest

from kbqa.cleaning import build_clean_db
from kbqa.tools import DataTools

#: 评测里那个失败用例：S02 2026 年 7 月。
#: 期望值来自 KB-001 §4 口径 + 原始库，不依赖本实现。
EXPECTED_S02_JULY = {
    "net_revenue": 41740.0,
    "refund_amount": 107.0,
    "orders": 875,
    "qty": 1395,
    "aov": 47.7,
}

#: 契约 §1：按 KB-001 清洗后保留的明细行数（销售行 + 退款行）。
EXPECTED_VALID_ROWS = 18290


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """从原始库重建一份清洗表。找不到原始库就跳过（评测环境可能不给）。"""
    from kbqa.config import load_settings

    settings = load_settings()
    if not settings.source_db.exists():
        pytest.skip("找不到原始库：%s" % settings.source_db)
    target = tmp_path_factory.mktemp("clean") / "clean.db"
    report = build_clean_db(settings.source_db, target)
    tools = DataTools(target)
    yield tools, report
    tools.close()


def test_valid_sales_rows(built):
    """契约 §1 的 `valid_sales_rows`：清洗后保留的行数。

    原始 18628 行，剔除后应为 18290 行。空壳实现会原样留下 18628 行。
    """
    tools, _ = built
    assert tools.valid_sales_rows() == EXPECTED_VALID_ROWS


def test_cleaning_report_is_not_all_zero(built):
    """六条规则都要真的删掉东西 —— 台账全 0 就是没执行。

    关于重复行的 100（原始字段逐字比较只有 70 行完全相同）：
    §3.6 要求的是"**规范化后**所有字段完全相同"，所以 `s01` 与 `S01 `、
    `¥38.00` 与 `38.00`、`2026/7/5` 与 `2026-07-05` 这些写法要算成同一行。
    规范化之后多暴露 30 行重复，这正是 §2、§3 的先后顺序在起作用。
    """
    _, report = built
    removed = report.removed
    assert removed["1_unparseable_date"] == 8
    assert removed["2_empty_amount"] == 150
    assert removed["3_qty_le_zero"] == 30
    assert removed["4_store_not_in_stores"] == 10
    assert removed["5_product_not_in_products"] == 40
    assert removed["6_duplicate_row"] == 100


def test_rows_are_accounted_for(built):
    """原始行数 = 保留 + 剔除，一行都不能凭空消失或多出来。"""
    _, report = built
    removed = sum(v for k, v in report.removed.items() if k != "note_unparseable_amount")
    assert report.raw_rows == 18628
    assert report.raw_rows == report.kept_rows + removed


def test_dates_are_all_iso(built):
    """清洗后日期必须全部归一成 `YYYY-MM-DD`。

    原来混着 `Y/M/D` 和 `DD-MM-YYYY`，而查询是**按字符串比较**的，
    非 ISO 的行永远查不出来。
    """
    tools, _ = built
    bad = tools.conn.execute(
        "SELECT COUNT(*) FROM sales_clean WHERE date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
    ).fetchone()[0]
    assert bad == 0, "还有 %d 行日期不是 ISO 格式" % bad


def test_no_dirty_rows_survive(built):
    """脏行不能在表里留下。"""
    tools, _ = built
    conn = tools.conn
    assert conn.execute("SELECT COUNT(*) FROM sales_clean WHERE amount_cents = 0").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sales_clean WHERE qty <= 0").fetchone()[0] == 0
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sales_clean WHERE store_id NOT IN (SELECT store_id FROM stores)"
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sales_clean WHERE product_id NOT IN "
            "(SELECT product_id FROM products)"
        ).fetchone()[0]
        == 0
    )


def test_no_duplicate_rows_survive(built):
    """七个字段完全相同的行不该有第二份。"""
    tools, _ = built
    dupes = tools.conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT order_id, date, store_id, product_id, qty, amount_cents, payment
            FROM sales_clean
            GROUP BY order_id, date, store_id, product_id, qty, amount_cents, payment
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert dupes == 0


def test_s02_july_matches_eval(built):
    """**评测报出来的那个失败用例**。五个字段都要对上。"""
    tools, _ = built
    actual = tools.query_metrics("2026-07-01", "2026-07-31", "S02")
    for field, expected in EXPECTED_S02_JULY.items():
        assert actual[field] == pytest.approx(expected, abs=0.01), "%s 期望 %s，实际 %s" % (
            field,
            expected,
            actual[field],
        )


def test_all_stores_july_is_consistent(built):
    """按门店拆分求和 = 不拆分总数，真实数据上也要成立。"""
    tools, _ = built
    whole = tools.query_metrics("2026-07-01", "2026-07-31")
    parts = tools.by_store("2026-07-01", "2026-07-31")["stores"]
    assert round(sum(s["net_revenue"] for s in parts), 2) == pytest.approx(
        whole["net_revenue"], abs=0.01
    )
    assert sum(s["orders"] for s in parts) == whole["orders"]
    assert sum(s["qty"] for s in parts) == whole["qty"]


def test_daily_sums_to_summary(built):
    """逐日累加 = 区间汇总，两条链路必须自洽。"""
    tools, _ = built
    days = tools.daily_metrics("2026-07-01", "2026-07-31", "S02")["days"]
    summary = tools.query_metrics("2026-07-01", "2026-07-31", "S02")
    assert len(days) == 31
    assert round(sum(d["net_revenue"] for d in days), 2) == pytest.approx(
        summary["net_revenue"], abs=0.01
    )
    assert sum(d["orders"] for d in days) == summary["orders"]
