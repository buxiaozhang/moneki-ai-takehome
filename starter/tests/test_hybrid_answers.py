"""数据 + 文档（hybrid）类问答的回归测试。

覆盖 `DEBUG_LOG.md` 的 D-025～D-027。这三条都是**规划器把已经判好的
hybrid 身份又推翻**造成的：问句里带的“多少/几”或“为什么”把
`target`/`price`/`anomaly` 改写成纯取数或纯文档，于是知识库那一半证据被丢掉。
"""

from __future__ import annotations

import re

import pytest

from kbqa.retriever import Retriever

#: 模块导入时抓住真实的 `Retriever.search`（理由见 test_doc_answers.py）。
_ORIGINAL_SEARCH = Retriever.search


@pytest.fixture
def hy_client():
    """不经过 `tests/conftest.py` 那层 `Retriever.search` 替换的 TestClient。"""
    patched = Retriever.search
    if patched is not _ORIGINAL_SEARCH:
        Retriever.search = _ORIGINAL_SEARCH
    try:
        from fastapi.testclient import TestClient

        from kbqa import server

        yield TestClient(server.app)
    finally:
        Retriever.search = patched


def _has_number(text: str, value: float, tol: float = 0.01) -> bool:
    """回答里是否出现了某个数值（容忍千分位逗号）。"""
    for match in re.finditer(r"-?\d+(?:\.\d+)?", text.replace(",", "")):
        try:
            if abs(float(match.group()) - value) <= tol:
                return True
        except ValueError:  # pragma: no cover
            continue
    return False


# --- D-025：target 被“多少”改写成纯取数 -----------------------------------------


def test_target_question_stays_hybrid(hy_client):
    """「618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？」

    这是一个两段式问题：前半段要数据库里的销量，后半段要活动方案里的目标值。
    规划器第 217-218 行已经判成 `target`/`hybrid`，但紧接着第 259 行的
    “句子里有『多少』就要数字”把它改写成 `summary`/`data` —— 目标值只能来自
    知识库，改写成纯取数之后就再也拿不到了。

    修复后必须保持 `hybrid`，且同时给出实际销量、目标值、以及达标结论。
    """
    body = hy_client.post(
        "/api/chat",
        json={"question": "618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？", "session_id": "hy-h02"},
    ).json()
    answer = body.get("answer") or ""
    cited = [c.get("doc_id") for c in (body.get("citations") or [])]

    assert body.get("answer_type") == "hybrid", "answer_type=%s，应为 hybrid" % body.get("answer_type")
    assert "KB-023" in cited, "应引用活动方案 KB-023，实际 %s" % cited
    assert _has_number(answer, 125), "回答里没有实际销量 125"
    assert _has_number(answer, 120), "回答里没有目标值 120"
    assert ("达标" in answer) or ("达成" in answer), "回答里没有给出达标结论"
    # 150 是干扰项（另一个商品的数字），出现即算错。
    assert not _has_number(answer, 150), "回答里出现了干扰数字 150"


def test_target_question_plan_is_hybrid():
    """不经过 HTTP，直接看规划结果：target 问句必须是 hybrid。"""
    from kbqa.config import load_settings
    from kbqa.service import Service

    service = Service(load_settings())
    plan = service.planner.plan("618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？")
    assert plan.intent == "hybrid", "intent=%s" % plan.intent
    assert plan.kind == "target", "kind=%s" % plan.kind
    assert plan.needs_data and plan.needs_docs, "两段式问题应同时需要数据和文档"


# --- D-026：price 被“多少”改写成 summary，再被区间校验拦成拒答 ------------------


def test_price_question_is_not_refused(hy_client):
    """「牛肉poke 现在卖多少钱一份？商品表里那个价能直接拿来用吗？」

    “多少钱”里的“多少”触发了同一个改写：第 219-220 行判好的 `price`/`hybrid`
    被改成 `summary`/`data`。而“现在”会被解析成 2026-09-01（系统当天），
    落在数据区间 2026-05-01～2026-08-31 之外，于是 `_check_period` 把它拦成
    `out_of_period` 拒答 —— 问价格却回答“这段时间没有销售数据”。

    修复后应是 `hybrid`/`doc`，引用调价通知 KB-025，并说明维表建档价不能直接用。
    """
    body = hy_client.post(
        "/api/chat",
        json={"question": "牛肉poke 现在卖多少钱一份？商品表里那个价能直接拿来用吗？", "session_id": "hy-h04"},
    ).json()
    answer = body.get("answer") or ""
    cited = [c.get("doc_id") for c in (body.get("citations") or [])]

    assert body.get("answer_type") in ("hybrid", "doc"), "answer_type=%s" % body.get("answer_type")
    assert "KB-025" in cited, "应引用调价通知 KB-025，实际 %s" % cited
    assert _has_number(answer, 45), "回答里没有现行售价 45"
    assert any(word in answer for word in ("建档价", "维表", "滞后")), "没有说明维表价为什么不能直接用"


def test_price_question_plan_is_hybrid():
    from kbqa.config import load_settings
    from kbqa.service import Service

    service = Service(load_settings())
    plan = service.planner.plan("牛肉poke 现在卖多少钱一份？商品表里那个价能直接拿来用吗？")
    assert plan.intent in ("hybrid", "doc"), "intent=%s" % plan.intent
    assert plan.kind == "price", "kind=%s" % plan.kind


# --- D-027：anomaly 被“为什么”改写成纯文档 --------------------------------------


