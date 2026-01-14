from __future__ import annotations

import uuid
from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models.run import Run
from app.domain.run_status import  assert_valid_transition
from db.models.run import RunStatus
from app.services.run_events import publish_event



class RunNotFoundError(Exception):
    pass


class RunStatusConflictError(Exception):
    pass


def create_run(db: Session, *, intent: str, wallet_address: str, chain_id: int) -> Run:
    run = Run(
        intent=intent,
        wallet_address=wallet_address,
        chain_id=chain_id,
        status=RunStatus.CREATED.value,
        error_code=None,
        error_message=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: uuid.UUID) -> Run | None:
    return db.execute(select(Run).where(Run.id == run_id)).scalar_one_or_none()


def update_run_status(
    db: Session,
    *,
    run_id: uuid.UUID,
    to_status: RunStatus,
    expected_from: RunStatus | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    current_step: str | None = None,
    final_status: str | None = None,
) -> Run:
    run = get_run(db, run_id)
    if not run:
        raise RunNotFoundError(f"Run not found: {run_id}")

    current = RunStatus(run.status)

    if expected_from is not None and current != expected_from:
        raise RunStatusConflictError(f"Expected {expected_from.value}, found {current.value}")

    assert_valid_transition(current, to_status)

    run.status = to_status.value
    run.error_code = error_code
    run.error_message = error_message
    if current_step is not None:
        run.current_step = current_step
    if final_status is not None:
        run.final_status = final_status

    db.add(run)
    db.commit()
    db.refresh(run)

    publish_event(
        str(run_id),
        {
            "type": "run_status",
            "eventId": f"status:{run_id}:{run.status}",
            "status": run.status,
        },
    )
    return run


def update_run_artifacts(
    db: Session,
    *,
    run_id: uuid.UUID,
    artifacts: dict,
) -> Run:
    run = get_run(db, run_id)
    if not run:
        raise RunNotFoundError(f"Run not found: {run_id}")

    run.artifacts = artifacts

    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_run_progress(
    db: Session,
    *,
    run_id: uuid.UUID,
    current_step: str | None = None,
    final_status: str | None = None,
) -> Run:
    run = get_run(db, run_id)
    if not run:
        raise RunNotFoundError(f"Run not found: {run_id}")

    if current_step is not None:
        run.current_step = current_step
    if final_status is not None:
        run.final_status = final_status

    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finalize_run(
    db: Session,
    *,
    run_id: uuid.UUID,
    artifacts: dict,
    to_status: RunStatus,
    expected_from: RunStatus | None = None,
    current_step: str | None = None,
    final_status: str | None = None,
) -> Run:
    run = get_run(db, run_id)
    if not run:
        raise RunNotFoundError(f"Run not found: {run_id}")

    current = RunStatus(run.status)
    if expected_from is not None and current != expected_from:
        raise RunStatusConflictError(f"Expected {expected_from.value}, found {current.value}")

    assert_valid_transition(current, to_status)

    run.artifacts = artifacts
    run.status = to_status.value
    if current_step is not None:
        run.current_step = current_step
    if final_status is not None:
        run.final_status = final_status

    db.add(run)
    db.commit()
    db.refresh(run)

    publish_event(
        str(run_id),
        {
            "type": "run_status",
            "eventId": f"status:{run_id}:{run.status}",
            "status": run.status,
        },
    )
    return run
