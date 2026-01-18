"""Configuration for AI Risk Analysis."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass
class RiskThresholds:
    """Thresholds for risk decisions."""
    approve_max: float = 0.3  # risk_score <= 0.3 → APPROVE
    review_max: float = 0.7   # 0.3 < risk_score <= 0.7 → NEEDS_REVIEW
    # risk_score > 0.7 → BLOCK


@dataclass
class ModelConfig:
    """Configuration for a risk model."""
    version: str = "1.0.0"
    model_path: Optional[str] = None
    threshold: float = 0.7
    fallback_enabled: bool = True


@dataclass
class DataSourceConfig:
    """Configuration for external data sources."""
    etherscan_api_key: Optional[str] = None
    cache_ttl_seconds: int = 300
    birdeye_api_key: Optional[str] = None
    solscan_api_key: Optional[str] = None


@dataclass
class AIRiskConfig:
    """Main configuration for AI Risk Analysis."""
    enabled: bool = True
    thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    rug_pull_model: ModelConfig = field(default_factory=ModelConfig)
    liquidity_model: ModelConfig = field(default_factory=ModelConfig)
    data_sources: DataSourceConfig = field(default_factory=DataSourceConfig)
    parallel_analysis: bool = True
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "AIRiskConfig":
        """Load configuration from environment variables."""
        enabled = os.getenv("AI_RISK_ENABLED", "true").lower() == "true"
        
        thresholds = RiskThresholds(
            approve_max=float(os.getenv("AI_RISK_APPROVE_THRESHOLD", "0.3")),
            review_max=float(os.getenv("AI_RISK_REVIEW_THRESHOLD", "0.7")),
        )
        
        rug_pull_model = ModelConfig(
            version=os.getenv("AI_RISK_RUG_PULL_MODEL_VERSION", "1.0.0"),
            threshold=float(os.getenv("AI_RISK_RUG_PULL_THRESHOLD", "0.7")),
        )
        
        liquidity_model = ModelConfig(
            version=os.getenv("AI_RISK_LIQUIDITY_MODEL_VERSION", "1.0.0"),
            threshold=float(os.getenv("AI_RISK_LIQUIDITY_THRESHOLD", "0.7")),
        )
        
        data_sources = DataSourceConfig(
            etherscan_api_key=os.getenv("ETHERSCAN_API_KEY"),
            cache_ttl_seconds=int(os.getenv("AI_RISK_CACHE_TTL", "300")),
            birdeye_api_key=os.getenv("BIRDEYE_API_KEY"),
            solscan_api_key=os.getenv("SOLSCAN_API_KEY"),
        )
        
        return cls(
            enabled=enabled,
            thresholds=thresholds,
            rug_pull_model=rug_pull_model,
            liquidity_model=liquidity_model,
            data_sources=data_sources,
            timeout_seconds=float(os.getenv("AI_RISK_TIMEOUT", "30.0")),
        )


@lru_cache(maxsize=1)
def get_ai_risk_config() -> AIRiskConfig:
    """Get cached AI Risk configuration."""
    return AIRiskConfig.from_env()
