# api/schemas/approval.py
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RunApproveRequest(BaseModel):
    reviewer: Optional[str] = Field(default=None, max_length=128)
    notes: Optional[str] = Field(default=None, max_length=2000)


class RunRejectRequest(BaseModel):
    reviewer: Optional[str] = Field(default=None, max_length=128)
    reason: Optional[str] = Field(default=None, max_length=2000)


class RunDecisionResponse(BaseModel):
    ok: bool = True
    runId: UUID
    status: str
