"""多轮追问（`multi_turn`）的回归测试。

覆盖 `DEBUG_LOG.md` 的 D-029。缺陷只有一行：`service._answer()` 从会话里
取出了 `history`，却**没有传给** `planner.plan()` —— 规划器永远以为这是第一轮，
于是「那 7 月呢？」被判成"没有上文的追问"，直接反问，多轮上下文整个失效。
"""

from __future__ import annotations

import re

import pytest

from kbqa.retriever import Retriever

#: 模块导入时抓住真实的 `Retriever.search`（理由见 test_doc_answers.py）。
_ORIGINAL_SEARCH = Retriever.search


@pytest.fixture
def mt_client():
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


def _numbers(text: str) -> list[float]:
    return [float(m.group()) for m in re.finditer(r"-?\d+(?:\.\d+)?", text.replace(",", ""))]


def _has_number(text: str, value: float, tol: float = 0.01) -> bool:
    return any(abs(n - value) <= tol for n in _numbers(text))


def _ask(client, session_id: str, questions: list[str]) -> list[dict]:
    return [
        client.post("/api/chat", json={"question": q, "session_id": session_id}).json()
        for q in questions
    ]


@pytest.fixture(scope="module")
def service_planner():
    """直接拿规划器，不经过 HTTP —— 只关心还原出来的区间。"""
    from kbqa.config import load_settings
    from kbqa.service import Service

    return Service(load_settings()).planner


def _cited(body: dict) -> list[str]:
    return [c.get("doc_id") for c in (body.get("citations") or [])]


# --- D-029：history 没有传进 planner --------------------------------------------


def test_follow_up_with_date_uses_previous_turn(mt_client):
    """T01：第一轮问 6 月，第二轮「那 7 月呢？」必须接着上文的**主题**换成 7 月。

    修复前第二轮返回 `clarify`：
    `这句像是追问，但这个会话里没有上文。请把问题补完整，例如"7 月的净营业额是多少"。`
    —— 明明同一个 session 刚问过营业额，却说自己没有上文。
    """
    first, second = _ask(mt_client, "mt-t01", ["6 月的净营业额是多少？", "那 7 月呢？"])

    assert first.get("answer_type") in ("data", "hybrid")
    assert _has_number(first.get("answer") or "", 156757.0), "第一轮没给出 6 月净营业额"

    assert second.get("answer_type") in ("data", "hybrid"), (
        "第二轮被反问成 %s —— 多轮上下文没生效" % second.get("answer_type")
    )
    assert _has_number(second.get("answer") or "", 162414.0), "第二轮没给出 7 月净营业额"


def test_follow_up_about_two_periods_keeps_both(mt_client):
    """T01 第三轮「这两个月的客单价差了多少？」要同时记住前两轮的区间并做差。"""
    turns = _ask(
        mt_client,
        "mt-t01b",
        ["6 月的净营业额是多少？", "那 7 月呢？", "这两个月的客单价差了多少？"],
    )
    answer = turns[2].get("answer") or ""
    assert turns[2].get("answer_type") in ("data", "hybrid"), "第三轮 answer_type=%s" % turns[2].get("answer_type")
    assert _has_number(answer, 36.36), "没给出 6 月客单价 36.36"
    assert _has_number(answer, 36.53), "没给出 7 月客单价 36.53"
    assert _has_number(answer, 0.17), "没给出差额 0.17"


def test_follow_up_switches_document_topic(mt_client):
    """T02：「那停售期间让顾客换成什么？」要接着上一轮的停售话题，仍是 KB-021。"""
    first, second, third = _ask(
        mt_client,
        "mt-t02",
        ["三文鱼poke 七月初为什么停售了？", "那停售期间让顾客换成什么？", "供应商后来赔了多少？"],
    )
    assert set(_cited(first)) & {"KB-021", "KB-022"}, "第一轮引用 %s" % _cited(first)
    assert "KB-021" in _cited(second), "第二轮引用 %s，应含 KB-021" % _cited(second)
    assert ("鸡肉poke" in (second.get("answer") or "")) or ("Chicken Poke" in (second.get("answer") or "")), (
        "第二轮没给出替代品鸡肉poke"
    )
    # 第三轮问赔偿，答案在英文邮件 KB-022 里（8600）。
    assert "KB-022" in _cited(third), "第三轮引用 %s，应含 KB-022" % _cited(third)
    assert _has_number(third.get("answer") or "", 8600, tol=0), "第三轮没给出赔偿金额 8600"


