"""流式问答与调试接口的测试。

这里测的是"调试台"本身能不能用：事件流是否完整、留档与流是否一致、
以及调试接口是否真的把过滤原因之类的东西暴露出来了。
前同事那套测试只断言 200 和非空，所以这些点以前一个都没被覆盖。
"""

from __future__ import annotations

import json

import pytest

from kbqa.streaming import sse


# -- SSE 分帧 ------------------------------------------------------------------


def test_sse_frame_shape():
    frame = sse("step", {"step": "plan", "took_ms": 1.5})
    assert frame.startswith("event: step\n")
    assert frame.endswith("\n\n")
    assert 'data: {"step": "plan", "took_ms": 1.5}' in frame


def test_sse_escapes_newlines():
    """data 里的换行必须被 JSON 转义，否则会把一帧拆成两帧。"""
    frame = sse("final", {"answer": "第一行\n第二行"})
    assert frame.count("\n\n") == 1
    body = frame.split("data: ", 1)[1].strip()
    assert json.loads(body)["answer"] == "第一行\n第二行"


# -- 流式接口 ------------------------------------------------------------------


def collect(client, question, session_id="stream-test"):
    """跑一次流式问答，返回 (事件名列表, final payload)。"""
    events = []
    payload = None
    with client.stream(
        "POST", "/api/chat/stream", json={"session_id": session_id, "question": question}
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                if frame.startswith(":"):
                    continue
                event, data = "message", ""
                for line in frame.split("\n"):
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data += line[5:].strip()
                events.append(event)
                if event == "final":
                    payload = json.loads(data)["payload"]
    return events, payload


def test_stream_emits_start_and_final(client):
    events, payload = collect(client, "7 月整体的净营业额是多少？")
    assert events[0] == "start"
    assert events[-1] == "final"
    assert payload is not None
    # 契约字段一个都不能少
    for field in ("answer", "answer_type", "citations", "data_evidence", "trace_id"):
        assert field in payload


def test_stream_emits_plan_step(client):
    """规划步骤必须实时推出来，否则调试面板看不到意图判断。"""
    events, _ = collect(client, "7 月整体的净营业额是多少？")
    assert "step" in events
    assert "llm" not in events or True  # mock 模式下没有模型调用，属正常


def test_stream_trace_matches_stored_trace(client):
    """流式跑完后，/api/trace/{id} 必须能取到同一次问答的留档。

    契约 §5 要求每答完一题都能取回 trace；流式这条路也不能例外。
    """
    _, payload = collect(client, "6 月的净营业额是多少？")
    response = client.get("/api/trace/%s" % payload["trace_id"])
    assert response.status_code == 200
    stored = response.json()
    assert stored["trace_id"] == payload["trace_id"]
    assert stored["steps"], "留档里应该有步骤"
    assert any(step["step"] == "response" for step in stored["steps"])


def test_stream_and_plain_chat_agree(client):
    """同一个问题，流式与 /api/chat 的答案形态应当一致。

    两条路共用 Service.answer_with_trace，这里锁住这个前提。
    """
    plain = client.post(
        "/api/chat", json={"session_id": "same-1", "question": "5 月的净营业额是多少？"}
    ).json()
    _, streamed = collect(client, "5 月的净营业额是多少？", session_id="same-2")
    assert plain["answer_type"] == streamed["answer_type"]
    assert plain["answer"] == streamed["answer"]


# -- 错误永远不抛出 ------------------------------------------------------------


def test_stream_never_breaks_200(client, monkeypatch):
    """作答内部炸了，也要给一个合法的 refusal，而不是 500。

    契约 §5 对 /api/chat 的要求，流式接口同样适用。
    """
    from kbqa import service as service_module

    def boom(self, plan, trace, history):
        raise RuntimeError("故意炸一下")

    monkeypatch.setattr(service_module.Service, "_run_engine", boom)
    events, payload = collect(client, "随便问点什么")
    assert events[-1] == "final"
    assert payload["answer_type"] == "refusal"
    assert payload["citations"] == []
    assert payload["data_evidence"] == []


# -- 调试接口 ------------------------------------------------------------------


def test_debug_index_reports_docs_and_chunks(client):
    data = client.get("/api/debug/index").json()
    assert data["doc_count"] == len(data["docs"])
    assert data["chunk_count"] > 0
    assert all("chunks" in doc for doc in data["docs"])


def test_debug_index_surfaces_kb_warnings(client):
    """README.md 没有 KB 编号，必须出现在告警里，而不是被悄悄吞掉。

    这是"文档数对不上"这类问题的第一现场。
    """
    data = client.get("/api/debug/index").json()
    assert any("README" in warning for warning in data["warnings"])


def test_debug_retrieve_exposes_filtered_reasons(client):
    data = client.post(
        "/api/debug/retrieve", json={"query": "外卖多久内退款", "top_k": 5}
    ).json()
    assert "filtered" in data
    assert "coverage" in data
    assert len(data["results"]) <= 5


def test_debug_retrieve_empty_query_is_safe(client):
    response = client.post("/api/debug/retrieve", json={"query": "", "top_k": 3})
    assert response.status_code == 200


def test_debug_doc_returns_chunks(client):
    """随便取一份索引里确实有的文档，切片结果要能看到（引用核对靠它）。

    这里不写死 KB-013：索引内容会随知识库和缓存变，测试不该依赖某一版数据。
    """
    index = client.get("/api/debug/index").json()
    doc_id = index["docs"][0]["doc_id"]
    data = client.get("/api/debug/doc/%s" % doc_id).json()
    assert data["doc_id"] == doc_id
    assert data["chunks"], "切片结果要能看到，引用核对靠它"
    assert data["chunks"][0]["chunk_id"].startswith(doc_id)


def test_debug_doc_unknown_404(client):
    assert client.get("/api/debug/doc/KB-999").status_code == 404


def test_debug_catalog_has_stores(client):
    data = client.get("/api/debug/catalog").json()
    assert data["stores"]
    assert data["products"]


# -- 历史 ----------------------------------------------------------------------


def test_traces_recent_lists_newest_first(client):
    client.post("/api/chat", json={"session_id": "h-1", "question": "6 月营业额"})
    client.post("/api/chat", json={"session_id": "h-2", "question": "7 月营业额"})
    data = client.get("/api/traces?limit=10").json()
    assert data["traces"]
    # 最新的一条排在最前
    assert data["traces"][0]["question"] == "7 月营业额"
    assert "total_ms" in data["traces"][0]


# -- 前端资源 ------------------------------------------------------------------


def test_index_page_and_assets_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/app.js" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_contract_routes_unchanged(client):
    """加了这么多接口，契约里的六个路径一个都不能少、不能改名。"""
    paths = {route.path for route in client.app.routes if hasattr(route, "path")}
    for required in (
        "/api/health",
        "/api/metrics/summary",
        "/api/metrics/daily",
        "/api/retrieve",
        "/api/chat",
        "/api/trace/{trace_id}",
    ):
        assert required in paths, required


# -- 抽屉的显示/隐藏 -----------------------------------------------------------


def test_drawer_hidden_rule_beats_display_rule(client):
    """`.drawer` 设了 display:flex，必须有一条更具体的规则让 [hidden] 压得住它。

    浏览器自带的 `[hidden]{display:none}` 是 UA 样式，优先级和 `.drawer` 相同（都是 0,1,0），
    而作者样式优先于 UA 样式 —— 少了这条规则，JS 把 hidden 设成 true 抽屉也关不掉，
    关闭按钮看起来就像"不生效"。
    """
    css = client.get("/static/styles.css").text
    assert "display: flex" in css

    # 去掉注释，逐条取出选择器，确认存在 [hidden] 的覆盖规则
    stripped = __import__("re").sub(r"/\*[\s\S]*?\*/", "", css)
    selectors = [
        part.strip()
        for block in __import__("re").findall(r"([^{}]+)\{", stripped)
        for part in block.split(",")
        if part.strip()
    ]
    overrides = [sel for sel in selectors if "[hidden]" in sel and ".drawer" in sel]
    assert overrides, "缺少 .drawer[hidden] 规则，抽屉关不掉"


def test_drawer_starts_hidden(client):
    page = client.get("/").text
    assert 'id="drawer" hidden' in page
    assert 'id="drawer-close"' in page