@pytest.mark.parametrize(
    "case_id,question,cite,numbers",
    [
        (
            "H01",
            "S03 六月第二周（6 月 8 日到 6 月 14 日）的营业额为什么比别的周低这么多？",
            "KB-020",
            [3630.0, 0.0],
        ),
        (
            "H06",
            "S02 在 8 月 17 日到 19 日为什么一分钱营业额都没有？",
            None,
            [0.0],
        ),
    ],
    ids=["H01", "H06"],
)
def test_anomaly_question_keeps_data_side(hy_client, case_id, question, cite, numbers):
    """问“为什么”的异常问题，不能丢掉数据库那一半。

    H01：`anomaly`/`hybrid` 已由第 221-223 行判好，但第 264 行的“为什么就找文档”
    把它覆盖成 `doc`/`doc` —— 于是回答里只有停业通知，**没有复现那两个数字**
    （区间净营业额 3630 与“4 天零营业额”），而 `evidence_required`/`numbers_any`
    恰恰要求数字来自数据库查询。

    H06：这个区间的营业额是 0，知识库里**没有**对应的通知。
    正确行为是给数字 + 如实说“没找到原因”，而不是拿门店档案之类的文档硬凑
    （评测 `cite_max: 0` 就是专门拦这个的）。
    """
    body = hy_client.post("/api/chat", json={"question": question, "session_id": "hy-" + case_id}).json()
    answer = body.get("answer") or ""
    cited = [c.get("doc_id") for c in (body.get("citations") or [])]

    # H01 有对应通知，应为 hybrid 并引用；H06 没有通知，可以是 data/hybrid/refusal。
    if cite is None:
        assert body.get("answer_type") in ("data", "hybrid", "refusal"), "answer_type=%s" % body.get("answer_type")
        assert len(cited) == 0, "知识库里没有解释，不该引用文档：%s" % cited
        assert any(word in answer for word in ("没有找到", "未找到", "没有查到", "找不到", "没有记录")), (
            "没有如实说明找不到原因"
        )
    else:
        assert body.get("answer_type") == "hybrid", "answer_type=%s" % body.get("answer_type")
        assert cite in cited, "应引用 %s，实际 %s" % (cite, cited)

    for value in numbers:
        assert _has_number(answer, value), "回答里没有期望数字 %s" % value


def test_anomaly_plan_keeps_hybrid_intent():
    """两个异常问句在规划阶段就该是 anomaly/hybrid。"""
    from kbqa.config import load_settings
    from kbqa.service import Service

    service = Service(load_settings())
    for question in (
        "S03 六月第二周（6 月 8 日到 6 月 14 日）的营业额为什么比别的周低这么多？",
        "S02 在 8 月 17 日到 19 日为什么一分钱营业额都没有？",
    ):
        plan = service.planner.plan(question)
        assert plan.kind == "anomaly", "%s -> kind=%s" % (question[:16], plan.kind)
        assert plan.intent == "hybrid", "%s -> intent=%s" % (question[:16], plan.intent)


# -- 模型把工具调用语法当正文吐出来 -------------------------------------------------


@pytest.mark.parametrize(
    "leaked",
    [
        # 实测抓到的原文（H06 那次，整段回答就是这个）
        '<｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="search_kb"> '
        '<｜｜DSML｜｜ parameter name="query">退款',
        '||DSML|| invoke name="query_metrics"',
        '<tool_calls><invoke name="daily_metrics">',
    ],
)
def test_tool_call_markup_is_detected(leaked):
    """模型有时会把"要调用工具"的标记当成正文返回。

    这种东西既不是答案、也绝不能给运营看到。`_finalise` 里靠这个正则识别出来，
    然后改用按工具结果渲染的模板回答顶上。
    """
    from kbqa.live import _TOOL_MARKUP

    assert _TOOL_MARKUP.search(leaked), "没识别出来：%r" % leaked[:60]


def test_normal_answer_is_not_flagged():
    """正常的回答不能被误伤。"""
    from kbqa.live import _TOOL_MARKUP

    for good in (
        "2026-06-18 牛肉poke 销量 125 件，净营业额 3625.00 元。",
        "依据 2026 年 618 活动方案 [KB-023]，当天目标 120 份。",
        "SQL 语句里查了 sales_clean 表。",
        "会员储值、微信、支付宝、现金、银行卡。",
    ):
        assert not _TOOL_MARKUP.search(good), "误伤了正常文本：%r" % good


# -- data_evidence 不能"穷举数字" -------------------------------------------------


def test_evidence_trims_long_daily_series():
    """整月逐日序列要裁掉，否则触发"穷举数字不是证据"。"""
    from kbqa.live import _count_numbers, _trim_evidence

    days = [
        {"date": "2026-07-%02d" % d, "net_revenue": 1000 + d, "orders": 30 + d,
         "aov": 33.3, "refund_amount": 0, "qty": 90 + d}
        for d in range(1, 31)
    ]
    big = {"start": "2026-07-01", "end": "2026-07-31", "days": days}
    assert _count_numbers(big) > 60, "构造的样本本身就该超限"

    out = _trim_evidence(big)
    assert _count_numbers(out) <= 60, "裁完还要超限就没意义了"
    assert len(out["days"]) <= 6
    assert out.get("_trimmed"), "要写清楚裁了什么，别让人以为数据本来就这么点"
    # 汇总字段不能动
    assert out["start"] == "2026-07-01" and out["end"] == "2026-07-31"


def test_evidence_keeps_small_result_intact():
    """小结果原样保留 —— 正常的证据不该被改。"""
    from kbqa.live import _trim_evidence

    small = {"net_revenue": 3625.0, "refund_amount": 0.0, "orders": 53, "aov": 68.4, "qty": 125}
    assert _trim_evidence(small) == small