def test_follow_up_with_explicit_date(mt_client):
    """T03：「那 6 月 18 号那天呢？」带上文的商品，换成 618 当天的活动价 29。"""
    first, second = _ask(mt_client, "mt-t03", ["牛肉poke 现在多少钱一份？", "那 6 月 18 号那天呢？"])
    assert "KB-025" in _cited(first), "第一轮引用 %s，应含 KB-025" % _cited(first)
    assert _has_number(first.get("answer") or "", 45, tol=0), "第一轮没给出 45"
    assert "KB-023" in _cited(second), "第二轮引用 %s，应含 KB-023" % _cited(second)
    assert _has_number(second.get("answer") or "", 29, tol=0), "第二轮没给出活动价 29"


def test_history_reaches_the_planner():
    """不经过 HTTP：`plan()` 收到 history 时必须能还原追问。"""
    from kbqa.config import load_settings
    from kbqa.service import Service

    service = Service(load_settings())
    history = [
        {
            "question": "6 月的净营业额是多少？",
            "standalone": "6 月的净营业额是多少？",
            "slots": {"recent_windows": [["2026-06-01", "2026-06-30"]]},
        }
    ]
    plan = service.planner.plan("那 7 月呢？", history)
    assert plan.intent != "clarify", "带 history 时不该反问"
    assert plan.window and plan.window[0].startswith("2026-07"), "window=%s" % (plan.window,)


def test_service_passes_history_to_planner():
    """守住那一行：`_answer()` 必须把会话历史交给 `plan()`。

    这条是"防止改回去"的哨兵 —— 修复前 `history` 取出来了却没传参，
    任何基于会话的多轮能力都会静默失效，而单轮测试全绿。
    """
    import inspect

    from kbqa.service import Service

    source = inspect.getsource(Service._answer)
    assert "self.planner.plan(question, history)" in source, (
        "service._answer() 没有把 history 传给 planner.plan()，多轮追问会失效"
    )


def test_no_history_still_asks_for_context(mt_client):
    """反过来也要成立：**真的**没有上文的追问，仍然要反问，不能瞎猜。

    注意这个断言只有在会话互相隔离时才成立 —— `SessionStore` 原本忽略了
    `session_id`，新会话会读到别人的历史，于是这里会随机变成非 `clarify`。
    """
    body = mt_client.post("/api/chat", json={"question": "那 7 月呢？", "session_id": "mt-fresh"}).json()
    assert body.get("answer_type") == "clarify", "无上文时应反问，实际 %s" % body.get("answer_type")


# --- D-030：会话历史没有按 session_id 隔离 --------------------------------------


def test_sessions_do_not_share_history():
    """`SessionStore` 必须按 `session_id` 分开存。

    修复前它只有一个全局 `_turns`，`history()`/`append()` 把 `session_id`
    整个忽略掉：alice 能看到 bob 的对话，随便传一个（或不传）id 都能读到全部。
    """
    from kbqa.sessions import SessionStore

    store = SessionStore()
    store.append("alice", {"question": "alice 的问题"})
    store.append("bob", {"question": "bob 的问题"})

    assert [t["question"] for t in store.history("alice")] == ["alice 的问题"]
    assert [t["question"] for t in store.history("bob")] == ["bob 的问题"]
    assert store.history("nobody") == [], "陌生 session 不该读到别人的对话"


def test_session_turn_limit_is_per_session():
    """轮数上限按会话各自计算，不能用一个会话把别的挤掉。"""
    from kbqa.sessions import SessionStore

    store = SessionStore(max_turns=2)
    for index in range(5):
        store.append("x", {"question": "x%d" % index})
    store.append("y", {"question": "y0"})

    assert [t["question"] for t in store.history("x")] == ["x3", "x4"]
    assert [t["question"] for t in store.history("y")] == ["y0"]


