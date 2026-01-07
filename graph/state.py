from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from db.models.run import RunStatus


class RunState(BaseModel):
    """
    RunState is the ONLY object that flows through LangGraph.

    Rules:
    - Serializable (JSON-safe)
    - No DB sessions, engines, or clients
    - Expanded incrementally in later phases (F9+)
    """

    model_config = ConfigDict(extra="allow")

    run_id: UUID
    intent: str
    status: RunStatus
    chain_id: int | None = None
    wallet_address: str | None = None

    # Free-form container for node outputs / intermediate artifacts
    artifacts: Dict[str, Any] = Field(default_factory=dict)
