
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

run_id_ctx: ContextVar[Optional[str]] = ContextVar("run_id", default=None)


def set_run_id(run_id: Optional[str]) -> None:
    run_id_ctx.set(run_id)


def get_run_id() -> Optional[str]:
    return run_id_ctx.get()
