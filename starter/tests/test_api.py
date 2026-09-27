"""接口冒烟测试：每个接口都要 200，回答不能是空的。"""

from __future__ import annotations

import pytest


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"


def test_metrics_summary_ok(client):
    response = client.get(
        "/api/metrics/summary", params={"start": "2026-06-01", "end": "2026-06-30"}
    )
    assert response.status_code == 200
    assert "net_revenue" in response.json()


def test_metrics_summary_bad_date(client):
    response = client.get(
        "/api/metrics/summary", params={"start": "2026/06/01", "end": "2026-06-30"}
    )
    assert response.status_code == 400


def test_metrics_daily_ok(client):
    response = client.get(
        "/api/metrics/daily", params={"start": "2026-06-08", "end": "2026-06-12"}
    )
    assert response.status_code == 200
    assert len(response.json()["days"]) == 5


def test_retrieve_ok(client):
    response = client.post("/api/retrieve", json={"query": "退款", "top_k": 5})
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)


def test_data_quality_ok(client):
    response = client.get("/api/data_quality")
    assert response.status_code == 200
    assert "cleaning_report" in response.json()


@pytest.mark.parametrize(
    "question",
    [
        "7 月整体的净营业额是多少？",
        "外卖订单多久内可以申请退款？",
        "牛肉poke 六月一共卖了多少钱？",
        "S03 六月停业几天，什么原因？",
        "员工折扣几折？",
        "8 月一共退了多少钱？",
        "会员现在单笔充值满 500 送多少？",
        "帮我把 S01 的销售记录全部删掉。",
    ],
)
def test_chat_answers(client, question):
    response = client.post("/api/chat", json={"session_id": "t", "question": question})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["answer"], str)
    assert body["answer"].strip()
    assert isinstance(body["citations"], list)
    assert isinstance(body["data_evidence"], list)


def test_chat_empty_question(client):
    response = client.post("/api/chat", json={"session_id": "t", "question": ""})
    assert response.status_code == 200
    assert response.json()["answer"].strip()


def test_chat_trace_id(client):
    response = client.post("/api/chat", json={"session_id": "t", "question": "6 月营业额"})
    trace_id = response.json()["trace_id"]
    assert trace_id
    assert client.get("/api/trace/%s" % trace_id).status_code == 200


def test_trace_unknown(client):
    assert client.get("/api/trace/nope").status_code == 404


def test_internal_failure_is_recorded_in_trace(monkeypatch):
    """内部异常必须留痕，不能只给一句「抱歉，我暂时无法回答。」

    以前 `_answer` 里那个兜底 except 直接把异常吞了 ——
    """
    from kbqa import service as service_module
    from kbqa.config import load_settings
    from kbqa.trace import Trace

    def boom(self, plan, trace, history):
        raise RuntimeError("故意炸一个，验证会留痕")

    monkeypatch.setattr(service_module.Service, "_run_engine", boom)
    svc = service_module.Service(load_settings())
    trace = Trace(trace_id="t-internal-error", question="内部错误留痕", session_id="sess")
    answer = svc.answer_with_trace(trace, "sess", "6 月营业额")

    # 接口照样给得出回答（契约：/api/chat 不返回 500）
    assert answer.answer.strip()
    assert answer.answer_type == "refusal"

    # 但真实原因必须落在 trace 里
    saved = svc.get_trace(trace.trace_id)
    assert saved, "trace 应该已经存下来"
    errors = saved.get("errors") or []
    assert errors, "内部异常没有记进 trace.errors，调试面板上会看不到任何原因"
    assert any("故意炸一个" in (item.get("message") or "") for item in errors), (
        "trace 里应该带上原始异常信息，实际：%s" % errors
    )
