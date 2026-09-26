"""看板页面与调试接口。
- `GET  /`                    看板页面（对话 / 索引 / 指标 / 数据质量）
- `POST /api/chat/stream`     流式问答（SSE），边做边推
- `GET  /api/traces`          最近若干次问答
- `GET  /api/debug/index`     哪些文档真的进了索引、切了多少块、跳过了什么
- `GET  /api/debug/doc/{id}`  一份文档的全文与切片（核对引用是否逐字存在）
- `POST /api/debug/retrieve`  检索对照：哪些候选被过滤了、什么原因
- `GET  /api/debug/catalog`   门店/商品维表、数据区间、大模型接入状态
- `GET  /api/debug/config`    当前生效的路径与配置（不含 Key 明文）
- `GET  /api/debug/sql`       在清洗表上跑只读 SQL，自己核对指标
"""

from pathlib import Path

from fastapi import Body, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# 从 server.py 顶层导入：注解在运行时必须能被解析成真实类型（见上面那段说明）。
# server.py 在末尾才 import 本模块，所以这里能安全拿到这些名字。
from .server import ChatRequest, _as_text, service
from .streaming import stream_chat

#: 前端静态文件目录。用 __file__ 定位，不依赖启动时的工作目录。
WEB_DIR = Path(__file__).resolve().parent / "web"


def install(app: FastAPI) -> None:
    """把页面、流式接口与调试接口挂到 app 上。

    由 `server.py` 在文件末尾调用。单独放一个文件是因为这些接口和契约接口不是
    一类东西：混在一起，改调试接口时容易误伤契约。
    """
    _mount_pages(app)
    _register_stream(app)
    _register_debug(app)


# -- 页面 ----------------------------------------------------------------------


def _mount_pages(app: FastAPI) -> None:
    """页面与静态资源。目录不存在就只挂接口，不影响契约。"""
    if not WEB_DIR.exists():
        return
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index_page() -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))


