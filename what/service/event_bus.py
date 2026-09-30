import queue
import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventBus:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _next_id: int = 1
    _subs: dict[int, queue.Queue[dict[str, Any]]] = field(default_factory=dict)

    def subscribe(self) -> tuple[int, queue.Queue[dict[str, Any]]]:
        with self._lock:
            sid = self._next_id
            self._next_id += 1
            q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=256)
            self._subs[sid] = q
            return sid, q

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            targets = list(self._subs.values())
        for q in targets:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass
