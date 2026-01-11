from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntentMode(str, Enum):
    QUERY = "QUERY"
    ACTION = "ACTION"
    CLARIFY = "CLARIFY"


class ChatRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    conversation_id: str | None = None
    wallet_address: str | None = None
    chain_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: IntentMode
    assistant_message: str
    questions: list[str] = Field(default_factory=list)
    run_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    next_ui: str | None = None
