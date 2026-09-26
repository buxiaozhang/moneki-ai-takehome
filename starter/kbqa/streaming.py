"""流式问答：把一次 `/api/chat` 的处理过程边做边推给前端。

设计要点（决定了它为什么这么写）：

1. **契约优先**。`/api/chat` 是评测入口，行为一个字都不能变。
   流式是**另一个接口** `/api/chat/stream`，两者共用同一套 `Service.chat`，
   所以流出来的每一步就是真实发生的那一步，不是给界面另外编的旁白。

2. **事件小、结果大**。SSE 事件只带摘要（步骤名、耗时、片段分数、工具名），
   最后的 `final` 事件才带完整的 `citations` / `data_evidence`。
   这样调试面板能实时滚动，又不会把大 JSON 拆得七零八落。

3. **不破坏 200**。任何异常都在生成器内部兜住，转成 `refusal` 事件，
   与 `/api/chat` 的"永远返回合法 JSON"保持一致。
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator, Optional

from .schemas import Answer
from .service import Service
from .trace import Trace


def sse(event: str, data: Any) -> str:
    """拼一条 SSE 记录。`data` 里的换行由 JSON 自己转义，不会破坏分帧。"""
    payload = json.dumps(data, ensure_ascii=False)
    return "event: %s\ndata: %s\n\n" % (event, payload)


class ChatStream:
    """在一次问答外边套一层：trace 每记一步就往队列里塞一个事件。"""

    def __init__(self, service: Service, session_id: Optional[str], question: str) -> None:
        self.service = service
        self.session_id = session_id
        self.question = question
        self.queue: "queue.Queue[Optional[dict]]" = queue.Queue()
        self.trace = Trace(
            trace_id=service.traces.new_id(service.settings.today.isoformat()),
            question=question or "",
            session_id=session_id,
        )
        self.trace.subscribe(self._push)
        self._heartbeat = threading.Event()

    # -- 推送 -------------------------------------------------------------------

    def _push(self, event: dict) -> None:
        self.queue.put(event)

    def _summary(self, event: dict) -> dict:
        """把 trace 事件瘦身成界面要用的形状。

        完整内容仍然留在 `/api/trace/{trace_id}` 里，SSE 只传"现在到哪一步了"。
        """
        kind = event.get("type")
        if kind == "step":
            detail = event.get("detail")
            slim: dict[str, Any] = {}
            if isinstance(detail, dict):
                for key in (
                    "intent",
                    "kind",
                    "standalone_question",
                    "search_query",
                    "window",
                    "store_id",
                    "product_id",
                    "answer_type",
                    "tool",
                    "params",
                    "query",
                    "coverage",
                    "kind_hint",
                ):
                    if key in detail:
                        slim[key] = detail[key]
            return {
                "type": "step",
                "step": event.get("step"),
                "at_ms": event.get("at_ms"),
                "took_ms": event.get("took_ms"),
                "detail": slim,
            }
        if kind == "llm":
            call = event.get("call") or {}
            return {
                "type": "llm",
                "endpoint": call.get("endpoint"),
                "model": call.get("model"),
                "messages": call.get("messages"),
                "tools": call.get("tools"),
                "finish_reason": call.get("finish_reason"),
                "tool_calls": call.get("tool_calls"),
                "has_reasoning": call.get("has_reasoning"),
                "content_chars": call.get("content_chars"),
                "error": call.get("error"),
                "took_ms": call.get("took_ms"),
                "prompt": call.get("prompt"),
                "raw_content": call.get("raw_content"),
            }
        if kind == "error":
            return {
                "type": "error",
                "where": event.get("where"),
                "error_type": event.get("type"),
                "message": event.get("message"),
            }
        return event

    # -- 主流程 -----------------------------------------------------------------

    def run(self) -> None:
        """后台线程里跑完整轮问答，把事件塞进队列，最后塞一个 None 收尾。"""
        try:
            self.queue.put(
                {
                    "type": "start",
                    "trace_id": self.trace.trace_id,
                    "session_id": self.session_id,
                    "question": self.question,
                    "llm_mode": self.service.settings.llm_mode,
                }
            )
            answer = self.service.answer_with_trace(self.trace, self.session_id, self.question)
            payload = {
                "answer": answer.answer,
                "answer_type": answer.answer_type,
                "citations": answer.citations,
                "data_evidence": answer.data_evidence,
                "trace_id": self.trace.trace_id,
            }
            self.queue.put({"type": "final", "payload": payload})
        except Exception as exc:  # noqa: BLE001 - 与 /api/chat 一致：绝不把异常抛给调用方
            self.trace.error("stream", exc)
            self.queue.put(
                {
                    "type": "final",
                    "payload": {
                        "answer": "抱歉，我暂时无法回答。",
                        "answer_type": "refusal",
                        "citations": [],
                        "data_evidence": [],
                        "trace_id": self.trace.trace_id,
                    },
                }
            )
        finally:
            self.queue.put(None)

    def events(self) -> Iterator[dict]:
        """消费事件流，直到问答结束。"""
        while True:
            item = self.queue.get()
            if item is None:
                return
            yield item

    def sse_events(self, heartbeat: float = 15.0) -> Iterator[str]:
        """SSE 分帧。长时间没有新事件时插入注释行，防止代理把连接掐掉。"""
        worker = threading.Thread(target=self.run, name="chat-stream", daemon=True)
        worker.start()
        while True:
            try:
                item = self.queue.get(timeout=heartbeat)
            except queue.Empty:
                # SSE 注释行：契约 §7.3 提到 DeepSeek 也会发 `: keep-alive`，
                # 这里同理，客户端解析时要跳过。
                yield ": keep-alive\n\n"
                if not worker.is_alive() and self.queue.empty():
                    return
                continue
            if item is None:
                return
            yield sse(item.get("type", "message"), self._summary(item))


def stream_chat(
    service: Service, session_id: Optional[str], question: str, heartbeat: float = 15.0
) -> Iterator[str]:
    """给 FastAPI 用的入口：返回一段可以直接 StreamingResponse 的文本流。"""
    yield from ChatStream(service, session_id, question).sse_events(heartbeat=heartbeat)


def answer_events(service: Service, session_id: Optional[str], question: str) -> Iterator[dict]:
    """不做 SSE、只出事件字典的版本，测试里好用。"""
    yield from ChatStream(service, session_id, question).events()
