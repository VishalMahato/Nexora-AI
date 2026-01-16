from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from llm.client import LLMClient
from llm.prompts import build_finalize_prompt
from tools.tool_runner import run_tool


def _short_address(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _compact_policy(policy_result: dict | None) -> dict | None:
    if not isinstance(policy_result, dict):
        return None
    checks = policy_result.get("checks") or []
    if not isinstance(checks, list):
        checks = []
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        status = (check.get("status") or "").upper()
        if status == "PASS":
            summary["pass"] += 1
        elif status == "WARN":
            summary["warn"] += 1
        elif status == "FAIL":
            summary["fail"] += 1
    top_issues = [
        {"title": c.get("title"), "reason": c.get("reason")}
        for c in checks
        if (c.get("status") or "").upper() in {"WARN", "FAIL"}
    ][:3]
    return {"summary": summary, "issues": top_issues}


def _compact_decision(decision: dict | None) -> dict | None:
    if not isinstance(decision, dict):
        return None
    return {
        "action": decision.get("action"),
        "summary": decision.get("summary"),
        "reasons": (decision.get("reasons") or [])[:3],
    }


def _compact_security(security_result: dict | None) -> dict | None:
    if not isinstance(security_result, dict):
        return None
    explanation = security_result.get("explanation") or {}
    return {
        "status": security_result.get("status"),
        "summary": explanation.get("summary"),
    }


def _compact_judge(judge_result: dict | None) -> dict | None:
    if not isinstance(judge_result, dict):
        return None
    output = judge_result.get("output") or {}
    issues = output.get("issues") or []
    first_issue = issues[0] if isinstance(issues, list) and issues else None
    if isinstance(first_issue, dict):
        issue_summary = {
            "code": first_issue.get("code"),
            "message": first_issue.get("message"),
            "severity": first_issue.get("severity"),
        }
    else:
        issue_summary = None
    return {
        "verdict": output.get("verdict"),
        "reasoning_summary": output.get("reasoning_summary"),
        "issue": issue_summary,
    }


def _compact_simulation(simulation: dict | None) -> dict | None:
    if not isinstance(simulation, dict):
        return None
    summary = simulation.get("summary") or {}
    return {
        "status": simulation.get("status"),
        "reason": simulation.get("reason"),
        "num_success": summary.get("num_success"),
        "num_failed": summary.get("num_failed"),
    }


def _compact_tx_requests(tx_requests: list | None) -> dict | None:
    if not isinstance(tx_requests, list):
        return None
    first = tx_requests[0] if tx_requests else None
    if isinstance(first, dict):
        first_summary = {
            "to": _short_address(first.get("to")),
            "valueWei": first.get("valueWei") or first.get("value_wei") or first.get("value"),
            "chainId": first.get("chainId") or first.get("chain_id"),
        }
    else:
        first_summary = None
    return {"count": len(tx_requests), "first": first_summary}


def _is_blocked(artifacts: dict) -> bool:
    decision = artifacts.get("decision") or {}
    action = (decision.get("action") or "").upper()
    if action == "BLOCK":
        return True
    security_result = artifacts.get("security_result") or {}
    if (security_result.get("status") or "").upper() == "BLOCK":
        return True
    judge_result = artifacts.get("judge_result") or {}
    verdict = ((judge_result.get("output") or {}).get("verdict") or "").upper()
    return verdict == "BLOCK"


def _simulation_ok(artifacts: dict) -> bool:
    simulation = artifacts.get("simulation")
    if not isinstance(simulation, dict):
        return False
    if simulation.get("status") == "completed":
        return True
    if simulation.get("success") is True:
        return True
    return False


def _resolve_final_status_suggested(artifacts: dict) -> str:
    if artifacts.get("fatal_error"):
        return "FAILED"
    if artifacts.get("needs_input"):
        return "NEEDS_INPUT"
    if _is_blocked(artifacts):
        return "BLOCKED"
    tx_plan = artifacts.get("tx_plan") or {}
    if isinstance(tx_plan, dict) and tx_plan.get("type") == "noop":
        return "NOOP"
    if not artifacts.get("tx_plan"):
        return "FAILED"
    if not _simulation_ok(artifacts):
        return "FAILED"
    return "READY"


def _planner_signal(artifacts: dict) -> dict:
    needs_input = artifacts.get("needs_input") or {}
    missing = needs_input.get("missing") or []
    if isinstance(missing, str):
        missing = [missing]
    questions = needs_input.get("questions") or []
    tx_plan = artifacts.get("tx_plan") or {}
    fatal_error = artifacts.get("fatal_error") or {}

    status = "OK"
    summary = "Plan created."

    step = fatal_error.get("step") if isinstance(fatal_error, dict) else None
    fatal_message = fatal_error.get("message") if isinstance(fatal_error, dict) else None
    if fatal_message and step in {"PLAN_TX", "BUILD_TXS", "REPAIR_PLAN_TX"}:
        status = "FAIL"
        summary = fatal_message
    elif missing or questions:
        status = "WARN"
        if missing:
            summary = "Missing: " + ", ".join(str(m) for m in missing)
        else:
            summary = "Clarification required."
    elif isinstance(tx_plan, dict) and tx_plan.get("type") == "noop":
        status = "WARN"
        reason = tx_plan.get("reason")
        summary = reason if isinstance(reason, str) and reason.strip() else "No actionable plan."

    planner_result = artifacts.get("planner_result") or {}
    explanation = planner_result.get("explanation") or {}
    planner_summary = explanation.get("summary")
    if status == "OK" and isinstance(planner_summary, str) and planner_summary.strip():
        summary = planner_summary.strip()

    return {"agent": "Planner", "status": status, "summary": summary}


def _policy_signal(artifacts: dict) -> dict:
    decision = artifacts.get("decision") or {}
    action = (decision.get("action") or "").upper()
    compact = _compact_policy(artifacts.get("policy_result")) or {}
    summary = decision.get("summary") or "Policy checks completed."

    if action == "BLOCK":
        status = "FAIL"
        reasons = decision.get("reasons") or []
        first_reason = next((r for r in reasons if isinstance(r, str) and r.strip()), None)
        if first_reason:
            summary = first_reason
    else:
        issues = compact.get("issues") or []
        if issues:
            status = "WARN"
            issue = issues[0] or {}
            issue_summary = issue.get("reason") or issue.get("title")
            if isinstance(issue_summary, str) and issue_summary.strip():
                summary = issue_summary
        else:
            status = "OK"

    return {"agent": "Policy", "status": status, "summary": summary}


def _security_signal(artifacts: dict) -> dict:
    security_result = artifacts.get("security_result") or {}
    status_raw = (security_result.get("status") or "").upper()
    explanation = security_result.get("explanation") or {}
    summary = explanation.get("summary") or "Security checks completed."

    if status_raw == "BLOCK":
        status = "FAIL"
    elif status_raw == "WARN":
        status = "WARN"
    else:
        status = "OK"

    return {"agent": "Security", "status": status, "summary": summary}


def _judge_signal(artifacts: dict) -> dict:
    judge_result = artifacts.get("judge_result") or {}
    output = judge_result.get("output") or {}
    verdict = (output.get("verdict") or "").upper()
    summary = output.get("reasoning_summary") or "Judge review completed."

    if verdict == "BLOCK":
        status = "FAIL"
    elif verdict == "NEEDS_REWORK":
        status = "WARN"
    else:
        status = "OK"

    return {"agent": "Judge", "status": status, "summary": summary}


def _consensus_next_ui(verdict: str) -> str:
    verdict = (verdict or "").upper()
    if verdict == "READY":
        return "approve"
    if verdict == "NEEDS_INPUT":
        return "clarify"
    return "explain"


def _build_consensus_summary(artifacts: dict) -> dict:
    verdict = artifacts.get("final_status")
    if isinstance(verdict, str) and verdict.strip():
        verdict_value = verdict.strip().upper()
    else:
        verdict_value = _resolve_final_status_suggested(artifacts)

    return {
        "title": "Multi-agent consensus",
        "verdict": verdict_value,
        "signals": [
            _planner_signal(artifacts),
            _policy_signal(artifacts),
            _security_signal(artifacts),
            _judge_signal(artifacts),
        ],
        "recommended_next_ui": _consensus_next_ui(verdict_value),
    }


def _fallback_assistant_message(finalize_input: dict) -> str:
    status = (finalize_input.get("final_status") or "FAILED").upper()
    intent = finalize_input.get("normalized_intent") or "your request"
    needs_input = finalize_input.get("needs_input") or {}
    questions = needs_input.get("questions") or []
    if status == "READY":
        return (
            "I prepared a safe transaction plan. Please review and approve to proceed."
            f"\nIntent: {intent}"
        )
    if status == "NEEDS_INPUT":
        if questions:
            lines = "\n".join(f"- {q}" for q in questions)
            return f"I need a bit more detail:\n{lines}"
        return "I need a bit more detail before I can proceed. What would you like to do?"
    if status == "BLOCKED":
        decision = finalize_input.get("decision") or {}
        reason = None
        for item in decision.get("reasons") or []:
            if isinstance(item, str) and item.strip():
                reason = item.strip()
                break
        if reason:
            return f"I can't proceed: {reason}"
        return "I can't proceed: the run was blocked by safety checks. Review the timeline for details."
    if status == "NOOP":
        return (
            "I couldn't identify an action to take. Tell me what you'd like to do, "
            "for example: 'swap 1 USDC to WETH'."
        )
    fatal = finalize_input.get("fatal_error") or {}
    fatal_msg = fatal.get("message") if isinstance(fatal, dict) else None
    if fatal_msg:
        return f"I couldn't complete the request due to an error: {fatal_msg}"
    return "I couldn't complete the request due to an error. Please try again or adjust the request."


def _build_finalize_input(state: RunState) -> dict:
    artifacts = state.artifacts
    tx_plan = artifacts.get("tx_plan") or {}
    tx_requests = artifacts.get("tx_requests") or []
    final_status = artifacts.get("final_status") or _resolve_final_status_suggested(artifacts)
    finalize_input = {
        "normalized_intent": artifacts.get("normalized_intent") or state.intent,
        "final_status": final_status,
        "chain_id": state.chain_id,
        "wallet_address": _short_address(state.wallet_address),
        "needs_input": artifacts.get("needs_input"),
        "fatal_error": artifacts.get("fatal_error"),
        "decision": _compact_decision(artifacts.get("decision")),
        "policy_result": _compact_policy(artifacts.get("policy_result")),
        "security_result": _compact_security(artifacts.get("security_result")),
        "judge_result": _compact_judge(artifacts.get("judge_result")),
        "simulation": _compact_simulation(artifacts.get("simulation")),
        "tx_plan": {
            "type": tx_plan.get("type"),
            "reason": tx_plan.get("reason"),
        }
        if isinstance(tx_plan, dict)
        else None,
        "tx_requests": _compact_tx_requests(tx_requests),
    }
    return finalize_input


def _finalize_from_llm(
    *,
    db: Session,
    state: RunState,
    step_id: int,
    finalize_input: dict,
    llm_client: LLMClient,
) -> tuple[str | None, str | None]:
    prompt = build_finalize_prompt(finalize_input)
    raw = run_tool(
        db,
        run_id=state.run_id,
        step_id=step_id,
        tool_name="llm.finalize",
        request={"finalize_input": finalize_input, "prompt": prompt},
        fn=lambda: llm_client.finalize(finalize_input=finalize_input),
    )
    assistant_message = raw.get("assistant_message") if isinstance(raw, dict) else None
    suggested = raw.get("final_status_suggested") if isinstance(raw, dict) else None
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        raise ValueError("finalize assistant_message missing or invalid")
    if isinstance(suggested, str):
        suggested = suggested.strip().upper()
        if suggested not in {"READY", "NEEDS_INPUT", "BLOCKED", "FAILED", "NOOP"}:
            suggested = None
    else:
        suggested = None
    return assistant_message.strip(), suggested


def finalize(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="FINALIZE",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    if "judge_result" not in state.artifacts:
        judge_result = AgentResult(
            agent="judge",
            step_name="JUDGE_AGENT",
            status="WARN",
            output={
                "verdict": "NEEDS_REWORK",
                "reasoning_summary": "Judge result missing; manual review required.",
                "issues": [],
            },
            explanation=Explanation(
                summary="Judge result missing; manual review required.",
                assumptions=[],
                why_safe=[],
                risks=[],
                next_steps=[],
            ),
            confidence=None,
            sources=["policy_result", "decision", "simulation"],
            errors=None,
        ).to_public_dict()
        put_artifact(state, "judge_result", judge_result)
        judge_event = agent_result_to_timeline(judge_result)
        judge_event["attempt"] = state.attempt
        append_timeline_event(state, judge_event)

    finalize_input = _build_finalize_input(state)
    assistant_message = None
    final_status_suggested = None
    llm_used = False
    llm_error = None

    if settings.LLM_ENABLED:
        llm_client = LLMClient(
            model=settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            api_key=settings.OPENAI_API_KEY,
            temperature=settings.LLM_CHAT_TEMPERATURE,
            timeout_s=settings.LLM_TIMEOUT_S,
        )
        try:
            assistant_message, final_status_suggested = _finalize_from_llm(
                db=db,
                state=state,
                step_id=step.id,
                finalize_input=finalize_input,
                llm_client=llm_client,
            )
            llm_used = True
        except Exception as e:
            llm_error = f"{type(e).__name__}: {e}"

    if not assistant_message:
        assistant_message = _fallback_assistant_message(finalize_input)
        if not final_status_suggested:
            final_status_suggested = finalize_input.get("final_status")

    state.artifacts["consensus_summary"] = _build_consensus_summary(state.artifacts)
    state.artifacts["assistant_message"] = assistant_message
    if final_status_suggested:
        state.artifacts["final_status_suggested"] = final_status_suggested
    state.artifacts["finalize_summary"] = {
        "final_status_suggested": final_status_suggested,
        "llm_used": llm_used,
        "llm_error": llm_error,
    }

    log_step(
        db,
        run_id=state.run_id,
        step_name="FINALIZE",
        status="DONE",
        output={
            "assistant_message": assistant_message,
            "final_status_suggested": final_status_suggested,
            "llm_used": llm_used,
            "llm_error": llm_error,
        },
        agent="LangGraph",
    )
    return state
