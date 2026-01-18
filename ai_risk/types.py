"""Data types for AI Risk Analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utcnow() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class RiskDecision(Enum):
    """Risk decision outcome."""
    APPROVE = "APPROVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCK = "BLOCK"


class RiskSeverity(Enum):
    """Risk severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RugPullAnalysis:
    """Result of rug pull analysis."""
    risk_score: float  # 0.0-1.0
    confidence: float  # 0.0-1.0
    detected_patterns: List[str] = field(default_factory=list)
    key_features: Dict[str, Any] = field(default_factory=dict)
    model_version: str = "1.0.0"
    timestamp: datetime = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "detected_patterns": self.detected_patterns,
            "key_features": self.key_features,
            "model_version": self.model_version,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class LiquidityAnalysis:
    """Liquidity-specific analysis result."""
    total_liquidity_usd: float
    lock_duration_days: int
    top_holder_percentage: float
    is_locked: bool
    risk_score: float


@dataclass
class TokenMetrics:
    """Token metadata and metrics."""
    token_address: str
    name: Optional[str] = None
    symbol: Optional[str] = None
    decimals: Optional[int] = None
    total_supply: Optional[float] = None
    holder_count: Optional[int] = None
    age_days: Optional[int] = None
