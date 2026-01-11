from __future__ import annotations

from app.chat.contracts import ChatRouteRequest, ChatRouteResponse, IntentMode


def route_chat(req: ChatRouteRequest) -> ChatRouteResponse:
    return ChatRouteResponse(
        mode=IntentMode.CLARIFY,
        assistant_message="I can help with that. What would you like to do?",
        questions=["What action do you want to perform (e.g., swap, check balance)?"],
        data={"stub": True},
    )
