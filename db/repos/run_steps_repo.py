from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.run_step import RunStep
from db.models.run import Run
from app.services.run_events import publish_event


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
    if status == "STARTED":
        run = db.get(Run, run_id)
        if run is not None:
            run.current_step = step_name
            db.add(run)
    db.add(step)
    db.commit()
    db.refresh(step)

    summary = None
    if isinstance(output, dict):
        summary = output.get("summary")
    if status == "FAILED" and error:
        summary = summary or error

    publish_event(
        str(run_id),
        {
            "type": "run_step",
            "eventId": f"step:{step.id}",
            "step": step_name,
            "status": status,
            "summary": summary,
            "agent": agent,
        },
    )
    return step


def list_steps_for_run(db: Session, *, run_id: uuid.UUID) -> list[RunStep]:
    stmt = (
        select(RunStep)
        .where(RunStep.run_id == run_id)
        .order_by(RunStep.started_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
