from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntentMode(str, Enum):
    QUERY = "QUERY"
    ACTION = "ACTION"
    CLARIFY = "CLARIFY"
    GENERAL = "GENERAL"


class ChatRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    conversation_id: str | None = None
    wallet_address: str | None = None
    chain_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: IntentMode
    intent_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    slots: dict[str, Any] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    reason: str | None = None


class RunRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str | None = None
    fetch_url: str | None = None


class ChatRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: IntentMode
    assistant_message: str
    questions: list[str] = Field(default_factory=list)
    run_id: str | None = None
    run_ref: RunRef | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    next_ui: str | None = None
    classification: IntentClassification | None = None
    conversation_id: str | None = None
    pending: bool = False
    pending_slots: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
