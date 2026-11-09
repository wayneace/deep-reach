"""One action's time budget.

Waiting in the browser queue pauses the clock: time spent waiting for a slot
must not eat the time the backend gets to answer.
"""

from __future__ import annotations

import threading
import time


class Clock:
    def __init__(self, budget: float) -> None:
        self._lock = threading.Lock()
        self._deadline = time.monotonic() + max(0.0, budget)
        self._paused_at = None
        self._depth = 0

    def remaining(self) -> float:
        with self._lock:
            return self._deadline - (self._paused_at or time.monotonic())

    def pause(self) -> None:
        with self._lock:
            if self._depth == 0:
                self._paused_at = time.monotonic()
            self._depth += 1

    def resume(self) -> None:
        with self._lock:
            self._depth = max(0, self._depth - 1)
            if self._depth == 0 and self._paused_at is not None:
                self._deadline += time.monotonic() - self._paused_at
                self._paused_at = None
