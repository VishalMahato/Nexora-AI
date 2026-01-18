from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RugPullSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    severity: str = Field(pattern=r"^(LOW|MED|HIGH)$")
    detail: str


class RugPullAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flagged: bool
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    summary: str
    signals: list[RugPullSignal] = Field(default_factory=list)
