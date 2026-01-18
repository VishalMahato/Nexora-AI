from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from policy.types import CheckStatus, DecisionAction, PolicyResult, Decision

logger = logging.getLogger(__name__)


def _safe_run_async(coro):
    """
    Safely execute async code from sync context.
    Handles existing event loops gracefully.
    """
    try:
        loop = asyncio.get_running_loop()
        # If already in async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    except RuntimeError:
        # No running event loop, safe to use asyncio.run
        return asyncio.run(coro)


def _build_tx_history(simulation_artifact: Optional[Dict]) -> List[Dict[str, Any]]:
    """
    Convert simulation transaction results to simple tx history.
    
    Maps transaction types: swap → sell, approve → transfer
    """
    if not simulation_artifact:
        return []
    
    history = []
    results = simulation_artifact.get("results", [])
    
    for result in results:
        tx = result.get("tx", {})
        meta = tx.get("meta", {})
        kind = meta.get("kind", "unknown")
        success = result.get("success", False)
        
        # Map transaction types
        tx_type = "transfer"
        if kind == "swap":
            tx_type = "sell"
        elif kind in ("buy", "purchase"):
            tx_type = "buy"
        
        history.append({
            "type": tx_type,
            "status": "success" if success else "failed",
            "amount_usd": meta.get("amount_usd", 0),
        })
    
    return history


def _build_liquidity_data(simulation_artifact: Optional[Dict]) -> Dict[str, Any]:
    """
    Extract liquidity context from simulation results.
    Heuristic-based approach to avoid tight coupling.
    """
    if not simulation_artifact:
        return {}
    
    summary = simulation_artifact.get("summary", {})
    num_failed = summary.get("num_failed", 0)
    
    return {
        "lock_duration_days": 0,  # Would need external data
        "total_liquidity_usd": 0,  # Would need external data
        "top_lp_holder_percentage": 0,  # Would need external data
        "_simulation_failures": num_failed,
    }


def _run_rug_pull_analysis(state: RunState) -> Optional[Dict[str, Any]]:
    """
    Run rug-pull detection analysis.
    
    Extracts token address from tx_plan or wallet_snapshot,
    calls RugPullDetector asynchronously.
    
    Returns:
        Dict with analysis results or None on error
    """
    try:
        from ai_risk.rug_pull_detector import RugPullDetector
        from ai_risk.config import get_ai_risk_config
        
        config = get_ai_risk_config()
        if not config.enabled:
            logger.info("AI Risk analysis is disabled")
            return None
        
        # Extract token address
        token_address = None
        
        # Try tx_plan first
        tx_plan = state.artifacts.get("tx_plan", {})
        actions = tx_plan.get("actions", [])
        for action in actions:
            token_in = action.get("token_in") or action.get("tokenIn")
            if token_in:
                token_address = token_in
                break
        
        # Try wallet_snapshot if no token found
        if not token_address:
            wallet_snapshot = state.artifacts.get("wallet_snapshot", {})
            erc20_list = wallet_snapshot.get("erc20", [])
            if erc20_list:
                token_address = erc20_list[0].get("token")
        
        if not token_address:
            logger.debug("No token context available for rug-pull analysis")
            return {"status": "insufficient_data", "message": "No token context available"}
        
        # Build analysis inputs
        simulation = state.artifacts.get("simulation")
        liquidity_data = _build_liquidity_data(simulation)
        tx_history = _build_tx_history(simulation)
        
        # Run analysis
        detector = RugPullDetector(config=config)
        analysis = _safe_run_async(
            detector.analyze_rug_pull_risk(
                token_address=token_address,
                liquidity_data=liquidity_data,
                transaction_history=tx_history,
                contract_info=None,  # Would need external contract data
            )
        )
        
        # Map risk score to severity
        if analysis.risk_score >= 0.8:
            severity = "high"
            suggestions = ["High rug-pull risk detected; abort or re-plan."]
        elif analysis.risk_score >= 0.5:
            severity = "medium"
            suggestions = ["Medium rug-pull risk; verify token and liquidity locks."]
        else:
            severity = "low"
            suggestions = ["Low rug-pull risk; proceed with caution."]
        
        return {
            "status": "ok",
            "risk_score": analysis.risk_score,
            "confidence": analysis.confidence,
            "detected_patterns": analysis.detected_patterns,
            "severity": severity,
            "suggestions": suggestions,
            "model_version": analysis.model_version,
        }
        
    except ImportError as e:
        logger.warning(f"AI Risk module not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Rug-pull analysis failed: {e}", exc_info=True)
        return None


def security_eval(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="SECURITY_EVAL",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    policy_result = PolicyResult.model_validate(state.artifacts.get("policy_result") or {})
    decision = Decision.model_validate(state.artifacts.get("decision") or {})

    warn_count = policy_result.warn_count
    fail_count = policy_result.fail_count
    if decision.action == DecisionAction.BLOCK or fail_count > 0:
        status = "BLOCK"
        summary = "Security evaluation blocked the run."
    elif warn_count > 0:
        status = "WARN"
        summary = "Security evaluation completed with warnings."
    else:
        status = "OK"
        summary = "Security evaluation passed."

    risk_items = []
    for check in policy_result.checks:
        if check.status in {CheckStatus.FAIL, CheckStatus.WARN}:
            severity = "HIGH" if check.status == CheckStatus.FAIL else "MED"
            risk_items.append(
                RiskItem(
                    severity=severity,
                    title=check.title,
                    detail=check.reason or "Policy check flagged an issue.",
                )
            )

    # Run optional rug-pull analysis
    rug_pull_summary = _run_rug_pull_analysis(state)
    
    # Add rug-pull risks if detected
    next_steps = []
    if rug_pull_summary and rug_pull_summary.get("status") == "ok":
        for pattern in rug_pull_summary.get("detected_patterns", []):
            risk_items.append(
                RiskItem(
                    severity="HIGH" if rug_pull_summary.get("severity") == "high" else "MED",
                    title="Rug Pull Pattern",
                    detail=pattern,
                )
            )
        next_steps.extend(rug_pull_summary.get("suggestions", []))
        
        # Update status if high rug-pull risk detected
        if rug_pull_summary.get("severity") == "high" and status == "OK":
            status = "WARN"
            summary = "Security evaluation completed with rug-pull warnings."

    security_result = AgentResult(
        agent="security",
        step_name="SECURITY_EVAL",
        status=status,
        output={
            "policy_result": policy_result.model_dump(),
            "decision": decision.model_dump(),
            "rug_pull_summary": rug_pull_summary,
        },
        explanation=Explanation(
            summary=summary,
            assumptions=[],
            why_safe=[],
            risks=risk_items,
            next_steps=next_steps,
        ),
        confidence=None,
        sources=["tx_plan", "simulation", "wallet_snapshot", "allowlist_to"],
        errors=None,
    ).to_public_dict()

    put_artifact(state, "security_result", security_result)
    security_event = agent_result_to_timeline(security_result)
    security_event["attempt"] = state.attempt
    append_timeline_event(state, security_event)

    log_step(
        db,
        run_id=state.run_id,
        step_name="SECURITY_EVAL",
        status="DONE",
        output={"security_result": security_result},
        agent="LangGraph",
    )

    return state
