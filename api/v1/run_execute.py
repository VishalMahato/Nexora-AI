# api/v1/run_execute.py
from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas.execute import RunExecuteResponse, RunTxSubmittedResponse, TxSubmittedRequest
from db.deps import get_db
from db.models.run import RunStatus
from db.repos.runs_repo import (
    RunNotFoundError,
    RunStatusConflictError,
    finalize_run,
    get_run,
)
from db.repos.run_steps_repo import log_step

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

_TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")


def _is_tx_hash(value: str) -> bool:
    return bool(_TX_HASH_RE.fullmatch(value or ""))


@router.post("/{run_id}/execute", response_model=RunExecuteResponse)
def execute_run(run_id: UUID, db: Session = Depends(get_db)) -> RunExecuteResponse:
    logger.info("execute_run called")

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if RunStatus(run.status) != RunStatus.APPROVED_READY:
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot be executed from status={run.status}",
        )

    artifacts = run.artifacts or {}
    tx_plan = artifacts.get("tx_plan") or {}
    candidates = tx_plan.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=400, detail="No transaction candidates to execute")

    candidate = candidates[0]
    tx_request = {
        "chainId": candidate.get("chainId") or candidate.get("chain_id") or run.chain_id,
        "to": candidate.get("to"),
        "data": candidate.get("data") or "0x",
        "valueWei": candidate.get("valueWei") or candidate.get("value_wei") or candidate.get("value"),
    }

    log_step(
        db,
        run_id=run_id,
        step_name="EXECUTE_PREP",
        status="STARTED",
        input={"tx_request": tx_request},
        agent="API",
    )

    log_step(
        db,
        run_id=run_id,
        step_name="EXECUTE_PREP",
        status="DONE",
        output={"status": run.status},
        agent="API",
    )

    return RunExecuteResponse(
        ok=True,
        runId=run_id,
        status=run.status,
        tx_request=tx_request,
    )


@router.post("/{run_id}/tx_submitted", response_model=RunTxSubmittedResponse)
def tx_submitted(
    run_id: UUID,
    payload: TxSubmittedRequest,
    db: Session = Depends(get_db),
) -> RunTxSubmittedResponse:
    logger.info("tx_submitted called")

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if RunStatus(run.status) != RunStatus.APPROVED_READY:
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot accept submission from status={run.status}",
        )

    if not _is_tx_hash(payload.txHash):
        raise HTTPException(status_code=400, detail="Invalid txHash")

    log_step(
        db,
        run_id=run_id,
        step_name="TX_SUBMITTED",
        status="STARTED",
        input={
            "tx_hash": payload.txHash,
            "submitted_by": payload.submittedBy,
        },
        agent="API",
    )

    artifacts = dict(run.artifacts or {})
    artifacts["tx_hash"] = payload.txHash

    try:
        finalize_run(
            db,
            run_id=run_id,
            artifacts=artifacts,
            to_status=RunStatus.SUBMITTED,
            expected_from=RunStatus.APPROVED_READY,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))

    log_step(
        db,
        run_id=run_id,
        step_name="TX_SUBMITTED",
        status="DONE",
        output={"status": RunStatus.SUBMITTED.value, "tx_hash": payload.txHash},
        agent="API",
    )

    return RunTxSubmittedResponse(
        ok=True,
        runId=run_id,
        status=RunStatus.SUBMITTED.value,
        txHash=payload.txHash,
    )
