from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from db.repos.run_steps_repo import log_step
from graph.state import RunState


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
