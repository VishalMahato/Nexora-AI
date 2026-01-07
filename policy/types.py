# policy/types.py
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class DecisionAction(str, Enum):
    ALLOW = "ALLOW"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    BLOCK = "BLOCK"


class Severity(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


class PolicyCheckResult(BaseModel):
    id: str
    title: str
    status: CheckStatus
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PolicyResult(BaseModel):
    checks: List[PolicyCheckResult] = Field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)


class Decision(BaseModel):
    action: DecisionAction
    risk_score: int = Field(ge=0, le=100)
    severity: Severity
    summary: str
    reasons: List[str] = Field(default_factory=list)
