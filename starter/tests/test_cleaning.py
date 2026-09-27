"""清洗规则：KB-001 §2（规范化）与 §3（六条剔除，按序执行）。

这一组是**指标算错的总根源**：`clean_rows` 原来是个空壳，六条规则一条都没执行，
脏行全留在表里（`kept_rows=18628`，台账六项全 0）。指标再怎么写都救不回来。

所以这里的测试盯的是**台账数字**，不是"表里有多少行"—— 台账对不上就说明规则没跑。
"""

from __future__ import annotations

import sqlite3

import pytest

from kbqa.cleaning import REMOVAL_REASONS, clean_rows, parse_amount, parse_qty


def rows(items: list[tuple]) -> list[sqlite3.Row]:
    """把元组列表包成 `clean_rows` 认的形状（它按字段名取值）。"""
    keys = ("order_id", "date", "store_id", "product_id", "qty", "amount", "payment")
    return [dict(zip(keys, item)) if isinstance(item, tuple) else item for item in items]


def run(items, stores=("S01",), products=("P01",)):
    """跑一遍清洗，返回 (保留行, 台账)。维表用最小的假数据。"""
    return clean_rows(
        rows(list(items)),
        store_ids=set(stores),
        product_ids=set(products),
    )


# -- §2.1 大小写与空白 ---------------------------------------------------------


def test_store_and_product_are_trimmed_and_uppercased():
    """`s01 `、` s01`、`s01` 规范化后都是 `S01`，不是脏数据（§2.1、§7.2）。"""
    kept, report = run(
        [
            ("O1", "2026-07-01", "s01", " p01 ", "1", "10.00", "现金"),
            ("O2", "2026-07-01", " s01", "p01", "1", "10.00", "现金"),
            ("O3", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
        ]
    )
    assert report.kept_rows == 3, "规范化后都是合法编号，三条都该留下"
    assert {r[2] for r in kept} == {"S01"}
    assert {r[3] for r in kept} == {"P01"}


def test_normalization_happens_before_foreign_key_check():
    """顺序反了会误删真实订单（§7.2 明确点出这个坑）。"""
    _, report = run([("O1", "2026-07-01", "s01", "p01", "1", "10.00", "现金")])
    assert report.removed["4_store_not_in_stores"] == 0
    assert report.removed["5_product_not_in_products"] == 0
    assert report.kept_rows == 1


# -- §2.2 三种日期格式 ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-25", "2026-07-25"),
        ("2026/7/25", "2026-07-25"),
        ("2026/07/05", "2026-07-05"),
        ("25-07-2026", "2026-07-25"),  # 日在前的旧 POS 格式
        ("07-06-2026", "2026-06-07"),
    ],
)
def test_date_formats_are_normalized(raw, expected):
    kept, _ = run([("O1", raw, "S01", "P01", "1", "10.00", "现金")])
    assert kept[0][1] == expected, "%r 应归一成 %s" % (raw, expected)


def test_day_first_is_not_month_first():
    """`25-07-2026` 是 7 月 25 日；搞反了会变成"没有 25 月"。

    手册特意说这类样本的"日"会大于 12，就是用来验证解析方向的（§2.2）。
    """
    kept, _ = run([("O1", "25-07-2026", "S01", "P01", "1", "10.00", "现金")])
    assert kept[0][1] == "2026-07-25"


