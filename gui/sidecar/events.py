"""AG-UI event bus.

Workflow runs execute in worker threads; WebSocket clients live on the
FastAPI asyncio loop. publish() is thread-safe and fans events out to every
subscribed client queue.

Event envelope follows AG-UI conventions (FR-21): uppercase `type`, flat
payload, millisecond `timestamp`. Emitted types:

  RUN_STARTED, STEP_STARTED, STEP_FINISHED, TEXT_MESSAGE_CONTENT,
  TOOL_CALL_START, TOOL_CALL_END, APPROVAL_REQUIRED, APPROVAL_RESOLVED,
  RUN_FINISHED, RUN_ERROR
"""
from __future__ import annotations

import asyncio
import threading
import time


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self.history: list[dict] = []  # ring buffer of recent events
        self._history_max = 500

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event_type: str, **payload) -> None:
        """Thread-safe publish from worker threads or the loop itself."""
        event = {
            "type": event_type,
            "timestamp": int(time.time() * 1000),
            **payload,
        }
        self.history.append(event)
        if len(self.history) > self._history_max:
            del self.history[: -self._history_max]
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._fanout, event)

    def _fanout(self, event: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client; drop rather than block the run


bus = EventBus()
