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