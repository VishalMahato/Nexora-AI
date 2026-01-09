from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from db.repos.run_steps_repo import log_step
from graph.state import RunState


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
