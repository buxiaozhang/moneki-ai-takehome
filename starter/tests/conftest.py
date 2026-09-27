"""测试夹具。

检索这块在测试里整个换成固定返回，这样测试就不用跟着知识库一起改，
跑起来也快。要看真实检索效果直接起服务问两句就行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAKE_TEXT = "退款政策 v2 > 三、时限：外卖订单在订单送达后 24 小时内可以申请退款。"


@pytest.fixture(scope="session", autouse=True)
def hermetic_llm_config():
    """整套测试默认不读工作目录里的 `.env`。

    本机开发时根目录通常有一份真实 `.env`（接真模型用的）。`load_settings()`
    会把它读进来，于是：
      - 断言"没配就是 mock"的用例会变成 live；
      - 问答用例会去打真实模型，慢、要花钱、结果还不确定 —— 测试本该是确定的。

    这里的测试全部按降级模式写，所以默认把发现逻辑关掉。
    要验证 `.env` 读取规则的用例传显式路径，不受影响（见 test_config.py）。
    """
    previous = os.environ.get("KBQA_NO_DOTENV")
    os.environ["KBQA_NO_DOTENV"] = "1"
    yield
    if previous is None:
        os.environ.pop("KBQA_NO_DOTENV", None)
    else:
        os.environ["KBQA_NO_DOTENV"] = previous


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    os.environ["VAR_DIR"] = str(tmp_path_factory.mktemp("var"))
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        os.environ.pop(key, None)

    from fastapi.testclient import TestClient

    from kbqa import retriever as retriever_module
    from kbqa import server

    def fake_search(self, query, top_k=5, **kwargs):
        hit = retriever_module.Hit(
            doc_id="KB-013",
            chunk_id="KB-013#1",
            score=42.0,
            text=FAKE_TEXT,
            source_text=FAKE_TEXT,
            meta={"title": "退款政策 v2", "status": "现行"},
        )
        return retriever_module.SearchResult(
            hits=[hit][:top_k],
            query=query,
            terms=[],
            expansions=[],
            filtered=[],
            coverage=1.0,
        )

    retriever_module.Retriever.search = fake_search
    return TestClient(server.app)
