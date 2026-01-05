from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.tool_call import ToolCall


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def log_tool_call(
    db: Session,
    *,
    run_id: uuid.UUID,
    tool_name: str,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    error: str | None = None,
    step_id: uuid.UUID | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> ToolCall:
    tool_call = ToolCall(
        run_id=run_id,
        step_id=step_id,
        tool_name=tool_name,
        request=request,
        response=response,
        error=error,
        started_at=started_at or utcnow(),
        ended_at=ended_at or (utcnow() if response is not None or error is not None else None),
    )
    db.add(tool_call)
    db.commit()
    db.refresh(tool_call)
    return tool_call


def list_tool_calls_for_run(
    db: Session,
    *,
    run_id: uuid.UUID,
) -> list[ToolCall]:
    stmt = (
        select(ToolCall)
        .where(ToolCall.run_id == run_id)
        .order_by(ToolCall.started_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
