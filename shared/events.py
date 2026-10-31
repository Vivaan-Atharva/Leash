"""Fire-and-forget event publishing to the hub. Never blocks or fails the caller.

Events go through one background thread so a service's events keep their order.
"""
import queue
import threading

import httpx

from shared.config import url
from shared.timeutil import now_iso

_q: "queue.Queue[dict]" = queue.Queue(maxsize=5000)
_started = False
_lock = threading.Lock()


def _worker() -> None:
    client = httpx.Client(timeout=1.0)
    while True:
        batch = [_q.get()]
        while len(batch) < 50:
            try:
                batch.append(_q.get_nowait())
            except queue.Empty:
                break
        try:
            client.post(f"{url('hub')}/events", json=batch)
        except httpx.HTTPError:
            pass  # hub down: the UI misses events, money path is unaffected


def emit(type_: str, lane: str, data: dict) -> None:
    global _started
    with _lock:
        if not _started:
            threading.Thread(target=_worker, daemon=True, name="leash-events").start()
            _started = True
    try:
        _q.put_nowait({"ts": now_iso(), "lane": lane, "type": type_, "data": data})
    except queue.Full:
        pass