def _register_stream(app: FastAPI) -> None:
    """流式问答。事件类型：start / step / llm / error / final。

    与 `/api/chat` 共用 `Service.answer_with_trace`，所以推出来的每一步和
    `/api/trace/{trace_id}` 的留档是同一份，不会"界面好看、留档另一回事"。
    """

    @app.post("/api/chat/stream", tags=["ui"])
    def chat_stream(request: ChatRequest):
        session_id = _as_text(request.session_id) or None
        question = _as_text(request.question)
        return StreamingResponse(
            stream_chat(service(), session_id, question),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                # 关掉反向代理的缓冲，否则事件会攒着一起到。
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/traces", tags=["ui"])
    def traces(limit: int = 50) -> dict:
        """最近的若干次问答，只给列表要用的摘要。"""
        return {"traces": service().traces.recent(limit)}


# -- 调试接口 ------------------------------------------------------------------


def _register_debug(app: FastAPI) -> None:
    """排查问题用的接口。

    ⚠️ 会把知识库全文、检索中间态、清洗库 SQL 都摊开，**只在开发时用，别对外暴露**。
    """

    @app.get("/api/debug/index", tags=["debug"])
    def debug_index() -> dict:
        """调试"检索为什么没命中"的第一步：文档在不在、块切得对不对。

        特别是 `warnings`：装载时被跳过的文件都记在这里。
        """
        current = service()
        index = current.index
        by_doc: dict[str, int] = {}
        for chunk in index.chunks:
            by_doc[chunk.doc_id] = by_doc.get(chunk.doc_id, 0) + 1

        docs = []
        for doc_id, meta in sorted(index.docs_meta.items()):
            docs.append(
                {
                    "doc_id": doc_id,
                    "title": meta.get("title"),
                    "type": meta.get("type"),
                    "status": meta.get("state"),
                    "effective_from": meta.get("effective_from"),
                    "superseded_by": meta.get("superseded_by"),
                    "stores": meta.get("stores"),
                    "estimates_only": meta.get("estimates_only"),
                    "format": meta.get("format"),
                    "filename": meta.get("filename"),
                    "chunks": by_doc.get(doc_id, 0),
                    "chars": len(index.texts.get(doc_id, "")),
                }
            )
        return {
            "index_key": index.key[:12],
            "doc_count": len(index.docs_meta),
            "chunk_count": len(index.chunks),
            "docs": docs,
            "warnings": index.warnings,
            "kb_dir": str(current.settings.kb_dir),
        }

    @app.get("/api/debug/doc/{doc_id}", tags=["debug"])
    def debug_doc(doc_id: str) -> dict:
        """一份文档的全文与切片：核对"引用的那句话到底在不在原文里"。"""
        current = service()
        if doc_id not in current.index.docs_meta:
            return JSONResponse(status_code=404, content={"error": "没有这份文档：%s" % doc_id})
        return {
            "doc_id": doc_id,
            "meta": current.index.docs_meta.get(doc_id),
            "text": current.index.texts.get(doc_id, ""),
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "kind": chunk.kind,
                    "chars": len(chunk.text),
                    "text": chunk.text,
                }
                for chunk in current.index.chunks_of(doc_id)
            ],
        }

    @app.post("/api/debug/retrieve", tags=["debug"])
    def debug_retrieve(payload: dict = Body(default={})) -> dict:
        """`/api/retrieve` 只给结果，看不出"哪些被挡掉了、为什么"。

        `coverage` 低说明问题里的词在语料里没出现过；
        `filtered` 非空说明候选被元数据规则挡住了（版本、门店不符等）。
        """
        current = service()
        query = _as_text(payload.get("query"))
        top_k = int(payload.get("top_k") or 5)
        result = current.retriever.search(query, top_k=max(1, top_k))
        trace = result.as_trace()
        return {
            "query": query,
            "top_k": top_k,
            "coverage": trace.get("coverage"),
            "expansions": trace.get("expansions"),
            "filtered": trace.get("filtered"),
            "results": [hit.as_result() for hit in result.hits],
            "hits": trace.get("hits"),
        }

    @app.get("/api/debug/catalog", tags=["debug"])
    def debug_catalog() -> dict:
        """门店/商品维表给前端筛选用；顺带回大模型接入状态（**不含 Key**）。"""
        current = service()
        return {
            "stores": current.tools.stores(),
            "products": current.tools.products(),
            "today": current.settings.today.isoformat(),
            "data_period": current.data_period,
            "llm_mode": current.settings.llm_mode,
            "llm_model": current.settings.llm_model or None,
            "llm_base_url": current.settings.llm_base_url or None,
            "llm": current.settings.llm_diagnostics(),
        }

    @app.get("/api/debug/config", tags=["debug"])
    def debug_config() -> dict:
        """排查"配置到底读没读进来"。

        `llm.missing` 会指名道姓说缺哪个变量，`llm.dotenv` 说 .env 是从哪读的。
        契约 §7.2 第四条：**任何接口都不得回传 Key 本身**。
        """
        settings = service().settings
        return {
            "today": settings.today.isoformat(),
            "data_dir": str(settings.data_dir),
            "kb_dir": str(settings.kb_dir),
            "var_dir": str(settings.var_dir),
            "index_path": str(settings.index_path),
            "source_db_exists": settings.source_db.exists(),
            "clean_db_exists": settings.clean_db.exists(),
            "llm": settings.llm_diagnostics(),
            "llm_timeout": settings.llm_timeout,
            "chat_budget": settings.chat_budget,
        }

    @app.get("/api/debug/sql", tags=["debug"])
    def debug_sql(sql: str = Query(..., description="只允许 SELECT / WITH 开头")) -> dict:
        """核对指标算得对不对时最直接的手段：自己写 SQL 对一遍。

        只放行只读语句 —— 这不是为了防住恶意用户（调试接口本就不该对外），
        而是防止手滑把清洗库改坏。
        """
        statement = (sql or "").strip()
        lowered = statement.lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            return JSONResponse(
                status_code=400,
                content={"error": "只允许 SELECT / WITH 开头的只读查询"},
            )
        forbidden = ("insert", "update", "delete", "drop", "alter", "attach", "pragma", "create")
        if any(word in lowered for word in forbidden):
            return JSONResponse(status_code=400, content={"error": "语句里含写操作关键字，已拒绝"})
        try:
            return service().tools.run_sql(statement)
        except Exception as exc:  # noqa: BLE001 - 调试接口，把原始错误回给使用者最有用
            return JSONResponse(
                status_code=400, content={"error": "%s: %s" % (type(exc).__name__, exc)}
            )
