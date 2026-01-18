"""Tests for the Rug Pull Detector module."""
import pytest
from ai_risk.rug_pull_detector import RugPullDetector
from ai_risk.types import RugPullAnalysis
from ai_risk.config import AIRiskConfig


@pytest.fixture
def detector():
    """Create a RugPullDetector instance."""
    return RugPullDetector()


@pytest.mark.asyncio
async def test_honeypot_detection(detector):
    """Test honeypot pattern detection."""
    liquidity_data = {
        "lock_duration_days": 30,
        "total_liquidity_usd": 10000,
        "top_lp_holder_percentage": 0.5,
    }
    
    # 80% failed sells
    transaction_history = [
        {"type": "sell", "status": "failed"},
        {"type": "sell", "status": "failed"},
        {"type": "sell", "status": "failed"},
        {"type": "sell", "status": "failed"},
        {"type": "sell", "status": "success"},
    ]
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xtest",
        liquidity_data=liquidity_data,
        transaction_history=transaction_history,
    )
    
    assert "Honeypot contract" in str(analysis.detected_patterns)
    assert analysis.risk_score > 0.7


@pytest.mark.asyncio
async def test_blacklist_detection(detector):
    """Test blacklist functionality."""
    detector.add_to_blacklist("0xbadtoken")
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xbadtoken",
        liquidity_data={},
        transaction_history=[],
    )
    
    assert analysis.risk_score == 1.0
    assert analysis.confidence == 1.0
    assert "blacklist" in str(analysis.detected_patterns).lower()


@pytest.mark.asyncio
async def test_clean_token(detector):
    """Test token with no red flags."""
    liquidity_data = {
        "lock_duration_days": 365,
        "total_liquidity_usd": 1000000,
        "top_lp_holder_percentage": 0.1,
    }
    
    transaction_history = [
        {"type": "buy", "status": "success"},
        {"type": "buy", "status": "success"},
        {"type": "sell", "status": "success"},
        {"type": "sell", "status": "success"},
    ]
    
    contract_info = {
        "is_verified": True,
        "ownership_renounced": True,
        "has_mint_function": False,
        "has_pause_function": False,
        "has_blacklist_function": False,
        "is_proxy": False,
        "age_days": 365,
        "transfer_fee_percent": 0,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xgood",
        liquidity_data=liquidity_data,
        transaction_history=transaction_history,
        contract_info=contract_info,
    )
    
    assert analysis.risk_score < 0.3
    assert len(analysis.detected_patterns) == 0


@pytest.mark.asyncio
async def test_owner_mint_detection(detector):
    """Test owner mint function detection."""
    contract_info = {
        "is_verified": True,
        "owner": "0x123",
        "ownership_renounced": False,
        "has_mint_function": True,
        "has_pause_function": False,
        "has_blacklist_function": False,
        "is_proxy": False,
        "age_days": 100,
        "transfer_fee_percent": 0,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xmintable",
        liquidity_data={"lock_duration_days": 60, "top_lp_holder_percentage": 0.3},
        transaction_history=[],
        contract_info=contract_info,
    )
    
    assert "Owner can mint unlimited tokens" in analysis.detected_patterns


@pytest.mark.asyncio
async def test_low_liquidity_lock_detection(detector):
    """Test low liquidity lock detection."""
    liquidity_data = {
        "lock_duration_days": 15,  # Less than 30 days
        "total_liquidity_usd": 50000,
        "top_lp_holder_percentage": 0.3,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xlowlock",
        liquidity_data=liquidity_data,
        transaction_history=[],
    )
    
    assert "Liquidity lock less than 30 days" in analysis.detected_patterns


@pytest.mark.asyncio
async def test_hidden_transfer_fee_detection(detector):
    """Test hidden transfer fee detection."""
    contract_info = {
        "is_verified": True,
        "ownership_renounced": True,
        "has_mint_function": False,
        "has_pause_function": False,
        "has_blacklist_function": False,
        "is_proxy": False,
        "age_days": 100,
        "transfer_fee_percent": 15,  # Above 10%
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xhiddenfee",
        liquidity_data={},
        transaction_history=[],
        contract_info=contract_info,
    )
    
    assert "Hidden transfer fee above 10%" in analysis.detected_patterns


@pytest.mark.asyncio
async def test_confidence_calculation(detector):
    """Test confidence scoring based on data completeness."""
    # Minimal data
    analysis_minimal = await detector.analyze_rug_pull_risk(
        token_address="0xtest1",
        liquidity_data={},
        transaction_history=[],
    )
    assert analysis_minimal.confidence == 0.5  # Base confidence only
    
    # With liquidity data
    analysis_liq = await detector.analyze_rug_pull_risk(
        token_address="0xtest2",
        liquidity_data={"lock_duration_days": 60},
        transaction_history=[],
    )
    assert analysis_liq.confidence > 0.5
    
    # With all data
    analysis_full = await detector.analyze_rug_pull_risk(
        token_address="0xtest3",
        liquidity_data={"lock_duration_days": 60},
        transaction_history=[{"type": "buy", "status": "success"}],
        contract_info={"is_verified": True, "age_days": 100},
    )
    assert analysis_full.confidence > analysis_liq.confidence


