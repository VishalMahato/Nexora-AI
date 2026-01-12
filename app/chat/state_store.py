from __future__ import annotations

import time
from typing import Any


_STORE: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def get(conversation_id: str) -> dict[str, Any] | None:
    state = _STORE.get(conversation_id)
    if not state:
        return None
    expires_at = state.get("expires_at")
    if expires_at is not None and expires_at <= _now():
        _STORE.pop(conversation_id, None)
        return None
    return state


def set(
    conversation_id: str,
    state: dict[str, Any],
    *,
    ttl_seconds: int = 1200,
) -> None:
    now = _now()
    state = dict(state)
    state["updated_at"] = now
    state["expires_at"] = now + ttl_seconds
    _STORE[conversation_id] = state


def delete(conversation_id: str) -> None:
    _STORE.pop(conversation_id, None)


def cleanup() -> None:
    now = _now()
    for key, state in list(_STORE.items()):
        expires_at = state.get("expires_at")
        if expires_at is not None and expires_at <= now:
            _STORE.pop(key, None)
