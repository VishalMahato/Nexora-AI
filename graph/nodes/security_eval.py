from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from policy.types import CheckStatus, DecisionAction, PolicyResult, Decision


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

    security_result = AgentResult(
        agent="security",
        step_name="SECURITY_EVAL",
        status=status,
        output={
            "policy_result": policy_result.model_dump(),
            "decision": decision.model_dump(),
        },
        explanation=Explanation(
            summary=summary,
            assumptions=[],
            why_safe=[],
            risks=risk_items,
            next_steps=[],
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
