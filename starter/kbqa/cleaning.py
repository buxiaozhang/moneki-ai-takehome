"""把原始 sales 导进 var/clean.db，指标都查这张表。

清洗规则全部来自 KB-001 §2（规范化）与 §3（剔除），**顺序不能变**：
规则 4、5 是外键检查，必须排在规范化之后，否则 `s01 `、` s03` 这类
"规范化后合法"的编号会被当成脏数据误删（手册 §7.2 专门点了这个坑）。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

#: 金额里的 `¥` 去掉再按数字解析。KB-001 §2.3 与 §7.1：这是**可恢复**的脏值，
#: 不是该整行丢掉的坏数据。顺带把全角空格也去掉。
_CURRENCY = str.maketrans("", "", "¥￥ \t　")

REMOVAL_REASONS = (
    "1_unparseable_date",
    "2_empty_amount",
    "3_qty_le_zero",
    "4_store_not_in_stores",
    "5_product_not_in_products",
    "6_duplicate_row",
)

#: KB-001 §2.2：接受的三种日期格式。第三种是旧 POS 的导出格式，**日在前、月在后**。
#: 按顺序试，`%Y-%m-%d` 放前面可以少解析几次。
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y")


def normalize_date(value: Optional[str]) -> Optional[str]:
    """把三种格式的日期统一成 `YYYY-MM-DD`。解析不了返回 None。

    归一化不只是为了好看：下游查指标是**按字符串比较**日期的
    （`date >= '2026-07-01'`），格式不统一的行永远查不出来。

    `DD-MM-YYYY` 必须**日在前**，手册 §2.2 说这类样本的"日"会大于 12，
    就是用来验证解析方向的 —— 搞反了 `25-07-2026` 会变成"没有 25 月"。
    """
    text = (value or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_id(value: Optional[str]) -> str:
    """`store_id` / `product_id`：去首尾空白并转大写（KB-001 §2.1）。"""
    return (value or "").strip().upper()


def parse_amount(value: Optional[str]) -> tuple[Optional[int], str]:
    """返回 (分, 状态)。状态取值：`ok`、`empty`、`bad`。

    KB-001 §2.3 与 §3.2：`¥38.00` 与 `38.00` 是同一个金额；空金额直接剔除，**不回填**。
    负金额（退款行）照常返回，§4 要靠它们算净营业额与退款额。
    """
    text = (value or "").translate(_CURRENCY)
    if not text:
        return None, "empty"
    try:
        cents = int((Decimal(text) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None, "bad"
    return cents, "ok"


def parse_qty(value: Optional[str]) -> Optional[int]:
    """KB-001 §2.4：按整数解析。解析不了的返回 None，会被 §3.3 剔除。"""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


@dataclass
class CleaningReport:
    raw_rows: int = 0
    kept_rows: int = 0
    kept_sales_rows: int = 0
    kept_refund_rows: int = 0
    removed: dict[str, int] = field(default_factory=lambda: {k: 0 for k in REMOVAL_REASONS})
    note_unparseable_amount: int = 0

    def as_dict(self) -> dict:
        return {
            "raw_rows": self.raw_rows,
            "removed": dict(self.removed, note_unparseable_amount=self.note_unparseable_amount),
            "kept_rows": self.kept_rows,
            "kept_sales_rows": self.kept_sales_rows,
            "kept_refund_rows": self.kept_refund_rows,
        }


def open_readonly(path: Path) -> sqlite3.Connection:
    """打开数据库。"""
    conn = sqlite3.connect(path.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def clean_rows(
    rows: Iterable[sqlite3.Row],
    store_ids: Optional[set] = None,
    product_ids: Optional[set] = None,
) -> tuple[list[tuple], CleaningReport]:
    """按 KB-001 §2 规范化、按 §3 的六条规则剔除。"""
    report = CleaningReport()
    kept: list[tuple] = []
    seen: set[tuple] = set()

    for row in rows:
        report.raw_rows += 1

        # §3.1 日期无法解析
        day = normalize_date(row["date"])
        if day is None:
            report.removed["1_unparseable_date"] += 1
            continue

        # §3.2 amount 为空（不回填）
        cents, status = parse_amount(row["amount"])
        if status != "ok":
            report.removed["2_empty_amount"] += 1
            if status == "bad":
                report.note_unparseable_amount += 1
            continue

        # §3.3 qty ≤ 0
        qty = parse_qty(row["qty"])
        if qty is None or qty <= 0:
            report.removed["3_qty_le_zero"] += 1
            continue

        # §2.1 规范化 —— 必须在规则 4、5 之前
        store_id = normalize_id(row["store_id"])
        product_id = normalize_id(row["product_id"])

        # §3.4 / §3.5 规范化后再查维表
        if store_ids is not None and store_id not in store_ids:
            report.removed["4_store_not_in_stores"] += 1
            continue
        if product_ids is not None and product_id not in product_ids:
            report.removed["5_product_not_in_products"] += 1
            continue

        order_id = (row["order_id"] or "").strip()
        payment = (row["payment"] or "").strip()

        # §3.6 七个字段规范化后完全相同才算重复。
        # 只用 order_id 去重会把"一张订单点多个商品"的合法多行明细吃掉（§7.3）。
        key = (order_id, day, store_id, product_id, qty, cents, payment)
        if key in seen:
            report.removed["6_duplicate_row"] += 1
            continue
        seen.add(key)

        kept.append(
            (order_id, day, store_id, product_id, qty, cents, payment, 1 if cents < 0 else 0)
        )

    report.kept_rows = len(kept)
    report.kept_refund_rows = sum(1 for row in kept if row[-1])
    report.kept_sales_rows = report.kept_rows - report.kept_refund_rows
    return kept, report


_SCHEMA = """
CREATE TABLE stores (store_id TEXT PRIMARY KEY, store_name TEXT, category TEXT, district TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT,
                       product_category TEXT, unit_price REAL);