def test_is_blacklisted(detector):
    """Test blacklist check functionality."""
    assert not detector.is_blacklisted("0xunknown")
    
    detector.add_to_blacklist("0xBAD")
    assert detector.is_blacklisted("0xbad")  # Case insensitive
    assert detector.is_blacklisted("0xBAD")


def test_load_blacklist(detector):
    """Test bulk blacklist loading."""
    addresses = ["0x111", "0x222", "0x333"]
    detector.load_blacklist(addresses)
    
    for addr in addresses:
        assert detector.is_blacklisted(addr)


@pytest.mark.asyncio
async def test_temporal_patterns_insufficient_data(detector):
    """Test temporal analysis with insufficient data."""
    result = await detector.analyze_temporal_patterns(
        token_address="0xtest",
        monthly_snapshots=[{"liquidity_usd": 1000}],  # Only 1 month
    )
    
    assert result["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_temporal_patterns_liquidity_drain(detector):
    """Test temporal analysis detects liquidity drain."""
    snapshots = [
        {"liquidity_usd": 100000, "top_holder_percentage": 0.60, "volume_usd": 50000},
        {"liquidity_usd": 80000, "top_holder_percentage": 0.70, "volume_usd": 40000},
        {"liquidity_usd": 20000, "top_holder_percentage": 0.95, "volume_usd": 5000},
    ]
    
    result = await detector.analyze_temporal_patterns(
        token_address="0xdrain",
        monthly_snapshots=snapshots,
    )
    
    assert result["status"] == "ok"
    assert len(result["red_flags"]) > 0
    assert "liquidity drain" in str(result["red_flags"]).lower()


@pytest.mark.asyncio
async def test_large_sell_blocked_detection(detector):
    """Test detection of blocked large sells."""
    transaction_history = [
        {"type": "sell", "status": "failed", "amount_usd": 5000},
        {"type": "sell", "status": "failed", "amount_usd": 2000},
        {"type": "sell", "status": "failed", "amount_usd": 8000},
        {"type": "sell", "status": "success", "amount_usd": 100},
    ]
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xblocked",
        liquidity_data={},
        transaction_history=transaction_history,
    )
    
    assert "Large sell transactions blocked" in analysis.detected_patterns


@pytest.mark.asyncio
async def test_proxy_contract_detection(detector):
    """Test proxy contract detection."""
    contract_info = {
        "is_verified": True,
        "ownership_renounced": True,
        "has_mint_function": False,
        "has_pause_function": False,
        "has_blacklist_function": False,
        "is_proxy": True,
        "age_days": 100,
        "transfer_fee_percent": 0,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xproxy",
        liquidity_data={},
        transaction_history=[],
        contract_info=contract_info,
    )
    
    assert "Upgradeable proxy contract" in analysis.detected_patterns


@pytest.mark.asyncio
async def test_recent_deployment_detection(detector):
    """Test recent deployment detection."""
    contract_info = {
        "is_verified": True,
        "ownership_renounced": True,
        "has_mint_function": False,
        "has_pause_function": False,
        "has_blacklist_function": False,
        "is_proxy": False,
        "age_days": 3,  # Less than 7 days
        "transfer_fee_percent": 0,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xnew",
        liquidity_data={},
        transaction_history=[],
        contract_info=contract_info,
    )
    
    assert "Contract deployed less than 7 days ago" in analysis.detected_patterns


@pytest.mark.asyncio
async def test_concentrated_supply_detection(detector):
    """Test concentrated supply detection."""
    liquidity_data = {
        "lock_duration_days": 60,
        "total_liquidity_usd": 50000,
        "top_lp_holder_percentage": 0.85,  # Above 80%
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xconcentrated",
        liquidity_data=liquidity_data,
        transaction_history=[],
    )
    
    assert "Top LP holder owns >80% of liquidity" in analysis.detected_patterns


def test_analysis_to_dict():
    """Test RugPullAnalysis serialization."""
    analysis = RugPullAnalysis(
        risk_score=0.75,
        confidence=0.85,
        detected_patterns=["Pattern 1", "Pattern 2"],
        key_features={"test": True},
    )
    
    result = analysis.to_dict()
    
    assert result["risk_score"] == 0.75
    assert result["confidence"] == 0.85
    assert len(result["detected_patterns"]) == 2
    assert result["key_features"]["test"] is True
    assert "timestamp" in result
