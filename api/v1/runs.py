from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas.runs import RunCreateRequest, RunCreateResponse, GetRunResponse, RunResponse
from app.domain.run_status import RunStatus
from db.deps import get_db
from db.repos.runs_repo import create_run, get_run


router = APIRouter(prefix="/runs", tags=["runs"])


def _validate_wallet_address(wallet: str) -> None:
    # MVP-light validation (don’t over-engineer):
    # - must start with 0x
    # - max len 64 (as per schema)
    if not wallet.startswith("0x"):
        raise HTTPException(status_code=422, detail="walletAddress must start with '0x'")


@router.post("", response_model=RunCreateResponse)
def create_run_endpoint(payload: RunCreateRequest, db: Session = Depends(get_db)) -> RunCreateResponse:
    _validate_wallet_address(payload.walletAddress)

    run = create_run(
        db,
        intent=payload.intent,
        wallet_address=payload.walletAddress,
        chain_id=payload.chainId,
    )
    return RunCreateResponse(runId=run.id, status=run.status)


@router.get("/{run_id}", response_model=GetRunResponse)
def get_run_endpoint(run_id: UUID, db: Session = Depends(get_db)) -> GetRunResponse:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return GetRunResponse(
        run=RunResponse(
            id=run.id,
            intent=run.intent,
            wallet_address=run.wallet_address,
            chain_id=run.chain_id,
            status=run.status,
            error_code=run.error_code,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
    )
