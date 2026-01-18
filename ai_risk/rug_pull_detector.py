"""
Rug Pull Detector - Pattern-based detection of rug-pull schemes in DeFi tokens.

This module provides comprehensive rug-pull risk assessment through:
- Pattern-based detection of 12+ rug-pull indicators
- Blacklist management for known malicious contracts
- Temporal analysis for month-wise trend tracking
- Confidence scoring based on data completeness
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import AIRiskConfig, get_ai_risk_config
from .types import RugPullAnalysis

logger = logging.getLogger(__name__)


class RugPullDetector:
    """
    Detects potential rug-pull schemes in DeFi tokens.
    
    Uses pattern matching and heuristics to analyze:
    - Contract characteristics (ownership, mint functions, etc.)
    - Transaction patterns (honeypot detection, blocked sells)
    - Liquidity data (lock duration, concentration)
    """

    # Pattern risk weights
    PATTERN_WEIGHTS = {
        "BLACKLISTED": 1.0,
        "HONEYPOT": 0.95,
        "OWNER_MINT": 0.85,
        "HIDDEN_TRANSFER_FEE": 0.80,
        "BLACKLIST_FUNCTION": 0.75,
        "OWNER_CAN_PAUSE": 0.70,
        "NO_RENOUNCED_OWNERSHIP": 0.60,
        "LOW_LIQUIDITY_LOCK": 0.55,
        "CONCENTRATED_SUPPLY": 0.50,
        "RECENT_DEPLOYMENT": 0.45,
        "NO_VERIFIED_SOURCE": 0.40,
        "PROXY_CONTRACT": 0.35,
        "LARGE_SELL_BLOCKED": 0.90,
        "SUSPICIOUS_SELL_RATIO": 0.65,
    }

    # Human-readable pattern descriptions
    PATTERN_DESCRIPTIONS = {
        "BLACKLISTED": "Token is on known rug-pull blacklist",
        "HONEYPOT": "Honeypot contract - cannot sell tokens",
        "OWNER_MINT": "Owner can mint unlimited tokens",
        "HIDDEN_TRANSFER_FEE": "Hidden transfer fee above 10%",
        "BLACKLIST_FUNCTION": "Contract has blacklist function",
        "OWNER_CAN_PAUSE": "Owner can pause contract operations",
        "NO_RENOUNCED_OWNERSHIP": "Ownership not renounced",
        "LOW_LIQUIDITY_LOCK": "Liquidity lock less than 30 days",
        "CONCENTRATED_SUPPLY": "Top LP holder owns >80% of liquidity",
        "RECENT_DEPLOYMENT": "Contract deployed less than 7 days ago",
        "NO_VERIFIED_SOURCE": "Source code not verified",
        "PROXY_CONTRACT": "Upgradeable proxy contract",
        "LARGE_SELL_BLOCKED": "Large sell transactions blocked",
        "SUSPICIOUS_SELL_RATIO": "Suspicious buy/sell ratio",
    }

    def __init__(self, config: Optional[AIRiskConfig] = None):
        """
        Initialize detector with configuration.
        
        Args:
            config: AIRiskConfig instance (uses default if None)
        """
        self.config = config or get_ai_risk_config()
        self._blacklist: Set[str] = set()
        logger.info(f"RugPullDetector initialized with model version {self.config.rug_pull_model.version}")

    async def analyze_rug_pull_risk(
        self,
        token_address: str,
        liquidity_data: Dict[str, Any],
        transaction_history: List[Dict[str, Any]],
        contract_info: Optional[Dict[str, Any]] = None,
    ) -> RugPullAnalysis:
        """
        Main analysis method. Performs comprehensive rug-pull risk assessment.
        
        Args:
            token_address: EVM contract address (string)
            liquidity_data: Dict with keys:
                - lock_duration_days: int
                - total_liquidity_usd: float
                - top_lp_holder_percentage: float
                - _simulation_failures: int (optional)
            transaction_history: List[Dict] with keys:
                - type: str ("buy", "sell", "transfer")
                - status: str ("success", "failed", "reverted")
                - amount_usd: float (optional)
            contract_info: Optional Dict with keys:
                - is_verified: bool
                - owner: str (address)
                - ownership_renounced: bool
                - has_mint_function: bool
                - has_pause_function: bool
                - has_blacklist_function: bool
                - is_proxy: bool
                - age_days: int
                - transfer_fee_percent: float
        
        Returns:
            RugPullAnalysis with:
            - risk_score: float (0.0-1.0)
            - confidence: float (0.0-1.0)
            - detected_patterns: List[str] (descriptions)
            - key_features: Dict[str, Any]
            - model_version: str
        """
        token_address_lower = token_address.lower()
        
        # Check blacklist first
        if self.is_blacklisted(token_address_lower):
            logger.warning(f"Token {token_address} is blacklisted")
            return RugPullAnalysis(
                risk_score=1.0,
                confidence=1.0,
                detected_patterns=[self.PATTERN_DESCRIPTIONS["BLACKLISTED"]],
                key_features={"blacklisted": True},
                model_version=self.config.rug_pull_model.version,
            )
        
        # Analyze different aspects
        all_patterns: List[str] = []
        all_features: Dict[str, Any] = {}
        risk_scores: List[float] = []
        
        # Liquidity analysis
        if liquidity_data:
            liq_patterns, liq_features = self._analyze_liquidity(liquidity_data)
            all_patterns.extend(liq_patterns)
            all_features.update(liq_features)
            for pattern in liq_patterns:
                if pattern in self.PATTERN_WEIGHTS:
                    risk_scores.append(self.PATTERN_WEIGHTS[pattern])
        
        # Transaction analysis
        if transaction_history:
            tx_patterns, tx_features = self._analyze_transactions(transaction_history)
            all_patterns.extend(tx_patterns)
            all_features.update(tx_features)
            for pattern in tx_patterns:
                if pattern in self.PATTERN_WEIGHTS:
                    risk_scores.append(self.PATTERN_WEIGHTS[pattern])
        
        # Contract analysis
        if contract_info:
            contract_patterns, contract_features = self._analyze_contract(contract_info)
            all_patterns.extend(contract_patterns)
            all_features.update(contract_features)
            for pattern in contract_patterns:
                if pattern in self.PATTERN_WEIGHTS:
                    risk_scores.append(self.PATTERN_WEIGHTS[pattern])
        
        # Calculate final risk score
        if risk_scores:
            # Weighted average with amplification factor
            raw_score = sum(risk_scores) / len(risk_scores)
            risk_score = min(1.0, raw_score * 1.2)  # Apply 1.2x amplification
        else:
            risk_score = 0.0
        
        # Calculate confidence based on data completeness
        confidence = self._calculate_confidence(
            has_liquidity=bool(liquidity_data),
            has_transactions=bool(transaction_history),
            has_contract_info=bool(contract_info),
        )
        
        # Convert pattern codes to descriptions
        detected_pattern_descriptions = [
            self.PATTERN_DESCRIPTIONS.get(p, p) for p in all_patterns
        ]
        
        logger.info(
            f"Analyzed {token_address}: risk_score={risk_score:.2f}, "
            f"confidence={confidence:.2f}, patterns={len(all_patterns)}"
        )
        
        return RugPullAnalysis(
            risk_score=risk_score,
            confidence=confidence,
            detected_patterns=detected_pattern_descriptions,
            key_features=all_features,
            model_version=self.config.rug_pull_model.version,
        )

    def is_blacklisted(self, contract_address: str) -> bool:
        """
        Check if address is on the blacklist.
        
        Args:
            contract_address: Address to check
            
        Returns:
            True if address is blacklisted
        """
        return contract_address.lower() in self._blacklist

    def add_to_blacklist(self, contract_address: str) -> None:
        """
        Add address to blacklist.
        
        Args:
            contract_address: Address to add
        """
        address_lower = contract_address.lower()
        self._blacklist.add(address_lower)
        logger.info(f"Added {contract_address} to blacklist")

    def load_blacklist(self, addresses: Optional[List[str]]) -> None:
        """
        Bulk load addresses into blacklist.
        
        Args:
            addresses: List of addresses to add
        """
        if addresses:
            for addr in addresses:
                self._blacklist.add(addr.lower())
            logger.info(f"Loaded {len(addresses)} addresses into blacklist")

    async def analyze_temporal_patterns(
        self,
        token_address: str,
        monthly_snapshots: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze temporal patterns over multiple months.
        
        Args:
            token_address: Token address
            monthly_snapshots: List of monthly data with keys:
                - liquidity_usd: float
                - top_holder_percentage: float
                - volume_usd: float
        
        Returns:
            Dict with temporal_analysis, red_flags, timeline_events
        """
        if len(monthly_snapshots) < 2:
            return {
                "status": "insufficient_data",
                "message": "Need at least 2 months of data",
                "red_flags": [],
                "timeline_events": [],
            }
        
        liquidity_trend = self._analyze_liquidity_trend(monthly_snapshots)
        holder_trend = self._analyze_holder_trend(monthly_snapshots)
        volume_trend = self._analyze_volume_trend(monthly_snapshots)
        
        red_flags = []
        timeline_events = []
        
        # Check for sudden liquidity drain
        if liquidity_trend.get("max_drop_percent", 0) > 50:
            red_flags.append("Sudden liquidity drain detected (>50% drop)")
            timeline_events.append({
                "type": "LIQUIDITY_DRAIN",
                "severity": "HIGH",
                "month": liquidity_trend.get("worst_month"),
            })
        
        # Check for increasing holder concentration
        if holder_trend.get("trend") == "increasing" and holder_trend.get("final_concentration", 0) > 0.8:
            red_flags.append("Increasing holder concentration above 80%")
            timeline_events.append({
                "type": "CONCENTRATION_INCREASE",
                "severity": "MEDIUM",
            })
        
        return {
            "status": "ok",
            "liquidity_trend": liquidity_trend,
            "holder_trend": holder_trend,
            "volume_trend": volume_trend,
            "red_flags": red_flags,
            "timeline_events": timeline_events,
        }

    def _analyze_liquidity(
        self, liquidity_data: Dict[str, Any]
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Analyze liquidity patterns.
        
        Returns:
            Tuple of (detected_patterns, features)
        """
        patterns = []
        features = {}
        
        lock_days = liquidity_data.get("lock_duration_days", 0)
        features["liquidity_lock_days"] = lock_days
        if lock_days < 30:
            patterns.append("LOW_LIQUIDITY_LOCK")
        
        total_liq = liquidity_data.get("total_liquidity_usd", 0)
        features["total_liquidity_usd"] = total_liq
        
        lp_concentration = liquidity_data.get("top_lp_holder_percentage", 0)
        features["lp_concentration"] = lp_concentration
        if lp_concentration > 0.8:
            patterns.append("CONCENTRATED_SUPPLY")
        
        # Check for simulation failures indicating issues
        sim_failures = liquidity_data.get("_simulation_failures", 0)
        if sim_failures > 0:
            features["low_liquidity_warning"] = True
        
        return patterns, features

    def _analyze_transactions(
        self, transaction_history: List[Dict[str, Any]]
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Analyze transaction patterns.
        
        Returns:
            Tuple of (detected_patterns, features)
        """
        patterns = []
        features = {}
        
        total_sells = 0
        failed_sells = 0
        total_buys = 0
        large_blocked_sells = 0
        
        for tx in transaction_history:
            tx_type = tx.get("type", "").lower()
            status = tx.get("status", "").lower()
            amount = tx.get("amount_usd", 0)
            
            if tx_type == "sell":
                total_sells += 1
                if status in ("failed", "reverted"):
                    failed_sells += 1
                    if amount > 1000:
                        large_blocked_sells += 1
            elif tx_type == "buy":
                total_buys += 1
        
        features["total_sells"] = total_sells
        features["total_buys"] = total_buys
        features["failed_sells"] = failed_sells
        
        # Honeypot detection: >50% failed sells
        if total_sells > 0 and (failed_sells / total_sells) > 0.5:
            patterns.append("HONEYPOT")
        
        # Large sell blocked detection
        if large_blocked_sells > 2:
            patterns.append("LARGE_SELL_BLOCKED")
        
        # Suspicious sell ratio: many buys but almost no sells
        if total_buys > 10 and total_sells < total_buys * 0.1:
            patterns.append("SUSPICIOUS_SELL_RATIO")
            features["suspicious_sell_ratio"] = True
        
        return patterns, features

    def _analyze_contract(
        self, contract_info: Dict[str, Any]
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Analyze contract metadata.
        
        Returns:
            Tuple of (detected_patterns, features)
        """
        patterns = []
        features = {}
        
        # Source verification
        is_verified = contract_info.get("is_verified", False)
        features["source_verified"] = is_verified
        if not is_verified:
            patterns.append("NO_VERIFIED_SOURCE")
        
        # Ownership
        owner = contract_info.get("owner")
        ownership_renounced = contract_info.get("ownership_renounced", False)
        features["ownership_renounced"] = ownership_renounced
        
        if owner and not ownership_renounced:
            patterns.append("NO_RENOUNCED_OWNERSHIP")
        
        # Mint function
        has_mint = contract_info.get("has_mint_function", False)
        features["has_mint_function"] = has_mint
        if has_mint and not ownership_renounced:
            patterns.append("OWNER_MINT")
        
        # Pause function
        has_pause = contract_info.get("has_pause_function", False)
        features["has_pause_function"] = has_pause
        if has_pause:
            patterns.append("OWNER_CAN_PAUSE")
        
        # Blacklist function
        has_blacklist = contract_info.get("has_blacklist_function", False)
        features["has_blacklist_function"] = has_blacklist
        if has_blacklist:
            patterns.append("BLACKLIST_FUNCTION")
        
        # Proxy contract
        is_proxy = contract_info.get("is_proxy", False)
        features["is_proxy"] = is_proxy
        if is_proxy:
            patterns.append("PROXY_CONTRACT")
        
        # Contract age
        age_days = contract_info.get("age_days", 0)
        features["contract_age_days"] = age_days
        if age_days < 7:
            patterns.append("RECENT_DEPLOYMENT")
        
        # Transfer fee
        transfer_fee = contract_info.get("transfer_fee_percent", 0)
        features["transfer_fee_percent"] = transfer_fee
        if transfer_fee > 10:
            patterns.append("HIDDEN_TRANSFER_FEE")
        
        return patterns, features

    def _calculate_confidence(
        self,
        has_liquidity: bool,
        has_transactions: bool,
        has_contract_info: bool,
    ) -> float:
        """
        Calculate confidence score based on data completeness.
        
        Returns:
            Confidence score between 0.5 and 1.0
        """
        confidence = 0.5  # Base confidence
        
        if has_liquidity:
            confidence += 0.15
        if has_transactions:
            confidence += 0.20
        if has_contract_info:
            confidence += 0.15
        
        return min(1.0, confidence)

    def _analyze_liquidity_trend(
        self, snapshots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze liquidity trends over time."""
        values = [s.get("liquidity_usd", 0) for s in snapshots]
        if not values or len(values) < 2:
            return {"trend": "unknown"}
        
        changes = []
        max_drop = 0
        worst_month = None
        
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                change = (values[i] - values[i - 1]) / values[i - 1] * 100
                changes.append(change)
                if change < max_drop:
                    max_drop = change
                    worst_month = i
        
        avg_change = sum(changes) / len(changes) if changes else 0
        
        return {
            "monthly_changes": changes,
            "average_change": avg_change,
            "max_drop_percent": abs(max_drop) if max_drop < 0 else 0,
            "worst_month": worst_month,
            "trend": "decreasing" if avg_change < -10 else "increasing" if avg_change > 10 else "stable",
        }

    def _analyze_holder_trend(
        self, snapshots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze holder concentration trends."""
        values = [s.get("top_holder_percentage", 0) for s in snapshots]
        if not values or len(values) < 2:
            return {"trend": "unknown"}
        
        initial = values[0]
        final = values[-1]
        
        return {
            "initial_concentration": initial,
            "final_concentration": final,
            "change": final - initial,
            "trend": "increasing" if final > initial + 0.1 else "decreasing" if final < initial - 0.1 else "stable",
        }

    def _analyze_volume_trend(
        self, snapshots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze trading volume trends."""
        values = [s.get("volume_usd", 0) for s in snapshots]
        if not values or len(values) < 2:
            return {"trend": "unknown"}
        
        avg_volume = sum(values) / len(values)
        
        return {
            "average_volume": avg_volume,
            "first_month": values[0],
            "last_month": values[-1],
            "trend": "increasing" if values[-1] > values[0] * 1.5 else "decreasing" if values[-1] < values[0] * 0.5 else "stable",
        }
