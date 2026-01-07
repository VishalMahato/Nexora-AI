# api/v1/run_approval.py
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas.approval import RunApproveRequest, RunRejectRequest
from db.deps import get_db
from db.models.run import RunStatus
from db.repos.runs_repo import (
    RunNotFoundError,
    RunStatusConflictError,
    get_run,
    update_run_status,
)
from db.repos.run_steps_repo import log_step

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("/{run_id}/approve")
def approve_run(
    run_id: UUID,
    payload: RunApproveRequest | None = None,
    db: Session = Depends(get_db),
):
    logger.info("approve_run called")

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if RunStatus(run.status) != RunStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot be approved from status={run.status}",
        )

    # audit START
    log_step(
        db,
        run_id=run_id,
        step_name="HUMAN_APPROVAL",
        status="STARTED",
        input={
            "action": "APPROVE",
            "reviewer": (payload.reviewer if payload else None),
            "notes": (payload.notes if payload else None),
        },
        agent="API",
    )

    try:
        update_run_status(
            db,
            run_id=run_id,
            to_status=RunStatus.APPROVED_READY,
            expected_from=RunStatus.AWAITING_APPROVAL,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))

    # audit DONE
    log_step(
        db,
        run_id=run_id,
        step_name="HUMAN_APPROVAL",
        status="DONE",
        output={"status": RunStatus.APPROVED_READY.value},
        agent="API",
    )

    return {"ok": True, "runId": str(run_id), "status": RunStatus.APPROVED_READY.value}


@router.post("/{run_id}/reject")
def reject_run(
    run_id: UUID,
    payload: RunRejectRequest | None = None,
    db: Session = Depends(get_db),
):
    logger.info("reject_run called")

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if RunStatus(run.status) != RunStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot be rejected from status={run.status}",
        )

    # audit START
    log_step(
        db,
        run_id=run_id,
        step_name="HUMAN_APPROVAL",
        status="STARTED",
        input={
            "action": "REJECT",
            "reviewer": (payload.reviewer if payload else None),
            "reason": (payload.reason if payload else None),
        },
        agent="API",
    )

    try:
        update_run_status(
            db,
            run_id=run_id,
            to_status=RunStatus.REJECTED,
            expected_from=RunStatus.AWAITING_APPROVAL,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))

    # audit DONE
    log_step(
        db,
        run_id=run_id,
        step_name="HUMAN_APPROVAL",
        status="DONE",
        output={"status": RunStatus.REJECTED.value},
        agent="API",
    )

    return {"ok": True, "runId": str(run_id), "status": RunStatus.REJECTED.value}
