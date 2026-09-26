"""追踪：一次问答的每一步、耗时、错误都记下来，调试面板用，还支持事件订阅：每记一步就同步推给订阅者。"""

from __future__ import annotations

import contextlib
import threading
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterator, Optional

#: 订阅者：收到一个事件字典，形状与 `/api/chat/stream` 的 `data` 一致。
Sink = Callable[[dict], None]


@dataclass
class Trace:
    trace_id: str
    question: str
    session_id: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="milliseconds"))
    steps: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter)
    _sinks: list[Sink] = field(default_factory=list, repr=False, compare=False)

    # -- 订阅 -------------------------------------------------------------------

    def subscribe(self, sink: Sink) -> None:
        """挂一个订阅者。订阅者出错不影响问答本身。"""
        self._sinks.append(sink)

    def _emit(self, event: dict) -> None:
        for sink in list(self._sinks):
            try:
                sink(event)
            except Exception:  # noqa: BLE001 - 推送是旁路，绝不能把问答带崩
                continue

    # -- 记录 -------------------------------------------------------------------

    def step(self, name: str, payload: Any = None, started: Optional[float] = None) -> None:
        now = time.perf_counter()
        entry = {
            "step": name,
            "at_ms": round((now - self._t0) * 1000, 1),
            "took_ms": round((now - started) * 1000, 1) if started else None,
            "detail": payload,
        }
        self.steps.append(entry)
        self._emit({"type": "step", **entry})

    def error(self, where: str, exc: BaseException) -> None:
        """真实原因要留下来：类型、消息、堆栈，一个都不少。"""
        entry = {
            "where": where,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=8),
        }
        self.errors.append(entry)
        self._emit({"type": "error", **entry})

    def llm(self, payload: dict) -> None:
        self.llm_calls.append(payload)
        self._emit({"type": "llm", "call": payload})

    def as_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "question": self.question,
            "started_at": self.started_at,
            "total_ms": round((time.perf_counter() - self._t0) * 1000, 1),
            "steps": self.steps,
            "llm_calls": self.llm_calls,
            "errors": self.errors,
        }


#: 当前线程正在记的那条 trace。
#: 用线程本地变量统一挂上：一个请求始终在同一个线程里跑完，不会串。
_context = threading.local()


@contextlib.contextmanager
def capture(trace: Trace) -> Iterator[Trace]:
    """在这个上下文里，`current()` 返回传进来的这条 trace。"""
    previous = getattr(_context, "trace", None)
    _context.trace = trace
    try:
        yield trace
    finally:
        _context.trace = previous


def current() -> Optional[Trace]:
    """当前线程正在记的 trace；不在作答链路里时返回 None。"""
    return getattr(_context, "trace", None)


class TraceStore:
    def __init__(self, capacity: int = 200) -> None:
        self._data: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()
        self.capacity = capacity
        self._counter = 0

    def new_id(self, today: str) -> str:
        with self._lock:
            self._counter += 1
            return "t-%s-%04d" % (today.replace("-", ""), self._counter)

    def save(self, trace: Trace) -> None:
        with self._lock:
            self._data[trace.trace_id] = trace.as_dict()
            self._data.move_to_end(trace.trace_id)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)

    def get(self, trace_id: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(trace_id)

    def recent(self, limit: int = 50) -> list[dict]:
        """最近的若干条，只给列表要用的摘要，不带逐步明细。"""
        limit = max(1, int(limit or 50))
        with self._lock:
            items = list(self._data.values())[-limit:]
        out: list[dict] = []
        for item in reversed(items):
            answer_type = None
            for step in item.get("steps", []):
                if step.get("step") == "response":
                    answer_type = (step.get("detail") or {}).get("answer_type")
            out.append(
                {
                    "trace_id": item.get("trace_id"),
                    "question": item.get("question"),
                    "session_id": item.get("session_id"),
                    "started_at": item.get("started_at"),
                    "total_ms": item.get("total_ms"),
                    "answer_type": answer_type,
                    "steps": len(item.get("steps", [])),
                    "llm_calls": len(item.get("llm_calls", [])),
                    "errors": len(item.get("errors", [])),
                }
            )
        return out
