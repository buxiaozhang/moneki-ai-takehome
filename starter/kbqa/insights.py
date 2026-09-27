"""看板的统计预警。

纯函数，不碰数据库 —— 输入是 `/api/metrics/daily` 那样的逐日序列，输出是一串
**可解释**的告警。刻意用固定规则而不是让模型判断：

* 规则透明，看到"低于均值 2σ"就能自己核对；
* 误报可预期，不会随模型状态漂移；
* 不会被误读成"模型觉得这里有问题"。

阈值都给成了参数，`/api/ui/dashboard` 可以不传，测试里可以精确构造边界。
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any, Optional

#: 告警级别。`high` 表示"这一天大概率是非正常经营"，`warn` 表示"值得看一眼"。
SEVERITY_HIGH = "high"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"

#: 判定"显著低于均值"的标准差倍数。
DEFAULT_Z = 2.0
#: 环比骤降的幅度阈值（相对前一天）。
DEFAULT_DROP_RATIO = 0.5
#: 连续零营业额达到几天算"疑似停业"。
DEFAULT_CLOSED_RUN = 2
#: 退款金额占净营业额超过多少算偏高。
DEFAULT_REFUND_RATIO = 0.05


def _mean_std(values: list[float]) -> tuple[float, float]:
    """均值和总体标准差。样本不足或全相等时返回 (均值, 0)。"""
    if not values:
        return 0.0, 0.0
    if len(values) < 2:
        return values[0], 0.0
    return statistics.fmean(values), statistics.pstdev(values)


def detect_anomalies(
    days: list[dict],
    *,
    z: float = DEFAULT_Z,
    drop_ratio: float = DEFAULT_DROP_RATIO,
    closed_run: int = DEFAULT_CLOSED_RUN,
) -> list[dict]:
    """从逐日序列里挑出异常日。

    `days` 每项形如 `{"date": "2026-06-08", "net_revenue": 0.0, "orders": 0}`。

    只看有营业额的日期来算均值和标准差 —— 把零营业额的日子也算进去会把均值
    和方差一起拉偏，反而让真正的异常日躲过阈值。这是有意的取舍，写在这里备查。
    """
    if not days:
        return []

    active = [float(day.get("net_revenue") or 0) for day in days if (day.get("net_revenue") or 0) > 0]
    mean, std = _mean_std(active)
    threshold = mean - z * std if std > 0 else None

    # 全是零：这不是"异常"，是"没选到数据"，单独给一条说明。
    if not active:
        return [
            {
                "kind": "empty_range",
                "severity": SEVERITY_INFO,
                "date": days[0].get("date"),
                "end_date": days[-1].get("date"),
                "label": "所选区间没有任何营业额",
                "detail": "%s 至 %s 每一天的净营业额都是 0。" % (days[0].get("date"), days[-1].get("date")),
                "value": 0.0,
            }
        ]

    anomalies: list[dict] = []
    zeros = [index for index, day in enumerate(days) if not (day.get("net_revenue") or 0)]

    # 先把连续的零营业额归成"疑似停业"，这些日期不再逐日重复报零。
    covered: set[int] = set()
    run_start: Optional[int] = None
    for index in range(len(days) + 1):
        is_zero = index < len(days) and index in zeros
        if is_zero and run_start is None:
            run_start = index
        elif not is_zero and run_start is not None:
            length = index - run_start
            if length >= closed_run:
                covered.update(range(run_start, index))
                first, last = days[run_start], days[index - 1]
                anomalies.append(
                    {
                        "kind": "closed_run",
                        "severity": SEVERITY_HIGH,
                        "date": first.get("date"),
                        "end_date": last.get("date"),
                        "days": length,
                        "label": "连续 %d 天零营业额" % length,
                        "detail": "%s 至 %s 共 %d 天没有产生任何营业额，通常意味着停业或未开业。"
                        % (first.get("date"), last.get("date"), length),
                        "value": 0.0,
                    }
                )
            run_start = None

    for index, day in enumerate(days):
        value = float(day.get("net_revenue") or 0)
        date_text = day.get("date")
        if index in covered:
            continue
        if value == 0:
            anomalies.append(
                {
                    "kind": "zero_day",
                    "severity": SEVERITY_HIGH,
                    "date": date_text,
                    "label": "零营业额",
                    "detail": "%s 当天净营业额为 0。" % date_text,
                    "value": 0.0,
                }
            )
            continue
        if threshold is not None and value < threshold:
            anomalies.append(
                {
                    "kind": "low_outlier",
                    "severity": SEVERITY_WARN,
                    "date": date_text,
                    "label": "显著低于均值",
                    "detail": "%s 净营业额 %s 元，低于均值 %s − %s×%s = %s 元。"
                    % (date_text, round(value, 2), round(mean, 2), z, round(std, 2), round(threshold, 2)),
                    "value": round(value, 2),
                    "threshold": round(threshold, 2),
                }
            )
        if index > 0:
            previous = float(days[index - 1].get("net_revenue") or 0)
            if previous > 0 and (previous - value) / previous >= drop_ratio:
                anomalies.append(
                    {
                        "kind": "sharp_drop",
                        "severity": SEVERITY_WARN,
                        "date": date_text,
                        "label": "环比骤降",
                        "detail": "从 %s 的 %s 元降到 %s 元，降幅 %d%%。"
                        % (
                            days[index - 1].get("date"),
                            round(previous, 2),
                            round(value, 2),
                            round((previous - value) / previous * 100),
                        ),
                        "value": round(value, 2),
                    }
                )

    anomalies.sort(key=lambda item: (item.get("date") or "", item.get("kind") or ""))
    return anomalies


def period_warnings(
    summary: dict, *, refund_ratio: float = DEFAULT_REFUND_RATIO, aov_gap: float = 0.2
) -> list[dict]:
    """区间级别的提示：退款占比、客单价与销量的背离。"""
    warnings: list[dict] = []
    net = float(summary.get("net_revenue") or 0)
    refund = float(summary.get("refund_amount") or 0)
    if net > 0 and refund / net >= refund_ratio:
        warnings.append(
            {
                "kind": "refund_high",
                "severity": SEVERITY_WARN,
                "label": "退款占比偏高",
                "detail": "退款 %s 元，占净营业额 %s 元的 %.1f%%。"
                % (round(refund, 2), round(net, 2), refund / net * 100),
            }
        )
    if summary.get("orders") == 0 and net == 0:
        warnings.append(
            {
                "kind": "no_business",
                "severity": SEVERITY_INFO,
                "label": "该区间没有营业",
                "detail": "订单数与净营业额都是 0，注意区分「真的没生意」和「筛选条件选错了」。",
            }
        )
    return warnings


def summarize(anomalies: list[dict]) -> dict[str, int]:
    """按级别计数，给看板的角标用。"""
    counts: dict[str, int] = {SEVERITY_HIGH: 0, SEVERITY_WARN: 0, SEVERITY_INFO: 0}
    for item in anomalies:
        level = item.get("severity") or SEVERITY_INFO
        counts[level] = counts.get(level, 0) + 1
    return counts


def annotate(days: list[dict], anomalies: list[dict]) -> list[dict]:
    """把告警挂回逐日序列，前端画标记点时不用再自己配对。

    跨天的告警（`closed_run`）要**铺满**它覆盖的每一天。只挂在起始日上，
    趋势图里后面几天就是干干净净的空白，看的人会以为那几天正常。
    """
    by_date: dict[str, list[dict]] = {}
    for item in anomalies:
        start = item.get("date")
        if not start:
            continue
        end = item.get("end_date") or start
        for day in _date_span(start, end):
            by_date.setdefault(day, []).append(item)
    out = []
    for day in days:
        merged = dict(day)
        found = by_date.get(day.get("date"), [])
        merged["anomalies"] = found
        merged["severity"] = (
            SEVERITY_HIGH
            if any(item.get("severity") == SEVERITY_HIGH for item in found)
            else SEVERITY_WARN
            if found
            else None
        )
        out.append(merged)
    return out


def _date_span(start: str, end: str) -> list[str]:
    """`start` 到 `end` 的每一天（含两端）；解析不了就只回起点。"""
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end)
    except (TypeError, ValueError):
        return [start]
    if last < first:
        return [start]
    days = []
    cursor = first
    while cursor <= last:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def as_payload(
    days: list[dict],
    summary: Optional[dict] = None,
    *,
    z: float = DEFAULT_Z,
    drop_ratio: float = DEFAULT_DROP_RATIO,
) -> dict[str, Any]:
    """一次算完，给接口直接返回。"""
    anomalies = detect_anomalies(days, z=z, drop_ratio=drop_ratio)
    warnings = period_warnings(summary or {})
    return {
        "anomalies": anomalies,
        "period_warnings": warnings,
        "counts": summarize(anomalies),
        "days": annotate(days, anomalies),
        "params": {"z": z, "drop_ratio": drop_ratio},
    }
