from __future__ import annotations

from uuid import UUID
import uuid
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

# from db.models.run import RunStatus

from db.deps import get_db
from db.repos.runs_repo import get_run
from db.repos.run_steps_repo import list_steps_for_run
from db.repos.tool_calls_repo import list_tool_calls_for_run
from app.services.runs_service import create_run_with_audit
from app.services.run_events import subscribe, unsubscribe

from api.schemas.runs import (
    RunCreateRequest,
    RunCreateResponse,
    GetRunResponse,
    RunResponse,
    ToolCallRead,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _validate_wallet_address(wallet: str) -> None:
    # MVP-light validation (don’t over-engineer):
    # - must start with 0x
    # - max len 64 (as per schema)
    if not wallet.startswith("0x"):
        raise HTTPException(status_code=422, detail="walletAddress must start with '0x'")


def _build_run_response(
    *,
    run,
    include_artifacts: bool,
    ) -> GetRunResponse:
    return GetRunResponse(
        run=RunResponse(
            id=run.id,
            intent=run.intent,
            wallet_address=run.wallet_address,
            chain_id=run.chain_id,
            status=run.status,
            current_step=getattr(run, "current_step", None),
            final_status=getattr(run, "final_status", None),
            error_code=run.error_code,
            error_message=run.error_message,
            artifacts=run.artifacts if include_artifacts else None,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
    )


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.post("", response_model=RunCreateResponse)
def create_run_endpoint(payload: RunCreateRequest, db: Session = Depends(get_db)) -> RunCreateResponse:
    _validate_wallet_address(payload.walletAddress)

    run_id = create_run_with_audit(
        db=db,
        intent=payload.intent,
        wallet_address=payload.walletAddress,
        chain_id=payload.chainId,
        agent="API",
        tool_name="api_create_run",
    )

    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunCreateResponse(runId=run.id, status=run.status)


@router.get("/{run_id}", response_model=GetRunResponse, response_model_exclude_none=False)
def get_run_endpoint(
    run_id: UUID,
    includeArtifacts: bool = Query(False, description="Include run artifacts in response"),
    db: Session = Depends(get_db),
) -> GetRunResponse:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return _build_run_response(run=run, include_artifacts=includeArtifacts)


@router.get("/{run_id}/status", response_model=GetRunResponse, response_model_exclude_none=False)
def get_run_status_endpoint(run_id: UUID, db: Session = Depends(get_db)) -> GetRunResponse:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return _build_run_response(run=run, include_artifacts=False)


@router.get("/{run_id}/details", response_model=GetRunResponse, response_model_exclude_none=False)
def get_run_details_endpoint(run_id: UUID, db: Session = Depends(get_db)) -> GetRunResponse:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return _build_run_response(run=run, include_artifacts=True)


@router.get("/{run_id}/events")
def stream_run_events(run_id: UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    def event_stream():
        steps = list_steps_for_run(db, run_id=run_id)
        for step in steps:
            output = step.output if isinstance(step.output, dict) else {}
            summary = output.get("summary")
            timestamp = (step.ended_at or step.started_at) or datetime.now(timezone.utc)
            yield _sse_event(
                {
                    "type": "run_step",
                    "eventId": f"step:{step.id}",
                    "runId": str(run_id),
                    "step": step.step_name,
                    "status": step.status,
                    "summary": summary,
                    "timestamp": timestamp.isoformat(),
                    "replay": True,
                }
            )

        yield _sse_event(
            {
                "type": "run_status",
                "eventId": f"status:{run_id}:{run.status}",
                "runId": str(run_id),
                "status": run.status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "replay": True,
            }
        )

        queue = subscribe(str(run_id))
        try:
            while True:
                event = queue.get()
                yield _sse_event(event)
        finally:
            unsubscribe(str(run_id), queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get(
    "/{run_id}/tool-calls",
    response_model=list[ToolCallRead],
)
def list_run_tool_calls(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run = get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return list_tool_calls_for_run(db, run_id=run_id)

@router.get("/{run_id}/tools", response_model=list[ToolCallRead])
def list_run_tools_alias(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    return list_run_tool_calls(run_id=run_id, db=db)
