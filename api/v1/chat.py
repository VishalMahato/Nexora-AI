from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse
from app.chat.router import route_chat
from db.deps import get_db

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/route", response_model=ChatRouteResponse)
def chat_route(req: ChatRouteRequest, db: Session = Depends(get_db)) -> ChatRouteResponse:
    return route_chat(req, db=db)
