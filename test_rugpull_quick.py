#!/usr/bin/env python3
"""
Quick test script for Rug Pull Detection feature.

This script demonstrates the rug pull detection functionality.
Run with:
    export SOLSCAN_API_KEY='your_key'
    export BIRDEYE_API_KEY='your_key'
    python3 test_rugpull_quick.py
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_risk.rug_pull_detector import RugPullDetector
from ai_risk.config import get_ai_risk_config, AIRiskConfig


def print_banner():
    print("=" * 60)
    print("       RUG PULL DETECTION FEATURE - QUICK TEST")
    print("=" * 60)


def print_section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


async def test_basic_detection():
    """Test basic rug pull detection."""
    print_section("Test 1: Basic Detection - Clean Token")
    
    detector = RugPullDetector()
    
    # Simulate a clean token
    liquidity_data = {
        "lock_duration_days": 365,
        "total_liquidity_usd": 1000000,
        "top_lp_holder_percentage": 0.15,
    }
    
    transaction_history = [
        {"type": "buy", "status": "success", "amount_usd": 1000},
        {"type": "buy", "status": "success", "amount_usd": 2000},
        {"type": "sell", "status": "success", "amount_usd": 500},
        {"type": "sell", "status": "success", "amount_usd": 800},
    ]
    
    contract_info = {
        "is_verified": True,
        "ownership_renounced": True,
        "has_mint_function": False,
        "has_pause_function": False,
        "has_blacklist_function": False,
        "is_proxy": False,
        "age_days": 365,
        "transfer_fee_percent": 1,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xCleanToken123456789",
        liquidity_data=liquidity_data,
        transaction_history=transaction_history,
        contract_info=contract_info,
    )
    
    print(f"  Risk Score: {analysis.risk_score:.2f}")
    print(f"  Confidence: {analysis.confidence:.2f}")
    print(f"  Detected Patterns: {len(analysis.detected_patterns)}")
    print(f"  Status: {'✅ SAFE' if analysis.risk_score < 0.3 else '⚠️ RISKY'}")
    
    return analysis.risk_score < 0.3


async def test_honeypot_detection():
    """Test honeypot detection."""
    print_section("Test 2: Honeypot Detection")
    
    detector = RugPullDetector()
    
    liquidity_data = {
        "lock_duration_days": 30,
        "total_liquidity_usd": 50000,
        "top_lp_holder_percentage": 0.5,
    }
    
    # 90% failed sells - classic honeypot
    transaction_history = [
        {"type": "buy", "status": "success", "amount_usd": 1000},
        {"type": "buy", "status": "success", "amount_usd": 2000},
        {"type": "sell", "status": "failed", "amount_usd": 500},
        {"type": "sell", "status": "failed", "amount_usd": 800},
        {"type": "sell", "status": "failed", "amount_usd": 1200},
        {"type": "sell", "status": "failed", "amount_usd": 300},
        {"type": "sell", "status": "success", "amount_usd": 50},
    ]
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xHoneypotToken",
        liquidity_data=liquidity_data,
        transaction_history=transaction_history,
    )
    
    print(f"  Risk Score: {analysis.risk_score:.2f}")
    print(f"  Confidence: {analysis.confidence:.2f}")
    print(f"  Detected Patterns:")
    for pattern in analysis.detected_patterns:
        print(f"    ⚠️ {pattern}")
    print(f"  Status: {'🚨 HONEYPOT DETECTED' if 'Honeypot' in str(analysis.detected_patterns) else '❓ UNKNOWN'}")
    
    return "Honeypot" in str(analysis.detected_patterns)


async def test_owner_mint_detection():
    """Test owner mint function detection."""
    print_section("Test 3: Owner Mint Function Detection")
    
    detector = RugPullDetector()
    
    contract_info = {
        "is_verified": True,
        "owner": "0xOwner123",
        "ownership_renounced": False,  # Not renounced!
        "has_mint_function": True,      # Can mint!
        "has_pause_function": True,     # Can pause!
        "has_blacklist_function": True, # Has blacklist!
        "is_proxy": False,
        "age_days": 5,                  # Very new
        "transfer_fee_percent": 0,
    }
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address="0xRiskyToken",
        liquidity_data={"lock_duration_days": 7, "top_lp_holder_percentage": 0.9},
        transaction_history=[],
        contract_info=contract_info,
    )
    
    print(f"  Risk Score: {analysis.risk_score:.2f}")
    print(f"  Confidence: {analysis.confidence:.2f}")
    print(f"  Detected Patterns ({len(analysis.detected_patterns)}):")
    for pattern in analysis.detected_patterns:
        print(f"    🚩 {pattern}")
    print(f"  Status: {'🚨 HIGH RISK' if analysis.risk_score > 0.7 else '⚠️ MEDIUM RISK' if analysis.risk_score > 0.3 else '✅ LOW RISK'}")
    
    return analysis.risk_score > 0.5


async def test_blacklist_functionality():
    """Test blacklist functionality."""
    print_section("Test 4: Blacklist Functionality")
    
    detector = RugPullDetector()
    
    # Add known bad token to blacklist
    bad_token = "0xKnownRugPull123"
    detector.add_to_blacklist(bad_token)
    
    print(f"  Added {bad_token} to blacklist")
    print(f"  Is blacklisted: {detector.is_blacklisted(bad_token)}")
    
    analysis = await detector.analyze_rug_pull_risk(
        token_address=bad_token,
        liquidity_data={},
        transaction_history=[],
    )
    
    print(f"  Risk Score: {analysis.risk_score:.2f}")
    print(f"  Confidence: {analysis.confidence:.2f}")
    print(f"  Status: {'🚨 BLACKLISTED' if analysis.risk_score == 1.0 else '❓ NOT BLACKLISTED'}")
    
    return analysis.risk_score == 1.0


async def test_temporal_analysis():
    """Test temporal pattern analysis."""
    print_section("Test 5: Temporal Pattern Analysis (Liquidity Drain)")
    
    detector = RugPullDetector()
    
    # Simulate liquidity drain over 3 months
    monthly_snapshots = [
        {"liquidity_usd": 100000, "top_holder_percentage": 0.30, "volume_usd": 50000},
        {"liquidity_usd": 60000,  "top_holder_percentage": 0.50, "volume_usd": 30000},
        {"liquidity_usd": 10000,  "top_holder_percentage": 0.90, "volume_usd": 5000},
    ]
    
    result = await detector.analyze_temporal_patterns(
        token_address="0xDrainingToken",
        monthly_snapshots=monthly_snapshots,
    )
    
    print(f"  Status: {result['status']}")
    print(f"  Liquidity Trend: {result.get('liquidity_trend', {}).get('trend', 'N/A')}")
    print(f"  Holder Trend: {result.get('holder_trend', {}).get('trend', 'N/A')}")
    print(f"  Red Flags:")
    for flag in result.get("red_flags", []):
        print(f"    🚩 {flag}")
    
    return len(result.get("red_flags", [])) > 0


async def test_config():
    """Test configuration loading."""
    print_section("Test 6: Configuration")
    
    config = get_ai_risk_config()
    
    print(f"  AI Risk Enabled: {config.enabled}")
    print(f"  Approve Threshold: {config.thresholds.approve_max}")
    print(f"  Review Threshold: {config.thresholds.review_max}")
    print(f"  Model Version: {config.rug_pull_model.version}")
    print(f"  Timeout: {config.timeout_seconds}s")
    
    # Check API keys
    birdeye_key = os.environ.get("BIRDEYE_API_KEY")
    solscan_key = os.environ.get("SOLSCAN_API_KEY")
    
    print(f"  Birdeye API Key: {'✅ Set' if birdeye_key else '❌ Not set'}")
    print(f"  Solscan API Key: {'✅ Set' if solscan_key else '❌ Not set'}")
    
    return config.enabled


async def main():
    """Run all tests."""
    print_banner()
    
    results = []
    
    # Run tests
    results.append(("Clean Token Detection", await test_basic_detection()))
    results.append(("Honeypot Detection", await test_honeypot_detection()))
    results.append(("Owner Mint Detection", await test_owner_mint_detection()))
    results.append(("Blacklist Functionality", await test_blacklist_functionality()))
    results.append(("Temporal Analysis", await test_temporal_analysis()))
    results.append(("Configuration", await test_config()))
    
    # Print summary
    print_section("TEST SUMMARY")
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
        if result:
            passed += 1
    
    print(f"\n  Total: {passed}/{len(results)} tests passed")
    print("=" * 60)
    
    return passed == len(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
