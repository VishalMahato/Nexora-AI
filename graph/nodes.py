from __future__ import annotations

from sqlalchemy.orm import Session
from langchain_core.runnables import RunnableConfig

from graph.state import RunState
from db.repos.run_steps_repo import log_step
from chain.client import ChainClient
import policy.engine as policy_engine

from app.config import get_settings

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