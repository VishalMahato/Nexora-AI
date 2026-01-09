from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TxRequest(BaseModel):
    chainId: int
    to: str
    data: str = "0x"
    valueWei: str | None = None


class RunExecuteResponse(BaseModel):
    ok: bool = True
    runId: UUID
    status: str
    tx_request: TxRequest


class TxSubmittedRequest(BaseModel):
    txHash: str = Field(..., min_length=66, max_length=66)
    submittedBy: Literal["walletconnect", "metamask", "manual"]


class RunTxSubmittedResponse(BaseModel):
    ok: bool = True
    runId: UUID
    status: str
    txHash: str
