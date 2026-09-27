"""对话历史。"""

from __future__ import annotations

import threading
from typing import Optional

MAX_TURNS = 6
MAX_SESSIONS = 500


class SessionStore:
    """最近几轮对话，够解追问就行。"""

    def __init__(self, max_sessions: int = MAX_SESSIONS, max_turns: int = MAX_TURNS) -> None:
        self._by_session: dict[str, list[dict]] = {}
        self._order: list[str] = []  # 记录出现顺序，用来淘汰最旧的会话
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self.max_turns = max_turns

    @staticmethod
    def _key(session_id: Optional[str]) -> str:
        """没有 id 时归到一个公共的无名会话，行为与"单会话"一致。"""
        return session_id if session_id else ""

    def history(self, session_id: Optional[str]) -> list[dict]:
        with self._lock:
            return list(self._by_session.get(self._key(session_id), ()))

    def append(self, session_id: Optional[str], turn: dict) -> None:
        key = self._key(session_id)
        with self._lock:
            turns = self._by_session.setdefault(key, [])
            if not turns:
                self._order.append(key)
            turns.append(turn)
            del turns[: max(0, len(turns) - self.max_turns)]
            # 会话数超限时，把最早出现的会话整个丢掉。
            while len(self._order) > self.max_sessions:
                oldest = self._order.pop(0)
                self._by_session.pop(oldest, None)

    def clear(self) -> None:
        with self._lock:
            self._by_session.clear()
            self._order.clear()
