# api/v1/run_confirmations.py
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas.confirmations import RunPollTxResponse
from chain.client import ChainClient
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


@router.post("/{run_id}/poll_tx", response_model=RunPollTxResponse)
def poll_tx(run_id: UUID, db: Session = Depends(get_db)) -> RunPollTxResponse:
    logger.info("poll_tx called")

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if RunStatus(run.status) != RunStatus.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot poll tx from status={run.status}",
        )

    artifacts = run.artifacts or {}
    tx_hash = artifacts.get("tx_hash")
    if not tx_hash:
        raise HTTPException(status_code=400, detail="No tx_hash recorded for run")

    poll_step = log_step(
        db,
        run_id=run_id,
        step_name="TX_POLL",
        status="STARTED",
        input={"tx_hash": tx_hash},
        agent="API",
    )

    client = ChainClient()
    receipt = client.get_tx_receipt(
        db=db,
        run_id=run_id,
        step_id=poll_step.id,
        chain_id=run.chain_id,
        tx_hash=tx_hash,
    )

    if receipt is None:
        log_step(
            db,
            run_id=run_id,
            step_name="TX_POLL",
            status="DONE",
            output={"mined": False},
            agent="API",
        )
        return RunPollTxResponse(
            ok=True,
            runId=run_id,
            status=run.status,
            mined=False,
            tx_hash=tx_hash,
            receipt=None,
        )

    artifacts = dict(artifacts)
    artifacts["tx_receipt"] = receipt

    raw_status = receipt.get("status")
    status_int: int | None = None
    if isinstance(raw_status, int):
        status_int = raw_status
    elif isinstance(raw_status, str):
        try:
            status_int = int(raw_status, 16) if raw_status.startswith("0x") else int(raw_status)
        except ValueError:
            status_int = None

    new_status = RunStatus.CONFIRMED if status_int == 1 else RunStatus.REVERTED

    try:
        finalize_run(
            db,
            run_id=run_id,
            artifacts=artifacts,
            to_status=new_status,
            expected_from=RunStatus.SUBMITTED,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (RunStatusConflictError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))

    log_step(
        db,
        run_id=run_id,
        step_name="TX_POLL",
        status="DONE",
        output={"mined": True, "status": new_status.value},
        agent="API",
    )

    log_step(
        db,
        run_id=run_id,
        step_name="TX_CONFIRMED" if new_status == RunStatus.CONFIRMED else "TX_REVERTED",
        status="DONE",
        output={"tx_hash": tx_hash, "receipt": receipt},
        agent="API",
    )

    return RunPollTxResponse(
        ok=True,
        runId=run_id,
        status=new_status.value,
        mined=True,
        tx_hash=tx_hash,
        receipt=receipt,
    )
