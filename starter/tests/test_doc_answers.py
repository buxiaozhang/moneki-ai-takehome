"""知识库加载与检索结果的回归测试。

覆盖 `DEBUG_LOG.md` 的 D-016～D-021，以及随 doc 分类修复一起发现的
两个加载缺陷（GB18030 解码、HTML 标签未剥离）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbqa.index import build_index
from kbqa.loader import decode_bytes, load_document
from kbqa.retriever import Retriever

#: 模块导入时抓住真实的 `Retriever.search`。
#: `tests/conftest.py` 的 `client` fixture 会把它换成固定返回 KB-013 的假实现，
#: 且作用域是 session、不会自动恢复 —— 那种做法对接口契约测试没问题，
#: 但会让"引用是否正确"这类断言被假数据骗过。本文件要用真实现。
_ORIGINAL_SEARCH = Retriever.search


@pytest.fixture
def doc_client():
    """不经过 conftest 那层 `Retriever.search` 替换的 TestClient。"""
    patched = Retriever.search
    if patched is not _ORIGINAL_SEARCH:
        Retriever.search = _ORIGINAL_SEARCH
    try:
        from fastapi.testclient import TestClient

        from kbqa import server

        yield TestClient(server.app)
    finally:
        Retriever.search = patched

# --- D-018 doc_id 必须与 chunk_id 同源 -----------------------------------------

DOC_QUESTIONS = [
    ("C01", "外卖订单多久内可以申请退款？", ["KB-013"]),
    ("C02", "有顾客问牛肉poke 里有哪些过敏原，怎么答？", ["KB-040"]),
    ("C03", "Super Souper 现在周五晚上营业到几点？", ["KB-062"]),
    ("C04", "三文鱼那次断供，供应商最后赔了我们多少钱？", ["KB-022"]),
    ("C05", "顾客要开发票，怎么跟他说？", ["KB-061"]),
    ("C06", "退款在净营业额里是怎么算的？", ["KB-001"]),
    ("C07", "S04 为什么不卖吞拿鱼三明治了？", ["KB-029"]),
    ("C08", "员工迟到多久算一次？", ["KB-016"]),
]

#: 除 doc 外，其余会走检索的公开题，用来盯住"改了排序别把别的题弄坏"。
OTHER_QUESTIONS = [
    ("R01", "外卖订单多久内可以申请退款"),
    ("R02", "牛肉poke 含哪些过敏原"),
    ("R03", "Super Souper 周五晚上营业到几点"),
    ("R04", "三文鱼那次断供供应商赔了多少钱"),
    ("R05", "发票怎么开"),
    ("R06", "净营业额怎么算，退款算不算进去"),
    ("R07", "今年 618 牛肉poke 的活动价和目标销量"),
    ("R08", "现在单笔充值 500 送多少"),
    ("R09", "味噌拉面在数据库里叫什么"),
    ("R10", "S04 为什么不卖吞拿鱼三明治了"),
    ("R11", "冷萃乌龙茶首月的目标销量是多少"),
    ("R12", "S03 六月停业几天，什么原因"),
    ("R13", "台风那天几点提前闭店"),
    ("R14", "S05 那天为什么只能收现金"),
    ("R15", "员工折扣几折，能不能和活动叠加"),
]


@pytest.fixture(scope="module")
def real_index():
    from kbqa.config import load_settings

    settings = load_settings()
    if not settings.kb_dir.exists():
        pytest.skip("知识库目录不存在")
    return build_index(settings.kb_dir)


def test_every_hit_doc_id_matches_its_chunk_id(real_index):
    """`hit.doc_id` 必须和 `hit.chunk_id` 指向同一篇文档。

    修复前 `retriever.py:276` 会用排序列表的下标覆盖 `doc_id`，
    导致 `doc_id=KB-016` 配上 `chunk_id=KB-060#4` 这种自相矛盾的命中，
    引用链据此给出完全错误的 citations（C07/C08 因此扣分）。
    """
    from kbqa.retriever import Retriever
    from kbqa.config import load_settings

    retriever = Retriever(real_index, load_settings().today)
    bad: list[str] = []
    questions = [q for _, q, _g in DOC_QUESTIONS] + [q for _, q in OTHER_QUESTIONS]
    for question in questions:
        for hit in retriever.search(question, top_k=5).hits:
            real = hit.chunk_id.split("#")[0]
            if hit.doc_id != real:
                bad.append("%s -> doc_id=%s chunk_id=%s" % (question, hit.doc_id, hit.chunk_id))
    assert not bad, "doc_id 与 chunk_id 不一致：\n" + "\n".join(bad)


def test_retrieval_hits_are_not_all_zero(real_index):
    """纯中文问句不能全部零分（零分意味着排序退化成 chunk 物理顺序）。"""
    from kbqa.retriever import Retriever
    from kbqa.config import load_settings

    retriever = Retriever(real_index, load_settings().today)
    for _, question, _ in DOC_QUESTIONS:
        hits = retriever.search(question, top_k=5).hits
        assert any(hit.score > 0 for hit in hits), "%s 全部零分" % question


# --- D-017 doc 回答长度上限 -----------------------------------------------------


def test_doc_answers_stay_within_delivery_limit(doc_client):
    """doc 类回答不超过 1200 字 —— 运营要的是一段能读的话。

    修复前 `answerer._context()` 会把整篇原文（KB-001 整本手册、KB-061 整页 HTML）
    拼在答案前面且不封顶，C02 到了 1677 字、C06 到了 2551 字。
    """
    for case_id, question, _ in DOC_QUESTIONS:
        body = doc_client.post("/api/chat", json={"question": question, "session_id": "len-" + case_id}).json()
        answer = body.get("answer") or ""
        assert len(answer) <= 1200, "%s 回答 %d 字，超过 1200" % (case_id, len(answer))


def test_doc_answers_do_not_dump_raw_html(doc_client):
    """回答里不能出现 HTML 标签 —— 引用要的是可见正文。"""
    body = doc_client.post(
        "/api/chat", json={"question": "顾客要开发票，怎么跟他说？", "session_id": "html-c05"}
    ).json()
    answer = body.get("answer") or ""
    for tag in ("<p>", "</p>", "<meta", "<style", "<div"):
        assert tag not in answer, "回答里混进了 HTML 标签 %s" % tag


# --- D-021 候选排序：该引的文档要引对 -------------------------------------------


@pytest.mark.parametrize("case_id,question,gold", DOC_QUESTIONS, ids=[c[0] for c in DOC_QUESTIONS])
def test_doc_questions_cite_the_gold_document(doc_client, case_id, question, gold):
    """公开题库的 8 道 doc 题必须引用金标文档，且 answer_type 是 doc/hybrid。

    修复前 0/8：意图被改判成 data、候选句按升序挑到了最低分的句子、
    被取代的旧版本压过现行版、KB-062 按 UTF-8 解码后正文为空。
    """
    body = doc_client.post("/api/chat", json={"question": question, "session_id": "cite-" + case_id}).json()
    cited = [c.get("doc_id") for c in (body.get("citations") or [])]
    assert body.get("answer_type") in ("doc", "hybrid"), "%s answer_type=%s" % (
        case_id,
        body.get("answer_type"),
    )
    assert set(gold) & set(cited), "%s 引用了 %s，缺少 %s" % (case_id, cited, gold)


def test_current_version_outranks_superseded(doc_client):
    """问现行规定时，当前版本要排在已废止版本之前。

    KB-012（退款政策 v1，2025-10-01）的 BM25 分数高于 KB-013（v2，2026-06-15），
    修复前引用的是 v1 的「7 天」，正确答案是 v2 的「24 小时」。
    """
    body = doc_client.post(
        "/api/chat", json={"question": "外卖订单多久内可以申请退款？", "session_id": "ver-c01"}
    ).json()
    cited = [c.get("doc_id") for c in (body.get("citations") or [])]
    assert "KB-013" in cited, "引用的是 %s，应为现行版 KB-013" % cited
    assert "24" in (body.get("answer") or ""), "答案里应包含 24 小时"


def test_underspecified_question_with_citations_is_answered(doc_client):
    """已经拿到可引用原文时不该反问。

    C05「顾客要开发票，怎么跟他说？」有明确主题，只是没有制度词，
    修复前因为 `underspecified` 且分数略低于阈值被反问成 clarify。
    """
    body = doc_client.post(
        "/api/chat", json={"question": "顾客要开发票，怎么跟他说？", "session_id": "cl-c05"}
    ).json()
    assert body.get("answer_type") != "clarify", "有引用却仍然反问了"
    assert "KB-061" in [c.get("doc_id") for c in (body.get("citations") or [])]


# --- 加载缺陷：GB18030 解码 -----------------------------------------------------


def test_gb18030_document_decodes_to_chinese(tmp_path: Path):
    """非 UTF-8 的老文件要按 GB18030 回退解码，而不是把中文丢掉。

    KB-062 是整份 GB18030 编码的中文公文。修复前 `decode_bytes` 用
    `errors="ignore"`，整篇中文被**删除**，只剩 `=` 和数字，
    文档虽然在索引里但内容为空，问「营业到几点」永远命不中。
    """
    raw = "合味餐饮管理（上海）有限公司 营业时间调整至 23:00".encode("gb18030")
    warnings: list[str] = []
    text = decode_bytes(raw, Path("KB-900_旧OA.txt"), warnings)
    assert "合味餐饮" in text, "GB18030 中文没有解出来：%r" % text
    assert "23:00" in text
    assert any("GB18030" in w for w in warnings), "回退解码应留下 warning"


def test_utf8_document_still_decodes(tmp_path: Path):
    warnings: list[str] = []
    text = decode_bytes("普通 UTF-8 中文".encode("utf-8"), Path("KB-901.md"), warnings)
    assert text == "普通 UTF-8 中文"
    assert warnings == []


def test_real_kb062_is_readable(real_index):
    """真实知识库里的 KB-062 必须能读出中文正文和它的关键事实。"""
    meta = real_index.docs_meta.get("KB-062")
    assert meta, "KB-062 不在索引里"
    assert "合味餐饮" in (meta.get("title") or ""), "标题还是乱码：%r" % meta.get("title")
    body = "".join(chunk.text for chunk in real_index.chunks_of("KB-062"))
    assert "23:00" in body, "KB-062 正文里没有恢复出 23:00"


# --- 加载缺陷：HTML 标签未剥离 --------------------------------------------------


def test_html_document_has_no_tags(tmp_path: Path):
    """HTML 文档入库前要剥掉标签，只留可见正文。

    KB-061 是一整页 HTML。修复前注释写着"标签也就那么几个，BM25 自己会忽略"，
    实测入库后有 153 个标签，引用会带上 `<p>`，而 quote 要求逐字引用可见正文。
    """
    path = tmp_path / "KB-902_FAQ.html"
    path.write_text(
        "<html><head><title>FAQ - 合味</title><style>p{color:red}</style></head>"
        "<body><p>发票在小程序里自助开具。</p></body></html>",
        encoding="utf-8",
    )
    doc = load_document(path)
    assert doc is not None
    assert "<p>" not in doc.text
    assert "<style" not in doc.text
    assert "color:red" not in doc.text
    assert "发票在小程序里自助开具。" in doc.text
    assert doc.title == "FAQ"


def test_real_kb061_has_no_tags(real_index):
    """真实知识库里的 KB-061 入库后不该再有标签。"""
    body = "".join(chunk.text for chunk in real_index.chunks_of("KB-061"))
    for tag in ("<p>", "<meta", "<style", "<div", "<!DOCTYPE"):
        assert tag not in body, "KB-061 里残留了 HTML 标签 %s" % tag
    assert "发票在小程序" in body
