from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from app.contracts.judge_result import JudgeIssueSeverity, JudgeOutput, JudgeVerdict
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from llm.client import LLMClient
from llm.prompts import build_judge_prompt
from tools.tool_runner import run_tool


def _slice_list(items: Any, *, limit: int) -> List[Any]:
    if not isinstance(items, list):
        return []
    return items[:limit]


def _compact_wallet_snapshot(wallet_snapshot: Dict[str, Any], *, top_erc20: int = 5) -> Dict[str, Any]:
    erc20 = _slice_list(wallet_snapshot.get("erc20"), limit=top_erc20)
    allowances = _slice_list(wallet_snapshot.get("allowances"), limit=top_erc20)
    return {
        "chainId": wallet_snapshot.get("chainId"),
        "walletAddress": wallet_snapshot.get("walletAddress"),
        "native": wallet_snapshot.get("native"),
        "erc20": erc20,
        "allowances": allowances,
    }


def _compact_tx_plan(tx_plan: Dict[str, Any], *, max_items: int = 3) -> Dict[str, Any]:
    actions = _slice_list(tx_plan.get("actions"), limit=max_items)
    candidates = _slice_list(tx_plan.get("candidates"), limit=max_items)
    return {
        "plan_version": tx_plan.get("plan_version"),
        "type": tx_plan.get("type"),
        "reason": tx_plan.get("reason"),
        "normalized_intent": tx_plan.get("normalized_intent"),
        "action_count": len(tx_plan.get("actions") or []),
        "candidate_count": len(tx_plan.get("candidates") or []),
        "actions": actions,
        "candidates": candidates,
    }


def _summarize_simulation(simulation: Dict[str, Any], *, max_failures: int = 3) -> Dict[str, Any]:
    status = simulation.get("status")
    if status == "skipped":
        return {"status": "skipped", "reason": simulation.get("reason")}
    if status != "completed":
        return {"status": status}

    results = simulation.get("results") or []
    failures = []
    for idx, result in enumerate(results):
        if result.get("success") is False:
            failures.append(
                {
                    "index": idx,
                    "error": result.get("error"),
                    "gasEstimate": result.get("gasEstimate"),
                    "fee": result.get("fee"),
                }
            )
        if len(failures) >= max_failures:
            break

    return {
        "status": "completed",
        "summary": simulation.get("summary"),
        "failures": failures,
    }


def _summarize_policy(policy_result: Dict[str, Any], *, max_items: int = 5) -> Dict[str, Any]:
    checks = policy_result.get("checks") or []
    flagged = []
    for check in checks:
        status = check.get("status")
        if status in {"WARN", "FAIL"}:
            flagged.append(
                {
                    "id": check.get("id"),
                    "title": check.get("title"),
                    "status": status,
                    "reason": check.get("reason"),
                }
            )
        if len(flagged) >= max_items:
            break
    return {
        "flagged_checks": flagged,
        "total_checks": len(checks),
    }


def _build_judge_input(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    tx_plan = artifacts.get("tx_plan") or {}
    simulation = artifacts.get("simulation") or {}
    policy_result = artifacts.get("policy_result") or {}
    decision = artifacts.get("decision") or {}
    wallet_snapshot = artifacts.get("wallet_snapshot") or {}
    planner_result = artifacts.get("planner_result") or {}

    return {
        "normalized_intent": artifacts.get("normalized_intent"),
        "tx_plan": _compact_tx_plan(tx_plan),
        "simulation": _summarize_simulation(simulation),
        "policy_result": _summarize_policy(policy_result),
        "decision": {
            "action": decision.get("action"),
            "severity": decision.get("severity"),
            "risk_score": decision.get("risk_score"),
            "summary": decision.get("summary"),
            "reasons": decision.get("reasons"),
        },
        "wallet_snapshot": _compact_wallet_snapshot(wallet_snapshot),
        "planner_summary": {
            "summary": (planner_result.get("explanation") or {}).get("summary"),
            "plan_type": ((planner_result.get("output") or {}).get("tx_plan") or {}).get("type"),
        },
        "prompt_version": "v1",
    }


def _issue_to_risk_item(issue: Dict[str, Any]) -> RiskItem:
    severity = issue.get("severity") or JudgeIssueSeverity.MED.value
    if severity not in {s.value for s in JudgeIssueSeverity}:
        severity = JudgeIssueSeverity.MED.value
    return RiskItem(
        severity=severity,
        title=issue.get("code") or "JUDGE_ISSUE",
        detail=issue.get("message") or "Judge flagged an issue.",
    )


def _fallback_judge_output(message: str) -> JudgeOutput:
    return JudgeOutput(
        verdict=JudgeVerdict.NEEDS_REWORK,
        reasoning_summary=message,
        issues=[],
    )


def judge_agent(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="JUDGE_AGENT",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    judge_input = _build_judge_input(state.artifacts)

    llm_used = False
    llm_error = None
    judge_output: JudgeOutput

    if settings.LLM_ENABLED:
        llm_client = LLMClient(
            model=settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            api_key=settings.OPENAI_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
            timeout_s=settings.LLM_TIMEOUT_S,
        )
        prompt = build_judge_prompt(judge_input)
        try:
            raw_output = run_tool(
                db,
                run_id=state.run_id,
                step_id=step.id,
                tool_name="llm.judge",
                request={"judge_input": judge_input, "prompt": prompt},
                fn=lambda: llm_client.judge(judge_input=judge_input),
            )
            llm_used = True
            judge_output = JudgeOutput.model_validate(raw_output)
        except Exception as e:
            llm_error = f"{type(e).__name__}: {e}"
            judge_output = _fallback_judge_output("Judge failed; manual review required.")
    else:
        judge_output = _fallback_judge_output("Judge disabled; manual review required.")

    verdict = judge_output.verdict.value
    if verdict == JudgeVerdict.BLOCK.value:
        status = "BLOCK"
    elif verdict == JudgeVerdict.NEEDS_REWORK.value:
        status = "WARN"
    else:
        status = "OK"

    issues = [issue.model_dump() for issue in judge_output.issues]
    risk_items = [_issue_to_risk_item(issue) for issue in issues]
    summary = judge_output.reasoning_summary or "Judge completed review."

    judge_result = AgentResult(
        agent="judge",
        step_name="JUDGE_AGENT",
        status=status,
        output={
            "verdict": verdict,
            "reasoning_summary": judge_output.reasoning_summary,
            "issues": issues,
        },
        explanation=Explanation(
            summary=summary,
            assumptions=[],
            why_safe=[],
            risks=risk_items,
            next_steps=[],
        ),
        confidence=None,
        sources=[
            "planner_result",
            "tx_plan",
            "simulation",
            "policy_result",
            "decision",
            "wallet_snapshot",
        ],
        errors=[llm_error] if llm_error else None,
    ).to_public_dict()

    put_artifact(state, "judge_result", judge_result)
    judge_event = agent_result_to_timeline(judge_result)
    judge_event["attempt"] = state.attempt
    append_timeline_event(state, judge_event)

    log_step(
        db,
        run_id=state.run_id,
        step_name="JUDGE_AGENT",
        status="DONE",
        output={
            "judge_result": judge_result,
            "llm_used": llm_used,
            "llm_error": llm_error,
        },
        agent="LangGraph",
    )

    return state
