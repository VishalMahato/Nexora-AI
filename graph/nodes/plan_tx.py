from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session
from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.schemas import TxCandidate, TxPlan, TxAction
from graph.state import RunState
from llm.client import LLMClient
from llm.prompts import build_plan_tx_prompt
from tools.tool_runner import run_tool


def _min_wallet_prompt_view(
    wallet_snapshot: Dict[str, Any],
    *,
    top_erc20: int = 8,
    allowlisted_router_addresses: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Do NOT reinvent snapshot. Just slice/filter the existing structure
    to keep prompt payload small.
    """
    allowlisted_router_addresses = allowlisted_router_addresses or []

    erc20 = wallet_snapshot.get("erc20") or []
    allowances = wallet_snapshot.get("allowances") or []

    erc20_view = erc20[:top_erc20] if isinstance(erc20, list) else []

    if allowlisted_router_addresses and isinstance(allowances, list):
        allowset = {a.lower() for a in allowlisted_router_addresses}
        allowances_view = [
            row for row in allowances
            if isinstance(row, dict) and str(row.get("spender", "")).lower() in allowset
        ]
    else:
        allowances_view = allowances if isinstance(allowances, list) else []

    return {
        "chainId": wallet_snapshot.get("chainId"),
        "walletAddress": wallet_snapshot.get("walletAddress"),
        "native": wallet_snapshot.get("native"),
        "erc20": erc20_view,
        "allowances": allowances_view,
    }


def _plan_tx_stub(planner_input: Dict[str, Any]) -> Dict[str, Any]:
    normalized_intent = (planner_input.get("normalized_intent") or "").strip()
    chain_id = planner_input.get("chain_id")

    text = " ".join(normalized_intent.lower().split())
    match = re.match(
        r"^(send|transfer)\s+([0-9]+(?:\.[0-9]+)?)\s+(eth|matic)\s+to\s+(0x[a-fA-F0-9]{40})$",
        text,
    )
    if not match:
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "no supported native transfer intent match",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }

    if not chain_id:
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "missing chain_id",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }

    amount_str = match.group(2)
    asset = match.group(3).upper()
    to_addr = match.group(4)

    try:
        amount_dec = Decimal(amount_str)
    except InvalidOperation:
        amount_dec = Decimal(0)

    if amount_dec <= 0:
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "amount must be greater than zero",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }

    value_wei = str(int(amount_dec * (Decimal(10) ** 18)))
    if value_wei == "0":
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "amount too small",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }
    candidate = TxCandidate(
        chain_id=int(chain_id),
        to=to_addr,
        data="0x",
        value_wei=value_wei,
        meta={"asset": asset},
    )
    action = TxAction(
        action="TRANSFER",
        amount=amount_str,
        to=to_addr,
        chain_id=int(chain_id),
        meta={"asset": asset},
    )

    return {
        "plan_version": 1,
        "type": "plan",
        "normalized_intent": normalized_intent,
        "actions": [action.model_dump(by_alias=True)],
        "candidates": [candidate.model_dump(by_alias=True)],
    }


def _noop_plan(normalized_intent: str, reason: str) -> Dict[str, Any]:
    return {
        "plan_version": 1,
        "type": "noop",
        "reason": reason,
        "normalized_intent": normalized_intent,
        "actions": [],
        "candidates": [],
    }


def plan_tx(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    normalized_intent: str = (state.artifacts.get("normalized_intent") or "").strip()
    wallet_snapshot: Dict[str, Any] = state.artifacts.get("wallet_snapshot") or {}
    chain_id = getattr(state, "chain_id", None)

    allowlisted_tokens = settings.allowlisted_tokens_for_chain(chain_id)
    allowlisted_routers = settings.allowlisted_routers_for_chain(chain_id)
    defaults = {
        "slippage_bps": settings.default_slippage_bps,
        "deadline_seconds": settings.default_deadline_seconds,
        "dex_kind": settings.dex_kind,
    }

    router_addresses: List[str] = []
    for _, rv in allowlisted_routers.items():
        if isinstance(rv, str):
            router_addresses.append(rv)
        elif isinstance(rv, dict) and rv.get("address"):
            router_addresses.append(rv["address"])

    wallet_prompt_view = _min_wallet_prompt_view(
        wallet_snapshot,
        top_erc20=8,
        allowlisted_router_addresses=router_addresses,
    )

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="PLAN_TX",
        status="STARTED",
        input={
            "normalized_intent": normalized_intent,
            "chain_id": chain_id,
            "wallet": {
                "native": wallet_prompt_view.get("native"),
                "erc20_count": len(wallet_snapshot.get("erc20") or []),
                "allowances_count": len(wallet_snapshot.get("allowances") or []),
            },
        },
        agent="LangGraph",
    )

    planner_input = {
        "normalized_intent": normalized_intent,
        "chain_id": chain_id,
        "wallet_snapshot": wallet_prompt_view,
        "allowlisted_tokens": allowlisted_tokens,
        "allowlisted_routers": allowlisted_routers,
        "defaults": defaults,
    }

    state.artifacts["planner_input"] = planner_input

    try:
        planner_warnings: List[str] = []
        llm_error: str | None = None
        llm_used = False
        fallback_used = False

        tx_plan = None
        if settings.LLM_ENABLED:
            llm_client = LLMClient(
                model=settings.LLM_MODEL,
                provider=settings.LLM_PROVIDER,
                api_key=settings.OPENAI_API_KEY,
                temperature=settings.LLM_TEMPERATURE,
                timeout_s=settings.LLM_TIMEOUT_S,
            )
            prompt = build_plan_tx_prompt(planner_input)
            try:
                raw_plan = run_tool(
                    db,
                    run_id=state.run_id,
                    step_id=step.id,
                    tool_name="llm.plan_tx",
                    request={"planner_input": planner_input, "prompt": prompt},
                    fn=lambda: llm_client.plan_tx(planner_input=planner_input),
                )
                llm_used = True
                tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)
            except Exception as e:
                llm_error = f"{type(e).__name__}: {e}"
                planner_warnings.append("llm planner failed; fallback to deterministic stub")
                fallback_used = True


        if tx_plan is None:
            raw_plan = _plan_tx_stub(planner_input)
            tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)

        max_actions = 3
        max_candidates = 3
        if len(tx_plan.get("actions") or []) > max_actions:
            planner_warnings.append("planner output exceeded action limit; converted to noop")
            tx_plan = _noop_plan(normalized_intent, "planner output exceeded action limit")
            fallback_used = True
        if len(tx_plan.get("candidates") or []) > max_candidates:
            planner_warnings.append("planner output exceeded candidate limit; converted to noop")
            tx_plan = _noop_plan(normalized_intent, "planner output exceeded candidate limit")
            fallback_used = True

        allowlisted_to = settings.allowlisted_to_set()
        if allowlisted_to:
            non_allowlisted = [
                (c.get("to") or "").lower()
                for c in (tx_plan.get("candidates") or [])
                if (c.get("to") or "").lower() not in allowlisted_to
            ]
            if non_allowlisted:
                planner_warnings.append("target not in allowlist; policy may block")

        if planner_warnings:
            state.artifacts["planner_warnings"] = planner_warnings
        if fallback_used:
            state.artifacts["planner_fallback"] = {"used": True, "error": llm_error}
        if llm_error:
            state.artifacts["planner_llm_error"] = llm_error
        state.artifacts["planner_llm_used"] = llm_used
        state.artifacts["tx_plan"] = tx_plan

        risk_items = [
            RiskItem(severity="MED", title="Planner warning", detail=warning)
            for warning in planner_warnings
        ]
        summary = (
            "Planner returned a noop plan."
            if tx_plan.get("type") == "noop"
            else "Planner produced a transaction plan."
        )
        if fallback_used:
            summary = f"{summary} Fallback planner was used."
        status = "WARN" if planner_warnings or fallback_used else "OK"
        errors = [llm_error] if llm_error else None

        planner_result = AgentResult(
            agent="planner",
            step_name="PLAN_TX",
            status=status,
            output={"tx_plan": tx_plan},
            explanation=Explanation(
                summary=summary,
                assumptions=[],
                why_safe=[],
                risks=risk_items,
                next_steps=[],
            ),
            confidence=None,
            sources=[
                "normalized_intent",
                "wallet_snapshot",
                "allowlisted_tokens",
                "allowlisted_routers",
                "defaults",
            ],
            errors=errors,
        ).to_public_dict()

        put_artifact(state, "planner_result", planner_result)
        planner_event = agent_result_to_timeline(planner_result)
        planner_event["attempt"] = state.attempt
        append_timeline_event(state, planner_event)

        log_step(
            db,
            run_id=state.run_id,
            step_name="PLAN_TX",
            status="DONE",
            output={
                "tx_plan": tx_plan,
                "planner_warnings": planner_warnings,
                "llm_error": llm_error,
                "llm_used": llm_used,
                "planner_result": planner_result,
            },
            agent="LangGraph",
        )
        return state

    except Exception as e:
        log_step(
            db,
            run_id=state.run_id,
            step_name="PLAN_TX",
            status="FAILED",
            error=f"{type(e).__name__}: {e}",
            agent="LangGraph",
        )
        raise
