# api/v1/run_execution.py
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.deps import get_db
from db.repos.runs_repo import RunNotFoundError, RunStatusConflictError
from app.services.runs_service import start_run_sync, resume_run_sync
from api.schemas.runs import RunResumeRequest, RunResumeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

@router.post("/{run_id}/start")
def start_run(run_id: UUID, db: Session = Depends(get_db)):
    """
    Minimal synchronous execution:
    CREATED -> RUNNING -> AWAITING_APPROVAL (on success)
    CREATED -> RUNNING -> FAILED (on exception)
    CREATED -> RUNNING -> PAUSED (noop/needs_input)

    With policy engine (F12):
    CREATED -> RUNNING -> BLOCKED (if decision.action == BLOCK)

    Note:
    run_id context is handled by middleware (no manual set_run_id here).
    """
    logger.info("start_run called")

    try:
        return start_run_sync(db=db, run_id=run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{run_id}/resume", response_model=RunResumeResponse)
def resume_run(
    run_id: UUID,
    payload: RunResumeRequest,
    db: Session = Depends(get_db),
) -> RunResumeResponse:
    logger.info("resume_run called")

    try:
        return resume_run_sync(
            db=db,
            run_id=run_id,
            answers=payload.answers,
            metadata=payload.metadata,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
