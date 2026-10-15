from __future__ import annotations

import threading
import time
from typing import Callable


class Cancelled(Exception):
    pass


class Control:
    """Cooperative controls; no process suspension or half-written DB commits."""

    def __init__(self, emit: Callable[[dict], None] = lambda event: None):
        self._condition = threading.Condition()
        self._paused = False
        self._stopped = False
        self._notified_pause = False
        self.emit = emit

    def command(self, command: str) -> None:
        with self._condition:
            if command == "stop":
                self._stopped = True
            elif command == "pause":
                self._paused = True
            elif command == "resume":
                self._paused = False
            self._condition.notify_all()

    def check(self) -> None:
        with self._condition:
            while self._paused and not self._stopped:
                if not self._notified_pause:
                    self.emit({"type": "state", "state": "paused", "message": "На паузе · состояние сохранено"})
                    self._notified_pause = True
                self._condition.wait(0.25)
            if self._stopped:
                raise Cancelled()
            if self._notified_pause:
                self._notified_pause = False
                self.emit({"type": "state", "state": "scanning", "message": "Продолжение задания"})

    def wait(self, seconds: float) -> None:
        remaining = max(0.0, float(seconds))
        while remaining > 0:
            self.check()
            interval = min(0.2, remaining)
            start = time.monotonic()
            with self._condition:
                self._condition.wait(interval)
            remaining -= time.monotonic() - start
        self.check()
