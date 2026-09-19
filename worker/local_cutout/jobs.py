"""Cooperative cancellation also interrupts blocked FFmpeg pipe reads/writes."""
import subprocess
import threading
import time
from collections.abc import Callable

from .errors import Cancelled


class Job:
    def __init__(self, job_id: str, emit: Callable[[dict], None]):
        self.id = job_id
        self.emit = emit
        self.cancelled = threading.Event()
        self._processes: set[subprocess.Popen] = set()
        self._lock = threading.Lock()
        self.started = time.monotonic()

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled()

    def cancel(self):
        self.cancelled.set()
        with self._lock:
            for process in self._processes:
                if process.poll() is None:
                    process.kill()

    def register(self, process: subprocess.Popen):
        with self._lock:
            self._processes.add(process)
            if self.cancelled.is_set() and process.poll() is None:
                process.kill()

    def unregister(self, process: subprocess.Popen):
        with self._lock:
            self._processes.discard(process)

    def progress(self, stage: str, current: int = 0, total: int = 0, **extra):
        self.check()
        elapsed = time.monotonic() - self.started
        self.emit({"v": 1, "event": "progress", "job_id": self.id,
                   "stage": stage, "current": current, "total": total,
                   "elapsed": elapsed, **extra})
