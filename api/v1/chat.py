from __future__ import annotations

import json

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse, IntentMode
from app.chat.router import route_chat
from db.deps import get_db
from db.session import SessionLocal
from app.services.runs_service import start_run_sync

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/route", response_model=ChatRouteResponse)
def chat_route(
    req: ChatRouteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ChatRouteResponse:
    metadata = dict(req.metadata or {})
    if "defer_start" not in metadata:
        metadata["defer_start"] = True
        req = req.model_copy(update={"metadata": metadata})

    resp = route_chat(req, db=db)
    if (
        metadata.get("defer_start")
        and resp.mode == IntentMode.ACTION
        and resp.run_id
    ):
        background_tasks.add_task(_start_run_background, resp.run_id)
    return resp


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=True)}\n\n"


@router.post("/route/stream")
def chat_route_stream(req: ChatRouteRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    def event_stream():
        yield _sse_event({"type": "status", "status": "processing"})
        response = route_chat(req, db=db)
        message = response.assistant_message or ""
        for i in range(0, len(message), 48):
            chunk = message[i : i + 48]
            yield _sse_event({"type": "delta", "content": chunk})
        yield _sse_event({"type": "final", "response": response.model_dump()})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _start_run_background(run_id: str) -> None:
    db = SessionLocal()
    try:
        start_run_sync(db=db, run_id=UUID(run_id))
    except Exception as exc:
        logger.warning("background run start failed: %s", exc)
    finally:
        db.close()