def test_session_count_limit_evicts_oldest():
    """会话数超限时淘汰最早的，不是把最近的丢掉。"""
    from kbqa.sessions import SessionStore

    store = SessionStore(max_sessions=2)
    for index in range(4):
        store.append("s%d" % index, {"question": "q%d" % index})

    assert store.history("s0") == [], "最早的会话应被淘汰"
    assert [t["question"] for t in store.history("s3")] == ["q3"], "最新的会话必须留着"


def test_two_sessions_do_not_leak_into_each_other(mt_client):
    """端到端：两个 session 各问各的，第二轮不能串到对方的话题上。"""
    mt_client.post("/api/chat", json={"question": "6 月的净营业额是多少？", "session_id": "leak-a"})
    # b 会话第一轮问的是完全不同的主题。
    mt_client.post("/api/chat", json={"question": "外卖订单多久内可以申请退款？", "session_id": "leak-b"})

    body = mt_client.post("/api/chat", json={"question": "那 7 月呢？", "session_id": "leak-a"}).json()
    answer = body.get("answer") or ""
    assert _has_number(answer, 162414.0), (
        "a 会话的追问没有接上自己的上文（拿到了 %s）" % body.get("answer_type")
    )


# --- D-031：上一轮的时间标签写成了"规范化"形式，追问时摘不掉 ---------------------


def test_labels_keep_the_original_wording():
    """时间标签必须是**原文**，不能用 `%d月第%d周` 拼出来。

    「六月第二周」被拼成「6月第2周」后，追问还原拿它去 `str.replace` 就命中不了，
    上一轮的时间留在句子里，`_choose_kind` 取 `windows[0]` 拿到的还是旧区间。
    """
    from kbqa.config import load_settings
    from kbqa.timeparse import parse_time

    today = load_settings().today
    spec = parse_time("S03 六月第二周营业额为什么这么低", today)
    assert spec.windows == [("2026-06-08", "2026-06-14")]
    assert "六月第二周" in spec.labels, "labels=%s，应保留原文写法" % spec.labels

    # 阿拉伯数字写法同样保留原文。
    assert "6月第2周" in parse_time("6月第2周", today).labels
    assert "六月" in parse_time("六月", today).labels


def test_follow_up_overrides_an_anomaly_window(mt_client):
    """用户报的场景：问完「S03 六月第二周为什么低」，追问「那七月呢？」必须换到 7 月。

    修复前第二轮仍然回答 6 月 8-14 日（净营业额 3630.00），因为「六月第二周」
    没被摘掉，它排在 `windows[0]`。
    """
    session = "d031-anomaly"
    first = mt_client.post(
        "/api/chat", json={"question": "S03 六月第二周营业额为什么这么低", "session_id": session}
    ).json()
    assert _has_number(first.get("answer") or "", 3630.0), "第一轮没给出 6 月第二周的 3630.00"

    second = mt_client.post(
        "/api/chat", json={"question": "那七月呢？", "session_id": session}
    ).json()
    answer = second.get("answer") or ""
    assert not _has_number(answer, 3630.0), "第二轮还在回答上一轮的 6 月数字"
    assert _has_number(answer, 29821.0), "第二轮没给出 7 月的 29821.00"


@pytest.mark.parametrize(
    "previous, follow_up, expected_month",
    [
        ("S03 六月第二周营业额为什么这么低", "那七月呢？", "2026-07"),
        ("6 月的净营业额是多少？", "那 7 月呢？", "2026-07"),
        ("S03 六月第二周营业额为什么这么低", "那八月呢？", "2026-08"),
    ],
    ids=["cn-week-then-july", "digit-month-then-july", "cn-week-then-august"],
)
def test_new_time_replaces_the_old_one(service_planner, previous, follow_up, expected_month):
    """新时间一律覆盖旧的，中英文月份写法都要成立。"""
    plan = service_planner.plan(previous, [])
    history = [{"question": previous, "standalone": plan.standalone, "slots": plan.slots}]
    follow = service_planner.plan(follow_up, history)
    assert follow.window and follow.window[0].startswith(expected_month), (
        "%s -> window=%s，期望落在 %s" % (follow_up, follow.window, expected_month)
    )


