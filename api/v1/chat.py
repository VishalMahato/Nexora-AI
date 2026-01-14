from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse
from app.chat.router import route_chat
from db.deps import get_db

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/route", response_model=ChatRouteResponse)
def chat_route(req: ChatRouteRequest, db: Session = Depends(get_db)) -> ChatRouteResponse:
    return route_chat(req, db=db)


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
