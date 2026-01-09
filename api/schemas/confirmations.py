from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class RunPollTxResponse(BaseModel):
    ok: bool = True
    runId: UUID
    status: str
    mined: bool
    tx_hash: str
    receipt: dict[str, Any] | None
