from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from db.repos.run_steps_repo import log_step
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


def _format_amount_from_base_units(amount_wei: int | str | None, decimals: int) -> str | None:
    try:
        if amount_wei is None:
            return None
        value = int(str(amount_wei))
    except Exception:
        return None
    if decimals <= 0:
        return str(value)
    scale = 10 ** decimals
    whole = value // scale
    frac = value % scale
    frac_str = str(frac).rjust(decimals, "0").rstrip("0")
    if not frac_str:
        return str(whole)
    return f"{whole}.{frac_str[:6]}"


def _format_slippage_bps(slippage_bps: int | str | None) -> str | None:
    try:
        if slippage_bps is None:
            return None
        value = int(str(slippage_bps))
    except Exception:
        return None
    return f"{value / 100:.2f}%"


def _extract_fee_info(simulation: dict | None) -> tuple[str | None, dict | None]:
    if not isinstance(simulation, dict):
        return None, None
    results = simulation.get("results") or []
    if not isinstance(results, list):
        return None, None
    fee = None
    gas_estimate = None
    for result in results:
        if not isinstance(result, dict):
            continue
        gas = result.get("gasEstimate")
        fee_obj = result.get("fee")
        if fee_obj and isinstance(fee_obj, dict):
            fee = fee_obj
            gas_estimate = gas
            break
        if gas and gas_estimate is None:
            gas_estimate = gas
    if not fee or gas_estimate is None:
        return None, None
    try:
        gas_int = int(str(gas_estimate))
    except Exception:
        return None, None
    max_fee = fee.get("maxFeePerGas") or fee.get("gasPrice")
    if max_fee is None:
        return None, None
    try:
        max_fee_int = int(str(max_fee))
    except Exception:
        return None, None
    total_fee = gas_int * max_fee_int
    fee_eth = _format_amount_from_base_units(total_fee, 18)
    if not fee_eth:
        return None, None
    return fee_eth, {"gasEstimate": gas_estimate, "fee": fee}


def _extract_tx_summary(artifacts: dict) -> dict | None:
    tx_plan = artifacts.get("tx_plan") or {}
    actions = tx_plan.get("actions") if isinstance(tx_plan, dict) else None
    actions = actions if isinstance(actions, list) else []
    quote = artifacts.get("quote") or {}
    planner_input = artifacts.get("planner_input") or {}
    allowlisted_tokens = planner_input.get("allowlisted_tokens") or {}

    swap_action = next((a for a in actions if (a.get("action") or "").upper() == "SWAP"), None)
    approve_action = next((a for a in actions if (a.get("action") or "").upper() == "APPROVE"), None)

    token_in = (swap_action or {}).get("token_in")
    token_out = (swap_action or {}).get("token_out")
    amount_in = (swap_action or {}).get("amount_in")
    slippage_bps = (swap_action or {}).get("slippage_bps")
    deadline_seconds = (swap_action or {}).get("deadline_seconds")

    quote_min_out = quote.get("minOut")
    quote_amount_in = quote.get("amountIn")
    quote_slippage = quote.get("slippageBps")

    token_out_meta = allowlisted_tokens.get(str(token_out).upper()) if token_out else None
    token_out_decimals = token_out_meta.get("decimals") if isinstance(token_out_meta, dict) else None
    min_out_human = None
    if quote_min_out and token_out_decimals is not None:
        min_out_human = _format_amount_from_base_units(quote_min_out, int(token_out_decimals))

    slippage = _format_slippage_bps(slippage_bps or quote_slippage)

    fee_eth, fee_raw = _extract_fee_info(artifacts.get("simulation"))

    if not swap_action:
        return None

    return {
        "type": "swap",
        "token_in": token_in,
        "token_out": token_out,
        "amount_in": amount_in,
        "min_out": min_out_human,
        "slippage": slippage,
        "deadline_seconds": deadline_seconds,
        "router_key": (swap_action or {}).get("router_key") or quote.get("routerKey"),
        "approval_required": bool(approve_action),
        "quote_amount_in": quote_amount_in,
        "gas_fee_estimate_eth": fee_eth,
        "gas_fee_details": fee_raw,
    }


