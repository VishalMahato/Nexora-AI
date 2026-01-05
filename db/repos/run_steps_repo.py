from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.run_step import RunStep


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def log_step(
    db: Session,
    *,
    run_id: uuid.UUID,
    step_name: str,
    status: str,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    agent: str | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> RunStep:
    step = RunStep(
        run_id=run_id,
        step_name=step_name,
        status=status,
        agent=agent,
        input=input,
        output=output,
        error=error,
        started_at=started_at or utcnow(),
        ended_at=ended_at or (utcnow() if status in {"DONE", "FAILED"} else None),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def list_steps_for_run(db: Session, *, run_id: uuid.UUID) -> list[RunStep]:
    stmt = (
        select(RunStep)
        .where(RunStep.run_id == run_id)
        .order_by(RunStep.started_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
