from __future__ import annotations

from datetime import datetime, timezone
from queue import Queue
from threading import Lock
from typing import Any

_subscribers: dict[str, list[Queue[dict[str, Any]]]] = {}
_lock = Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def publish_event(run_id: str, event: dict[str, Any]) -> None:
    event.setdefault("runId", run_id)
    event.setdefault("timestamp", _utcnow_iso())
    with _lock:
        queues = list(_subscribers.get(run_id, []))
    for queue in queues:
        queue.put(event)


def subscribe(run_id: str) -> Queue[dict[str, Any]]:
    queue: Queue[dict[str, Any]] = Queue()
    with _lock:
        _subscribers.setdefault(run_id, []).append(queue)
    return queue


def unsubscribe(run_id: str, queue: Queue[dict[str, Any]]) -> None:
    with _lock:
        queues = _subscribers.get(run_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues and run_id in _subscribers:
            _subscribers.pop(run_id, None)
