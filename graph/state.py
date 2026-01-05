from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field


class RunState(BaseModel):
    """
    RunState is the ONLY object that flows through LangGraph.

    Rules:
    - Serializable (JSON-safe)
    - No DB sessions, engines, or clients
    - Expanded incrementally in later phases (F9+)
    """

    run_id: UUID
    intent: str
    status: str

    # Free-form container for node outputs / intermediate artifacts
    artifacts: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = False  # allow mutation by nodes
