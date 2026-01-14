from __future__ import annotations

import policy.engine as policy_engine
from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from db.repos.run_steps_repo import log_step
from graph.state import RunState


def policy_eval(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

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
        allowlisted_tokens=settings.allowlisted_tokens_for_chain(state.chain_id),
        allowlisted_routers=settings.allowlisted_routers_for_chain(state.chain_id),
        allowlist_targets_enabled=not settings.allowlist_to_all,
        min_slippage_bps=settings.min_slippage_bps,
        max_slippage_bps=settings.max_slippage_bps,
    )

    state.artifacts["policy_result"] = policy_result.model_dump()
    state.artifacts["decision"] = decision.model_dump()

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
