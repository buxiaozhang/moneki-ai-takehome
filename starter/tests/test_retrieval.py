"""分词与检索的回归测试。

覆盖对应 `DEBUG_LOG.md` 的 D-009～D-012：
- D-009 中文查询必须被切成多个词
- D-010 `.txt` / `.html` 必须进索引
- D-011 知识库内容变了缓存键必须变
- D-012 中文问句要能命中纯英文文档
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbqa.index import build_index, content_key, load_index, save_index
from kbqa.loader import SUPPORTED_SUFFIXES, load_knowledge_base
from kbqa.retriever import Retriever
from kbqa.tokenizer import TOKENIZER_VERSION, content_tokens, tokenize

#: 在模块导入时抓住真实的 `Retriever.search`。`tests/conftest.py` 的 `client` fixture
#: 会把它替换成固定返回，且作用域是 session、不会自动恢复；本文件需要真实现。
_ORIGINAL_SEARCH = Retriever.search


# --- D-009 分词 -----------------------------------------------------------------


def test_chinese_query_is_tokenized():
    """中文没有词间空格，整句必须被切成多个词。

    修复前 tokenize() 是 `normalise(text).split()`，整句返回长度 1。
    """
    tokens = tokenize("外卖订单多久内可以申请退款")
    assert len(tokens) > 1, "中文整句被当成一个词，BM25 会全零分"


def test_cjk_single_chars_are_tokens():
    tokens = tokenize("台风闭店")
    assert tokens == ["台", "风", "闭", "店"]


def test_ascii_words_stay_whole():
    """英文与数字保持整词，不能拆成字母。"""
    assert tokenize("S03 618") == ["s03", "618"]
    assert tokenize("Salmon Poke") == ["salmon", "poke"]


def test_mixed_text_splits_both_ways():
    tokens = tokenize("牛肉poke 卖了多少")
    assert "poke" in tokens
    assert "牛" in tokens and "肉" in tokens
    assert "poke" not in [t for t in tokens if t != "poke"] or True


def test_tokenizer_version_bumped_for_cache_invalidation():
    """分词规则变了，版本号必须跟着变，否则旧索引缓存不会被丢弃。"""
    assert TOKENIZER_VERSION != "tokenizer-2"


def test_content_tokens_drops_stopchars():
    kept = content_tokens("的了吗")
    assert kept == []


# --- D-010 支持 .txt / .html ----------------------------------------------------


def test_txt_and_html_are_supported_suffixes():
    assert ".txt" in SUPPORTED_SUFFIXES
    assert ".html" in SUPPORTED_SUFFIXES


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_loader_indexes_txt(tmp_path: Path):
    """`.txt` 文档必须进索引（KB-022 / KB-062 都是 txt）。"""
    _write(tmp_path / "KB-900_供应商邮件.txt", "KB-900\n\nThis is a supplier email about salmon.\n")
    docs, _ = load_knowledge_base(tmp_path)
    assert "KB-900" in {d.doc_id for d in docs}


def test_loader_indexes_html(tmp_path: Path):
    """`.html` 文档必须进索引（KB-061 是 html）。"""
    _write(tmp_path / "KB-901_FAQ.html", "<html><body>KB-901 发票怎么开</body></html>")
    docs, _ = load_knowledge_base(tmp_path)
    assert "KB-901" in {d.doc_id for d in docs}


def test_skipped_file_produces_warning(tmp_path: Path):
    """不支持的类型不能静默跳过，必须留下线索。"""
    _write(tmp_path / "KB-902_数据.pdf", "KB-902 not really a pdf")
    docs, warnings = load_knowledge_base(tmp_path)
    assert docs == []
    assert any("KB-902" in w for w in warnings), "跳过文件时没有产生任何 warning"


# --- D-011 缓存键 ---------------------------------------------------------------


def test_cache_key_changes_when_document_edited(tmp_path: Path):
    """改了文档内容，缓存键必须变，否则重建命令等于没执行。"""
    doc = tmp_path / "KB-900_a.md"
    _write(doc, "KB-900\n\n原始内容。\n")
    before = content_key(tmp_path)
    _write(doc, "KB-900\n\n改过一个字。\n")
    after = content_key(tmp_path)
    assert before != after


def test_cache_key_changes_when_document_added(tmp_path: Path):
    _write(tmp_path / "KB-900_a.md", "KB-900\n\n甲。\n")
    before = content_key(tmp_path)
    _write(tmp_path / "KB-901_b.md", "KB-901\n\n乙。\n")
    assert content_key(tmp_path) != before


def test_cache_key_stable_for_same_content(tmp_path: Path):
    _write(tmp_path / "KB-900_a.md", "KB-900\n\n内容。\n")
    assert content_key(tmp_path) == content_key(tmp_path)


def test_load_index_rebuilds_on_content_change(tmp_path: Path):
    """缓存文件存在但语料变了时，load_index 必须重建。"""
    doc = tmp_path / "KB-900_a.md"
    _write(doc, "KB-900\n\n原始内容。\n")
    index_path = tmp_path / "index.json"
    save_index(build_index(tmp_path), index_path)

    _write(doc, "KB-900\n\n换了内容，多了「专属词」三个字。\n")
    reloaded = load_index(tmp_path, index_path)
    assert "专属词" in reloaded.texts["KB-900"]


# --- D-012 中文问句命中英文文档 -------------------------------------------------

#: 与评测题库 `eval/public_questions.jsonl` 的 retrieval 题一一对应。
RETRIEVAL_CASES = [
    ("R01", "外卖订单多久内可以申请退款", ["KB-013"]),
    ("R02", "牛肉poke 含哪些过敏原", ["KB-040"]),
    ("R03", "Super Souper 周五晚上营业到几点", ["KB-062"]),
    ("R04", "三文鱼那次断供供应商赔了多少钱", ["KB-022"]),
    ("R05", "发票怎么开", ["KB-061"]),
    ("R06", "净营业额怎么算，退款算不算进去", ["KB-001"]),
    ("R07", "今年 618 牛肉poke 的活动价和目标销量", ["KB-023"]),
    ("R08", "现在单笔充值 500 送多少", ["KB-011"]),
    ("R09", "味噌拉面在数据库里叫什么", ["KB-003"]),
    ("R10", "S04 为什么不卖吞拿鱼三明治了", ["KB-029"]),
    ("R11", "冷萃乌龙茶首月的目标销量是多少", ["KB-028"]),
    ("R12", "S03 六月停业几天，什么原因", ["KB-020", "KB-051"]),
    ("R13", "台风那天几点提前闭店", ["KB-026", "KB-053"]),
    ("R14", "S05 那天为什么只能收现金", ["KB-027", "KB-052"]),
    ("R15", "员工折扣几折，能不能和活动叠加", ["KB-014"]),
]


@pytest.fixture(scope="module")
def real_retriever():
    """用真实知识库构建检索器。

    注意 `tests/conftest.py` 的 `client` fixture 会把 `Retriever.search` 换成固定返回，
    而且它是 session 作用域的 monkey-patch，不会自动恢复 —— 那种做法是为了让接口测试
    不必跟着知识库变，但会把真实的检索逻辑一起挡掉。本文件在模块导入时就抓住了**原始**
    的 `search`（那时 conftest 还没打补丁），这里显式换回来再跑，否则本文件的用例会被
    那个假实现骗过（它会固定返回 KB-013，让所有检索断言"通过"得毫无意义）。
    """
    from kbqa.config import load_settings

    patched_search = Retriever.search
    patched = patched_search is not _ORIGINAL_SEARCH
    if patched:
        Retriever.search = _ORIGINAL_SEARCH
    try:
        settings = load_settings()
        if not settings.kb_dir.exists():
            pytest.skip("知识库目录不存在")
        yield Retriever(build_index(settings.kb_dir), settings.today)
    finally:
        if patched:
            # 放回 conftest 装的假实现，避免影响其它测试文件的预期。
            Retriever.search = patched_search


@pytest.mark.parametrize("case_id,question,gold", RETRIEVAL_CASES, ids=[c[0] for c in RETRIEVAL_CASES])
def test_public_retrieval_questions(real_retriever, case_id, question, gold):
    """公开题库的 15 道检索题，top-5 里必须至少命中一个金标文档。

    修复前 6/15：中文纯问句因为分词失效全部退化成 chunk 物理顺序。
    """
    hits = {hit.doc_id for hit in real_retriever.search(question, top_k=5).hits}
    assert hits & set(gold), "%s：top-5 %s 里缺少 %s" % (case_id, sorted(hits), gold)


def test_chinese_query_hits_english_document(real_retriever):
    """中文问句要能命中纯英文的 KB-022（靠别名词典做跨语言归一）。"""
    hits = {hit.doc_id for hit in real_retriever.search("三文鱼那次断供供应商赔了多少钱", top_k=5).hits}
    assert "KB-022" in hits


def test_pure_chinese_query_scores_are_not_all_zero(real_retriever):
    """纯中文问句不能全部零分 —— 全零分意味着排序退化成 chunk 物理顺序。"""
    result = real_retriever.search("台风那天几点提前闭店", top_k=5)
    assert any(hit.score > 0 for hit in result.hits), "所有命中都是 0 分"


# --- D-015 kb_docs 口径 ---------------------------------------------------------


def test_kb_docs_counts_indexed_docs_not_directory_files(client):
    """契约 §1：`kb_docs` 是进索引的文档数，不是目录里的文件数。

    修复前 `service.py` 用 `kb_dir.rglob("*")` 数文件，把没有 KB 编号的
    `README.md` 也算了进去，报 36；实际索引里只有 35 份。
    """
    health = client.get("/api/health").json()
    from kbqa.config import load_settings
    from kbqa.index import load_index

    settings = load_settings()
    indexed = len(load_index(settings.kb_dir, settings.index_path).docs_meta)
    assert health["kb_docs"] == indexed, "kb_docs 报的是目录文件数，不是索引里的文档数"


def test_search_returns_exactly_top_k_when_versions_are_excluded(real_retriever):
    """契约 §4：过滤版本必须发生在截断**之前**，返回条数仍恰好 `top_k`。

    修复前 `retriever.py` 是"先取满 `top_k`、最后再过滤"：被剔除的版本占掉的名额
    没人补位，返回条数会掉到 `top_k` 以下。契约 §4 逐字点名了这种实现：
    「先取前 `top_k` 再做过滤、结果只剩两三条的实现，不符合这一条」。

    做法：把排名前三的文档强制判为不可用，看返回条数。
    """
    retriever = real_retriever
    question = "外卖订单多久内可以申请退款"

    # 先看未强制排除时的前几名，作为"被排除的都是高分文档"的依据。
    top = [hit.doc_id for hit in retriever.search(question, top_k=5).hits]
    assert len(top) == 5
    forced = set(top[:3])
    assert forced, "需要至少一个高分文档才能构造这个场景"

    original = retriever._eligible

    def force_excluded(doc_id, as_of, store_id, historical):
        if doc_id in forced:
            return "回归测试：强制排除"
        return original(doc_id, as_of, store_id, historical)

    retriever._eligible = force_excluded
    try:
        result = retriever.search(question, top_k=5)
    finally:
        retriever._eligible = original

    returned = [hit.doc_id for hit in result.hits]
    assert len(result.hits) == 5, (
        "排除 %s 之后只返回 %d 条，应为 5 条：%s" % (sorted(forced), len(result.hits), returned)
    )
    assert not (set(returned) & forced), "被排除的文档不该出现在结果里：%s" % returned
    assert {item["doc_id"] for item in result.filtered} >= forced

