from __future__ import annotations

from sqlalchemy.orm import Session
from langchain_core.runnables import RunnableConfig

from graph.state import RunState
from db.repos.run_steps_repo import log_step
from chain.client import ChainClient


def input_normalize(state: RunState, config: RunnableConfig) -> RunState:
    """
    Normalize user intent.
    """
    db: Session = config["configurable"]["db"]   # 👈 pulled from config

    # ---- STEP START ----
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

    # ---- STEP DONE ----
    log_step(
        db,
        run_id=state.run_id,
        step_name="INPUT_NORMALIZE",
        status="DONE",
        output={"normalized_intent": normalized_intent},
        agent="LangGraph",
    )

    return state


def finalize(state: RunState, config: RunnableConfig) -> RunState:
    """
    Final no-op node.
    """
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


def wallet_snapshot(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    client = ChainClient()

    # Step start
    log_step(
        db,
        run_id=state.run_id,
        step_name="WALLET_SNAPSHOT",
        status="STARTED",
        input={
            "chainId": state.chain_id,
            "walletAddress": state.wallet_address,
        },
        agent="GRAPH",
    )

    try:
        snapshot = client.wallet_snapshot(
            db=db,
            run_id=state.run_id,
            step_id=None,  # ✅ if your log_step does NOT return step.id reliably
            chain_id=state.chain_id or 0,
            wallet_address=state.wallet_address or "",
            erc20_tokens=[],
            allowances=[],
        )

        state.artifacts["wallet_snapshot"] = snapshot

        # Step done
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
    """
    Deterministic tx planning (MVP):
    - For now: always NOOP plan (safe)
    - Later: parse intent to approve/swap templates
    """
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

    # MVP-safe behavior: NOOP
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
    """
    Simulate planned transactions.
    MVP behavior:
    - If tx_plan is noop or has no candidates → skip
    - Otherwise simulate each tx (future)
    """
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

    # MVP-safe: nothing to simulate
    if tx_plan.get("type") == "noop" or not tx_plan.get("candidates"):
        simulation_result = {
            "status": "skipped",
            "reason": "no transactions to simulate",
        }

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

    # ---- future path (not active yet) ----
    client = ChainClient()
    results = []

    for tx in tx_plan["candidates"]:
        # Placeholder for future simulation
        results.append(
            {
                "tx": tx,
                "status": "not_implemented",
            }
        )

    simulation_result = {
        "status": "completed",
        "results": results,
    }

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