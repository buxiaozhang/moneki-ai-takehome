"""看板接口与前端静态资源的回归测试。

前端没法在这个环境里跑浏览器，所以这里守的是**能自动检查的部分**：
* 接口的字段结构（前端按这些字段名取值，改名会静默把界面画空）；
* 静态文件确实被挂上、且引用的脚本都存在（404 会让整页白屏）；
* 统计规则本身（`insights`）的边界行为。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kbqa import insights


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from kbqa.server import app

    return TestClient(app)


# --- 统计规则 ------------------------------------------------------------------


def _days(values, start_day=1):
    return [
        {"date": "2026-06-%02d" % (start_day + index), "net_revenue": value, "orders": 1 if value else 0}
        for index, value in enumerate(values)
    ]


def test_closed_run_reported_once():
    """连续 4 天零营业额只报一条"疑似停业"，不要逐日重复报零。"""
    days = _days([500, 0, 0, 0, 0, 400])
    found = insights.detect_anomalies(days)
    kinds = [item["kind"] for item in found]
    assert kinds.count("closed_run") == 1, kinds
    assert "zero_day" not in kinds, "连续零营业额已被归组，不该再逐日报：%s" % kinds
    run = next(item for item in found if item["kind"] == "closed_run")
    assert run["days"] == 4
    assert run["date"] == "2026-06-02" and run["end_date"] == "2026-06-05"


def test_single_zero_day_is_its_own_alert():
    """只有一天零营业额时不构成"停业"，但仍然是高优先级异常。"""
    found = insights.detect_anomalies(_days([500, 0, 480, 520]))
    zero = [item for item in found if item["kind"] == "zero_day"]
    assert len(zero) == 1
    assert zero[0]["severity"] == insights.SEVERITY_HIGH


def test_low_outlier_uses_active_days_only():
    """均值和标准差只看有营业额的日子。

    把零营业额也计入会把均值拉低、方差拉大，真正的异常日反而躲过阈值。
    """
    days = _days([1000, 1000, 1000, 1000, 100, 1000])
    found = insights.detect_anomalies(days)
    low = [item for item in found if item["kind"] == "low_outlier"]
    assert low, "100 明显低于均值，应被标出：%s" % [item["kind"] for item in found]
    assert low[0]["date"] == "2026-06-05"


def test_flat_series_has_no_outlier():
    """全都一样时标准差是 0，不该因为"低于均值 − 0σ"而产生误报。"""
    found = insights.detect_anomalies(_days([500, 500, 500, 500]))
    assert [item for item in found if item["kind"] == "low_outlier"] == []


def test_sharp_drop_detected():
    found = insights.detect_anomalies(_days([1000, 200, 900]))
    drops = [item for item in found if item["kind"] == "sharp_drop"]
    assert drops and drops[0]["date"] == "2026-06-02"


def test_empty_range_explained_not_flagged_as_anomaly():
    """全零不是"异常"，是"没选到数据" —— 给一条说明，不要报一堆零营业额。"""
    found = insights.detect_anomalies(_days([0, 0, 0]))
    assert len(found) == 1
    assert found[0]["kind"] == "empty_range"
    assert found[0]["severity"] == insights.SEVERITY_INFO


def test_period_warnings_refund_ratio():
    warnings = insights.period_warnings({"net_revenue": 1000, "refund_amount": 100, "orders": 10})
    assert [w["kind"] for w in warnings] == ["refund_high"]
    assert insights.period_warnings({"net_revenue": 1000, "refund_amount": 10, "orders": 10}) == []


def test_annotate_attaches_marks_to_days():
    days = _days([500, 0, 0, 500])
    payload = insights.as_payload(days, {"net_revenue": 1000, "orders": 4})
    marked = [day for day in payload["days"] if day["severity"]]
    assert len(marked) == 2, "两天零营业额都应被标出"
    assert all(day["anomalies"] for day in marked)
    assert payload["counts"]["high"] == 1


# --- 看板接口 ------------------------------------------------------------------


def test_dashboard_returns_every_field_the_frontend_reads(client):
    """字段名是前端取值用的，改名会把界面画空而且不报错 —— 这里钉住。"""
    response = client.get("/api/ui/dashboard", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert response.status_code == 200
    data = response.json()
    for field in (
        "summary", "days", "anomalies", "anomaly_counts", "period_warnings",
        "top_products", "by_store", "payments", "data_quality", "data_period",
    ):
        assert field in data, "缺少字段 %s" % field

    assert set(["net_revenue", "refund_amount", "orders", "aov", "qty"]).issubset(data["summary"])
    # 逐日条目要带异常标记，否则前端画不出红点。
    assert data["days"] and {"date", "net_revenue", "orders", "anomalies"} <= set(data["days"][0])
    assert data["top_products"], "Top 商品不该为空"
    assert {"product_id", "product_name", "net_revenue", "qty"} <= set(data["top_products"][0])


def test_dashboard_store_filter_narrows_result(client):
    all_stores = client.get(
        "/api/ui/dashboard", params={"start": "2026-06-01", "end": "2026-06-30"}
    ).json()
    one_store = client.get(
        "/api/ui/dashboard",
        params={"start": "2026-06-01", "end": "2026-06-30", "store_id": "S03"},
    ).json()
    assert one_store["summary"]["net_revenue"] < all_stores["summary"]["net_revenue"]
    # 选了单店就不再给门店对比（前端改用支付构成画那张图）。
    assert one_store["by_store"] == []
    assert all_stores["by_store"], "全门店时应给出门店对比"


def test_dashboard_rejects_bad_date(client):
    response = client.get("/api/ui/dashboard", params={"start": "2026/06/01", "end": "2026-06-30"})
    assert response.status_code == 400
    assert "YYYY-MM-DD" in response.json()["error"]


def test_dashboard_top_limit_respected(client):
    data = client.get(
        "/api/ui/dashboard",
        params={"start": "2026-05-01", "end": "2026-08-31", "top_limit": 3},
    ).json()
    assert len(data["top_products"]) == 3


def test_dashboard_top_products_sorted_desc(client):
    data = client.get(
        "/api/ui/dashboard", params={"start": "2026-05-01", "end": "2026-08-31"}
    ).json()
    values = [item["net_revenue"] for item in data["top_products"]]
    assert values == sorted(values, reverse=True)


# --- 静态资源 ------------------------------------------------------------------


def test_page_and_assets_are_served(client):
    """`/` 与它引用的三个资源都要能取到；少一个就是白屏。"""
    index = client.get("/")
    assert index.status_code == 200
    html = index.text
    assert "app.js" in html and "charts.js" in html and "styles.css" in html

    for asset in ("/static/app.js", "/static/charts.js", "/static/styles.css"):
        assert client.get(asset).status_code == 200, "%s 取不到" % asset


def test_every_getelementbyid_target_exists_in_html(client):
    """`$('x')` 取不到就是 null，接着 `.value` 会抛错并让整个初始化中断。

    这类错在浏览器里才看得见，所以在测试里把两边的名字对一遍。
    """
    html = client.get("/").text
    ids = set(re.findall(r'id="([^"]+)"', html))

    js = client.get("/static/app.js").text
    # 先去掉注释再扫：注释里为了举例写出的取法不是真的引用，
    # 之前就因为注释里写了一个例子把这条测试弄红过。
    # （app.js 里没有把 // 写进字符串的地方，所以整行截断是安全的。）
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    js = re.sub(r"(?m)//[^\n]*", "", js)

    referenced = set(re.findall(r"\$\('([^']+)'\)", js))
    missing = sorted(referenced - ids)
    assert not missing, "app.js 引用了 HTML 里不存在的 id：%s" % missing


# --- 前端布局不变量 -------------------------------------------------------------
# jsdom 不做布局，算不出"两个盒子叠在一起"，所以这类重叠只能靠静态断言守。


def _css_block(css: str, selector: str) -> str:
    """取某个选择器的声明块。

    只认"行首选择器 + { ... }"这种平铺写法（styles.css 就是这么写的）。
    取不到直接失败 —— 选择器被改名了也该让测试红，而不是静默放过。
    """
    match = re.search(r"(?m)^\s*%s\s*\{([^}]*)\}" % re.escape(selector), css)
    assert match, "styles.css 里找不到规则：%s" % selector
    return match.group(1)


def _has(block: str, prop: str, value: str) -> bool:
    pattern = r"(?m)(?:^|;)\s*%s\s*:\s*%s\s*(?:;|$)" % (
        re.escape(prop), re.escape(value),
    )
    return re.search(pattern, block) is not None


def test_trace_summary_is_collapsible_and_cannot_overlap(client):
    """回归：模型调用失败后，「耗时构成」会压到「规划」那块步骤上。

    根因：「实时追踪」面板是纵向 flex 容器，`.trace-summary` 是它的子项，
    默认 `flex-shrink: 1`。模型失败会多出错误与重试步骤，面板被挤，
    这块就被压到比内容还矮；行高固定的 `.gantt-row` 溢出到下面没有背景色的
    `.trace` 上，看着就是两段文字叠在一起。

    两条一起守：能折叠（用户主动腾地方，折起来就不可能重叠），
    以及展开时也不许被压缩（否则照样溢出）。
    """
    css = client.get("/static/styles.css").text
    js = client.get("/static/app.js").text

    # 1. 可折叠：状态存在、靠 collapsed 类控制、收起时行不显示。
    assert "summaryCollapsed" in js, "app.js 里应有折叠状态"
    assert "classList.toggle('collapsed'" in js, "应通过 collapsed 类控制折叠"
    assert _has(_css_block(css, ".trace-summary.collapsed .gantt-body"), "display", "none")
    # 折叠头得是真 button，键盘与读屏器才用得了。
    assert re.search(r'<button type="button" class="gantt-head"', js), (
        "耗时构成的头应渲染成 button"
    )
    assert "aria-expanded" in js, "折叠控件要带 aria-expanded"

    # 2. 展开时不许被压缩，而且要有上限、自己滚动。
    summary = _css_block(css, ".trace-summary")
    assert _has(summary, "flex", "0 0 auto") or _has(summary, "flex-shrink", "0"), (
        ".trace-summary 必须 flex-shrink:0，否则被压扁后内容会溢出到步骤列表上"
    )
    assert "max-height" in summary, ".trace-summary 需要 max-height 上限"
    assert _has(summary, "overflow-y", "auto"), ".trace-summary 超上限时要自己滚动"

    # 3. 面板表头也是 flex 子项，被压扁同样会溢到下面的块上。
    head = _css_block(css, ".trace-col .panel:first-child > .panel-head")
    assert _has(head, "flex", "0 0 auto") or _has(head, "flex-shrink", "0"), (
        "面板表头也要固定住，不然它自己就会叠到下面"
    )

    # 4. 唯一允许伸缩、负责吸收高度的是 .trace，它必须能滚。
    assert _has(_css_block(css, ".trace"), "overflow-y", "auto")


def test_charts_module_exposes_the_three_renderers(client):
    js = client.get("/static/charts.js").text
    for name in ("renderTrendChart", "renderBarChart", "renderDonutChart"):
        assert name in js, "charts.js 没有 %s" % name
    assert "window.Charts" in js


def test_trace_fixture_matches_current_shape(client):
    """`tests/fixtures/trace_sample.json` 是前端冒烟测试的输入。

    它是抓下来的一份真实响应，接口以后若改了字段，夹具不会自己跟着变 ——
    那会让前端测试测的是旧形状。这里拿它与**当前**的 trace 对一遍。
    """
    fixture_path = Path(__file__).parent / "fixtures" / "trace_sample.json"
    assert fixture_path.exists(), "缺夹具：%s" % fixture_path
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    # 当前实现真的产出这些字段吗？
    live = client.post(
        "/api/chat", json={"question": fixture["trace"]["question"], "session_id": "fixture-check"}
    ).json()
    trace = client.get("/api/trace/" + live["trace_id"]).json()

    fixture_steps = {step["step"] for step in fixture["trace"]["steps"]}
    live_steps = {step["step"] for step in trace["steps"]}
    assert fixture_steps <= live_steps, (
        "夹具里的步骤 %s 在当前实现里已经没有了" % (fixture_steps - live_steps)
    )
    assert set(fixture["trace"]) <= set(trace), "trace 顶层字段变了"
    assert set(fixture["chat"]) <= set(live), "chat 返回字段变了"

    search = next(step for step in trace["steps"] if step["step"] == "search")
    for field in ("hits", "filtered", "coverage", "query"):
        assert field in search["detail"], "search 步骤缺字段 %s" % field
    assert search["detail"]["hits"], "夹具问题应当检索到东西"


def test_web_smoke_runs_or_skips_cleanly():
    """前端冒烟脚本必须**要么通过、要么明确跳过**，不能自己报错。

    没装 jsdom（或没装 node）时它应打印跳过信息并返回 0 —— 环境缺依赖不该
    变成红灯，否则这个检查迟早被人从流水线里删掉。
    """
    if shutil.which("node") is None:
        pytest.skip("本机没有 node")

    result = subprocess.run(
        ["node", str(Path(__file__).parent / "web_smoke.js")],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, "前端冒烟失败：\n%s\n%s" % (result.stdout, result.stderr)
    assert "全部通过" in result.stdout or "跳过" in result.stdout, result.stdout