def _compact_tx_plan(tx_plan: dict | None) -> dict | None:
    if not isinstance(tx_plan, dict):
        return None
    plan_type = tx_plan.get("type")
    if isinstance(plan_type, str) and plan_type.lower() == "noop":
        plan_type = "empty"
    actions = tx_plan.get("actions") or []
    candidates = tx_plan.get("candidates") or []
    return {
        "type": plan_type,
        "action_count": len(actions) if isinstance(actions, list) else 0,
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
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


def _sanitize_reason(reason: str | None) -> str | None:
    if not isinstance(reason, str):
        return None
    text = reason.strip()
    if not text:
        return None
    text = text.replace("noop", "no actionable plan")
    text = text.replace("no-op", "no actionable plan")
    return text


def _extract_block_reason(artifacts: dict) -> str | None:
    decision = artifacts.get("decision") or {}
    reasons = decision.get("reasons") or []
    for item in reasons:
        if isinstance(item, str) and item.strip():
            return _sanitize_reason(item)

    judge_output = (artifacts.get("judge_result") or {}).get("output") or {}
    reasoning = judge_output.get("reasoning_summary")
    if isinstance(reasoning, str) and reasoning.strip():
        return _sanitize_reason(reasoning)
    issues = judge_output.get("issues") or []
    if isinstance(issues, list) and issues:
        issue = issues[0] or {}
        if isinstance(issue, dict):
            message = issue.get("message") or issue.get("code")
            if isinstance(message, str) and message.strip():
                return _sanitize_reason(message)

    security_result = artifacts.get("security_result") or {}
    explanation = security_result.get("explanation") or {}
    summary = explanation.get("summary")
    if isinstance(summary, str) and summary.strip():
        return _sanitize_reason(summary)
    return None


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
    if "judge_result" not in artifacts:
        return {"agent": "Judge", "status": "SKIPPED", "summary": "Judge step skipped."}
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
    block_reason = finalize_input.get("block_reason")
    tx_summary = finalize_input.get("tx_summary") or {}
    gas_fee = tx_summary.get("gas_fee_estimate_eth")
    slippage = tx_summary.get("slippage")
    min_out = tx_summary.get("min_out")
    approval_required = tx_summary.get("approval_required")
    if status == "READY":
        details = []
        if slippage:
            details.append(f"Slippage: {slippage}")
        if min_out:
            details.append(f"Min receive: {min_out} {tx_summary.get('token_out')}")
        if gas_fee:
            details.append(f"Estimated gas fee: ~{gas_fee} ETH")
        if approval_required:
            details.append("An approval transaction is required before the swap.")
        detail_text = "\n".join(details)
        if detail_text:
            detail_text = f"\n{detail_text}"
        return (
            "I prepared a safe transaction plan. Please review and approve to proceed."
            f"\nIntent: {intent}{detail_text}"
        )
    if status == "NEEDS_INPUT":
        if questions:
            lines = "\n".join(f"- {q}" for q in questions)
            return f"I need a bit more detail:\n{lines}"
        return "I need a bit more detail before I can proceed. What would you like to do?"
    if status == "BLOCKED":
        if isinstance(block_reason, str) and block_reason.strip():
            return f"I can't proceed yet: {block_reason.strip()}"
        return "I can't proceed yet because this request needs more detail or failed safety checks."
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
    skipped_steps = []
    if "simulation" not in artifacts:
        skipped_steps.append("SIMULATE_TXS")
    if "policy_result" not in artifacts:
        skipped_steps.append("POLICY_EVAL")
    if "security_result" not in artifacts:
        skipped_steps.append("SECURITY_EVAL")
    if "judge_result" not in artifacts:
        skipped_steps.append("JUDGE_AGENT")
    finalize_input = {
        "normalized_intent": artifacts.get("normalized_intent") or state.intent,
        "final_status": final_status,
        "chain_id": state.chain_id,
        "wallet_address": _short_address(state.wallet_address),
        "needs_input": artifacts.get("needs_input"),
        "fatal_error": artifacts.get("fatal_error"),
        "block_reason": _extract_block_reason(artifacts),
        "skipped_steps": skipped_steps,
        "tx_summary": _extract_tx_summary(artifacts),
        "decision": _compact_decision(artifacts.get("decision")),
        "policy_result": _compact_policy(artifacts.get("policy_result")),
        "security_result": _compact_security(artifacts.get("security_result")),
        "judge_result": _compact_judge(artifacts.get("judge_result")),
        "simulation": _compact_simulation(artifacts.get("simulation")),
        "tx_plan": _compact_tx_plan(tx_plan),
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