CREATE TABLE sales_clean (
    order_id TEXT, date TEXT, store_id TEXT, product_id TEXT,
    qty INTEGER, amount_cents INTEGER, payment TEXT, is_refund INTEGER
);
CREATE INDEX idx_clean_date ON sales_clean(date);
CREATE INDEX idx_clean_store ON sales_clean(store_id);
CREATE INDEX idx_clean_product ON sales_clean(product_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def build_clean_db(source: Path, target: Path) -> CleaningReport:
    """从只读的源库重建清洗表。返回清洗台账，供 `/api/health` 与数据质量面板使用。"""
    if not source.exists():
        raise FileNotFoundError("找不到源数据库：%s" % source)
    src = open_readonly(source)
    try:
        stores = [tuple(r) for r in src.execute("SELECT store_id, store_name, category, district FROM stores")]
        products = [
            tuple(r)
            for r in src.execute(
                "SELECT product_id, product_name, product_category, unit_price FROM products"
            )
        ]
        rows, report = clean_rows(
            src.execute("SELECT order_id, date, store_id, product_id, qty, amount, payment FROM sales"),
            # §3.4/§3.5 的外键检查要拿维表比，所以先把合法编号读出来。
            store_ids={normalize_id(r[0]) for r in stores},
            product_ids={normalize_id(r[0]) for r in products},
        )
    finally:
        src.close()

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    out = sqlite3.connect(target)
    try:
        out.executescript(_SCHEMA)
        out.executemany("INSERT INTO stores VALUES (?,?,?,?)", stores)
        out.executemany("INSERT INTO products VALUES (?,?,?,?)", products)
        out.executemany("INSERT INTO sales_clean VALUES (?,?,?,?,?,?,?,?)", rows)
        out.execute(
            "INSERT INTO meta VALUES ('cleaning_report', ?)",
            (json.dumps(report.as_dict(), ensure_ascii=False),),
        )
        out.execute("INSERT INTO meta VALUES ('source_db', ?)", (source.name,))
        out.commit()
    finally:
        out.close()
    return report
