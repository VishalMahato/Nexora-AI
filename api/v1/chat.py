from __future__ import annotations

from fastapi import APIRouter

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse
from app.chat.router import route_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/route", response_model=ChatRouteResponse)
def chat_route(req: ChatRouteRequest) -> ChatRouteResponse:
    return route_chat(req)
