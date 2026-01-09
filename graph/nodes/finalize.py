from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from db.repos.run_steps_repo import log_step
from graph.state import RunState


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
