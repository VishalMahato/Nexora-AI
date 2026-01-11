from __future__ import annotations

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event
from graph.state import RunState


def _judge_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    judge_result = artifacts.get("judge_result") or {}
    return judge_result.get("output") or {}


def repair_router(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    state.artifacts["attempt"] = state.attempt
    state.artifacts["max_attempts"] = state.max_attempts

    judge_output = _judge_payload(state.artifacts)
    verdict = judge_output.get("verdict")
    issues = judge_output.get("issues") or []

    can_retry = (
        verdict == "NEEDS_REWORK"
        and state.attempt < state.max_attempts
        and isinstance(issues, list)
        and len(issues) > 0
        and settings.LLM_ENABLED
    )

    next_step = "FINALIZE"
    summary = "Routing to finalize."

    if verdict == "BLOCK":
        summary = "Judge blocked; routing to finalize."
    elif verdict == "PASS":
        summary = "Judge passed; routing to finalize."
    elif verdict == "NEEDS_REWORK" and can_retry:
        state.attempt += 1
        state.artifacts["attempt"] = state.attempt
        next_step = "REPAIR_PLAN_TX"
        summary = f"Judge requested rework; retrying (attempt {state.attempt}/{state.max_attempts})."
        state.artifacts["repair_context"] = {
            "attempted": True,
            "attempt": state.attempt,
            "max_attempts": state.max_attempts,
            "judge_issues_used": [issue.get("code") for issue in issues if isinstance(issue, dict)],
        }
    elif verdict == "NEEDS_REWORK" and not settings.LLM_ENABLED:
        summary = "Judge requested rework; repair disabled."
    elif verdict == "NEEDS_REWORK" and state.attempt >= state.max_attempts:
        summary = "Judge requested rework; no retries left."
    elif verdict == "NEEDS_REWORK":
        summary = "Judge requested rework; no usable issues for repair."

    if state.attempt > 1 and verdict in {"PASS", "NEEDS_REWORK"}:
        state.artifacts["repair_summary"] = {
            "attempted": True,
            "success": verdict == "PASS",
            "attempts": state.attempt,
            "max_attempts": state.max_attempts,
        }

    state.artifacts["repair_next_step"] = next_step

    log_step(
        db,
        run_id=state.run_id,
        step_name="REPAIR_ROUTER",
        status="DONE",
        output={
            "verdict": verdict,
            "next_step": next_step,
            "attempt": state.attempt,
            "max_attempts": state.max_attempts,
        },
        agent="LangGraph",
    )

    append_timeline_event(
        state,
        {
            "step": "REPAIR_ROUTER",
            "status": "DONE",
            "title": "repair_router",
            "summary": summary,
            "attempt": state.attempt,
        },
    )

    return state