def test_unparseable_date_is_removed():
    kept, report = run(
        [
            ("O1", "不是日期", "S01", "P01", "1", "10.00", "现金"),
            ("O2", "", "S01", "P01", "1", "10.00", "现金"),
            ("O3", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
        ]
    )
    assert report.removed["1_unparseable_date"] == 2
    assert report.kept_rows == 1


# -- §2.3 金额 ----------------------------------------------------------------


def test_currency_symbol_is_stripped_not_discarded():
    """`¥38.00` 和 `38.00` 是同一个金额，带符号的行**必须保留**（§2.3、§7.1）。"""
    kept, report = run(
        [
            ("O1", "2026-07-01", "S01", "P01", "1", "¥38.00", "现金"),
            ("O2", "2026-07-01", "S01", "P01", "1", "38.00", "现金"),
        ]
    )
    assert report.kept_rows == 2, "带 ¥ 的是可恢复的脏值，不能整行丢掉"
    assert [r[5] for r in kept] == [3800, 3800]


def test_parse_amount_variants():
    assert parse_amount("¥38.00") == (3800, "ok")
    assert parse_amount("38.00") == (3800, "ok")
    assert parse_amount(" 38 ") == (3800, "ok")
    assert parse_amount("-38.00")[0] == -3800, "负金额是退款行，要能解析出来"
    assert parse_amount("")[1] == "empty"
    assert parse_amount(None)[1] == "empty"


def test_empty_amount_is_removed_not_backfilled():
    """空金额直接剔除，**不回填**（§3.2，这是 v3 相对 v2 的变更之一）。"""
    _, report = run(
        [
            ("O1", "2026-07-01", "S01", "P01", "5", "", "现金"),
            ("O2", "2026-07-01", "S01", "P01", "5", None, "现金"),
            ("O3", "2026-07-01", "S01", "P01", "5", "50.00", "现金"),
        ]
    )
    assert report.removed["2_empty_amount"] == 2
    assert report.kept_rows == 1


# -- §2.4 / §3.3 数量 ----------------------------------------------------------


def test_qty_le_zero_is_removed():
    _, report = run(
        [
            ("O1", "2026-07-01", "S01", "P01", "0", "10.00", "现金"),
            ("O2", "2026-07-01", "S01", "P01", "-2", "10.00", "现金"),
            ("O3", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
        ]
    )
    assert report.removed["3_qty_le_zero"] == 2
    assert report.kept_rows == 1


def test_parse_qty():
    assert parse_qty("3") == 3
    assert parse_qty(" 3 ") == 3
    assert parse_qty("3.0") == 3
    assert parse_qty("abc") is None
    assert parse_qty("") is None


# -- §3.4 / §3.5 外键 ---------------------------------------------------------


def test_unknown_store_is_removed():
    _, report = run(
        [
            ("O1", "2026-07-01", "S99", "P01", "1", "10.00", "现金"),
            ("O2", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
        ]
    )
    assert report.removed["4_store_not_in_stores"] == 1
    assert report.kept_rows == 1


def test_unknown_product_is_removed():
    _, report = run(
        [
            ("O1", "2026-07-01", "S01", "P99", "1", "10.00", "现金"),
            ("O2", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
        ]
    )
    assert report.removed["5_product_not_in_products"] == 1
    assert report.kept_rows == 1


# -- §3.6 重复行 vs 合法多行订单 -----------------------------------------------


def test_exact_duplicate_rows_are_deduped():
    """七个字段规范化后完全相同的行，只留 1 条（§3.6）。"""
    row = ("O1", "2026-07-01", "S01", "P01", "1", "10.00", "现金")
    kept, report = run([row, row, row])
    assert report.removed["6_duplicate_row"] == 2
    assert report.kept_rows == 1


def test_multi_item_order_is_kept():
    """一张订单点两个不同商品 → 两行明细都保留（§3.6、§7.3）。

    这一条和上一条是一对：只靠 order_id 去重会把真实的多行订单吃掉。
    """
    kept, report = run(
        [
            ("O1", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
            ("O1", "2026-07-01", "S01", "P02", "1", "20.00", "现金"),
        ],
        products=("P01", "P02"),
    )
    assert report.removed["6_duplicate_row"] == 0
    assert report.kept_rows == 2, "共用订单号的不同商品行必须全部保留"


def test_duplicate_detection_uses_normalized_values():
    """规范化之后才比对：大小写/空白不同但实际相同的行，也算重复（§3.6）。"""
    kept, report = run(
        [
            ("O1", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
            ("O1", "2026-07-01", "s01", "p01", "1", "¥10.00", "现金"),
        ]
    )
    assert report.removed["6_duplicate_row"] == 1
    assert report.kept_rows == 1


# -- 退款行与台账 --------------------------------------------------------------


def test_refund_rows_are_kept():
    """负金额行（退款）过完六条规则要**保留**，§4 要靠它们算净营业额和退款额。"""
    kept, report = run(
        [
            ("O1", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),
            ("O2", "2026-07-01", "S01", "P01", "1", "-10.00", "现金"),
        ]
    )
    assert report.kept_refund_rows == 1
    assert report.kept_sales_rows == 1
    assert report.kept_rows == 2
    assert kept[1][7] == 1, "is_refund 标记要打上"


def test_report_accounts_for_every_row():
    """脏行必须有去处：要么留下，要么记在某条规则下。"""
    items = [
        ("O1", "2026-07-01", "S01", "P01", "1", "10.00", "现金"),   # 留
        ("O2", "坏日期", "S01", "P01", "1", "10.00", "现金"),        # 规则 1
        ("O3", "2026-07-01", "S01", "P01", "1", "", "现金"),        # 规则 2
        ("O4", "2026-07-01", "S01", "P01", "0", "10.00", "现金"),   # 规则 3
        ("O5", "2026-07-01", "S99", "P01", "1", "10.00", "现金"),   # 规则 4
        ("O6", "2026-07-01", "S01", "P99", "1", "10.00", "现金"),   # 规则 5
    ]
    _, report = run(items + [items[0]])  # 最后一条是重复行
    removed = sum(report.removed[k] for k in REMOVAL_REASONS)
    assert report.raw_rows == 7
    assert report.kept_rows == 1
    assert removed == 6, "每条被剔除的行都要记在对应规则下"
    assert report.raw_rows == report.kept_rows + removed


def test_removal_order_matters():
    """规则按序执行。一行同时踩中多条时，记在**靠前**的那条上。

    顺序错了会让台账数字对不上（例如先做外键检查，`s01 ` 就会被误删）。
    """
    # 既坏日期又坏门店：应记在规则 1
    _, report = run([("O1", "坏日期", "S99", "P01", "1", "10.00", "现金")])
    assert report.removed["1_unparseable_date"] == 1
    assert report.removed["4_store_not_in_stores"] == 0
