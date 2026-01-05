from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=5000)
    walletAddress: str = Field(..., min_length=3, max_length=64)
    chainId: int = Field(..., ge=1)


class RunCreateResponse(BaseModel):
    runId: UUID
    status: str


class RunResponse(BaseModel):
    id: UUID
    intent: str
    wallet_address: str
    chain_id: int
    status: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class GetRunResponse(BaseModel):
    run: RunResponse
