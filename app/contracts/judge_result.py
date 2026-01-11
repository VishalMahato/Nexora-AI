from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class JudgeVerdict(str, Enum):
    PASS = "PASS"
    NEEDS_REWORK = "NEEDS_REWORK"
    BLOCK = "BLOCK"


class JudgeIssueSeverity(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


class JudgeIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: JudgeIssueSeverity
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)


class JudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: JudgeVerdict  
    reasoning_summary: str
    issues: List[JudgeIssue] = Field(default_factory=list)
