from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["LOW", "MED", "HIGH"]
    title: str
    detail: str


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    assumptions: list[str] = Field(default_factory=list)
    why_safe: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str
    step_name: str
    version: int = 1
    status: Literal["OK", "WARN", "BLOCK", "ERROR"]
    output: Dict[str, Any]
    explanation: Explanation
    confidence: float | None = Field(default=None, ge=0, le=1)
    sources: list[str] = Field(default_factory=list)
    errors: list[str] | None = None
    created_at: datetime = Field(default_factory=_utcnow)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
