from __future__ import annotations

from sqlalchemy.orm import Session
from langchain_core.runnables import RunnableConfig  # 👈 import this

from graph.state import RunState
from db.repos.run_steps_repo import log_step


def input_normalize(state: RunState, config: RunnableConfig) -> RunState:
    """
    Normalize user intent.
    """
    # Get DB session from configurable context
    db: Session = config["configurable"]["db"]

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
