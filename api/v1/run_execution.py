# api/v1/run_execution.py
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.deps import get_db
from db.models.run import RunStatus
from db.repos.runs_repo import (
    RunNotFoundError,
    RunStatusConflictError,
    get_run,
    update_run_status,
)
from graph.graph import run_graph
from graph.state import RunState

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/runs", tags=["runs"])

@router.post("/{run_id}/start")


@router.post("/{run_id}/start")
def start_run(run_id: UUID, db: Session = Depends(get_db)):
    """
    Minimal synchronous execution:
    CREATED -> RUNNING -> AWAITING_APPROVAL (on success)
    CREATED -> RUNNING -> FAILED (on exception)

    Note:
    run_id context is handled by middleware (no manual set_run_id here).
    """
    logger.info("start_run called")

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Only allow starting from CREATED
    if RunStatus(run.status) != RunStatus.CREATED:
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot be started from status={run.status}",
        )

    # Transition to RUNNING (optimistic lock via expected_from)
    try:
        run = update_run_status(
            db,
            run_id=run_id,
            to_status=RunStatus.RUNNING,
            expected_from=RunStatus.CREATED,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=RunStatus.RUNNING.value,  # RunState.status is str
        )

        final_state = run_graph(db, state)

        # FSM-correct success transition from RUNNING
        update_run_status(
            db,
            run_id=run_id,
            to_status=RunStatus.AWAITING_APPROVAL,
            expected_from=RunStatus.RUNNING,
        )

        artifacts = (
            final_state.artifacts
            if hasattr(final_state, "artifacts")
            else final_state.get("artifacts", {})
        )

        return {
            "ok": True,
            "runId": str(run.id),
            "status": RunStatus.AWAITING_APPROVAL.value,
            "artifacts": artifacts,
        }

    except Exception as e:
        # Mark failed (FSM-correct)
        try:
            update_run_status(
                db,
                run_id=run_id,
                to_status=RunStatus.FAILED,
                expected_from=RunStatus.RUNNING,
                error_code="GRAPH_EXECUTION_ERROR",
                error_message=f"{type(e).__name__}: {e}",
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail=f"Run execution failed: {type(e).__name__}: {e}",
        )
