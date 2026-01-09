from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, List, Optional, Tuple

import policy.engine as policy_engine
from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session
from web3 import Web3

from app.config import get_settings
from chain.client import ChainClient
from db.repos.run_steps_repo import log_step
from graph.schemas import TxCandidate, TxPlan, TxAction
from graph.state import RunState
from tools.tool_runner import run_tool

def input_normalize(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="INPUT_NORMALIZE",
        status="STARTED",
        input={"intent": state.intent},
        agent="LangGraph",
    )

    normalized_intent = state.intent.strip()
    state.artifacts["normalized_intent"] = normalized_intent

    log_step(
        db,
        run_id=state.run_id,
        step_name="INPUT_NORMALIZE",
        status="DONE",
        output={"normalized_intent": normalized_intent},
        agent="LangGraph",
    )
    return state


def wallet_snapshot(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    client = ChainClient()

    log_step(
        db,
        run_id=state.run_id,
        step_name="WALLET_SNAPSHOT",
        status="STARTED",
        input={"chainId": state.chain_id, "walletAddress": state.wallet_address},
        agent="GRAPH",
    )

    try:
        snapshot = client.wallet_snapshot(
            db=db,
            run_id=state.run_id,
            step_id=None,
            chain_id=state.chain_id or 0,
            wallet_address=state.wallet_address or "",
            erc20_tokens=[],
            allowances=[],
        )

        state.artifacts["wallet_snapshot"] = snapshot

        log_step(
            db,
            run_id=state.run_id,
            step_name="WALLET_SNAPSHOT",
            status="DONE",
            output=snapshot,
            agent="GRAPH",
        )
        return state

    except Exception as e:
        log_step(
            db,
            run_id=state.run_id,
            step_name="WALLET_SNAPSHOT",
            status="FAILED",
            output={"error": f"{type(e).__name__}: {e}"},
            agent="GRAPH",
        )
        raise


def build_txs(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="BUILD_TXS",
        status="STARTED",
        input={
            "normalized_intent": state.artifacts.get("normalized_intent"),
            "has_wallet_snapshot": "wallet_snapshot" in state.artifacts,
        },
        agent="GRAPH",
    )

    normalized_intent = (state.artifacts.get("normalized_intent") or "").lower().strip()

    existing_tx_plan = state.artifacts.get("tx_plan")
    if existing_tx_plan:
        tx_plan = existing_tx_plan
    else:
        tx_plan = {
            "type": "noop",
            "reason": "tx planning not implemented yet (F11 Part 2).",
            "normalized_intent": normalized_intent,
            "candidates": [],
        }
        state.artifacts["tx_plan"] = tx_plan

    log_step(
        db,
        run_id=state.run_id,
        step_name="BUILD_TXS",
        status="DONE",
        output=tx_plan,
        agent="GRAPH",
    )
    return state


def simulate_txs(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    tx_plan = state.artifacts.get("tx_plan") or {}

    log_step(
        db,
        run_id=state.run_id,
        step_name="SIMULATE_TXS",
        status="STARTED",
        input={
            "tx_plan_type": tx_plan.get("type"),
            "num_candidates": len(tx_plan.get("candidates", [])),
        },
        agent="GRAPH",
    )

    if tx_plan.get("type") == "noop" or not tx_plan.get("candidates"):
        simulation_result = {"status": "skipped", "reason": "no transactions to simulate"}
        state.artifacts["simulation"] = simulation_result

        log_step(
            db,
            run_id=state.run_id,
            step_name="SIMULATE_TXS",
            status="DONE",
            output=simulation_result,
            agent="GRAPH",
        )
        return state

    # future implementation
    client = ChainClient()
    results = []
    for tx in tx_plan["candidates"]:
        results.append({"tx": tx, "status": "not_implemented"})

    simulation_result = {"status": "completed", "results": results}
    state.artifacts["simulation"] = simulation_result

    log_step(
        db,
        run_id=state.run_id,
        step_name="SIMULATE_TXS",
        status="DONE",
        output=simulation_result,
        agent="GRAPH",
    )
    return state


def finalize(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="FINALIZE",
        status="DONE",
        output={"artifacts": list(state.artifacts.keys())},
        agent="LangGraph",
    )
    return state




def policy_eval(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    # Step START
    step = log_step(
        db,
        run_id=state.run_id,
        step_name="POLICY_EVAL",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    settings = get_settings()
    policy_result, decision = policy_engine.evaluate_policies(
        state.artifacts,
        allowlisted_to=settings.allowlisted_to_set(),
    )


    state.artifacts["policy_result"] = policy_result.model_dump()
    state.artifacts["decision"] = decision.model_dump()

    # Step DONE
    log_step(
        db,
        run_id=state.run_id,
        step_name="POLICY_EVAL",
        status="DONE",
        output={
            "policy_result": state.artifacts["policy_result"],
            "decision": state.artifacts["decision"],
        },
        agent="LangGraph",
    )

    return state

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

    # keep top N tokens (snapshot is already only for tokens you requested)
    erc20_view = erc20[:top_erc20] if isinstance(erc20, list) else []

    # keep allowances only for allowlisted routers (if needed)
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


def plan_tx(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    normalized_intent: str = (state.artifacts.get("normalized_intent") or "").strip()
    wallet_snapshot: Dict[str, Any] = state.artifacts.get("wallet_snapshot") or {}
    chain_id = getattr(state, "chain_id", None)

    # config allowlists/defaults (names may vary in your settings; keep consistent with your app.config)
    allowlisted_tokens = getattr(settings, "allowlisted_tokens", {}) or {}
    allowlisted_routers = getattr(settings, "allowlisted_routers", {}) or {}
    defaults = getattr(settings, "defaults", {}) or {}

    # collect router addresses for filtering (optional)
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

    # Step 1 - RunStep logging: STARTED (small input only)
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

    # Step 2 - Gather planner inputs (single dict)
    planner_input = {
        "normalized_intent": normalized_intent,
        "chain_id": chain_id,
        "wallet_snapshot": wallet_prompt_view,   # use existing snapshot (light-sliced)
        "allowlisted_tokens": allowlisted_tokens,
        "allowlisted_routers": allowlisted_routers,
        "defaults": defaults,
    }

    state.artifacts["planner_input"] = planner_input

    try:
        raw_plan = run_tool(
            db,
            run_id=state.run_id,
            step_id=step.id,
            tool_name="llm.plan_tx",
            request=planner_input,
            fn=lambda: _plan_tx_stub(planner_input),
        )

        tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)
        state.artifacts["tx_plan"] = tx_plan

        log_step(
            db,
            run_id=state.run_id,
            step_name="PLAN_TX",
            status="DONE",
            output=tx_plan,
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
