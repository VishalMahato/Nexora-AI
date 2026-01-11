from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.contracts.agent_result import AgentResult, Explanation
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState


def finalize(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    if "judge_result" not in state.artifacts:
        judge_result = AgentResult(
            agent="judge",
            step_name="JUDGE_AGENT",
            status="WARN",
            output={
                "verdict": "NEEDS_REWORK",
                "reasoning_summary": "Judge result missing; manual review required.",
                "issues": [],
            },
            explanation=Explanation(
                summary="Judge result missing; manual review required.",
                assumptions=[],
                why_safe=[],
                risks=[],
                next_steps=[],
            ),
            confidence=None,
            sources=["policy_result", "decision", "simulation"],
            errors=None,
        ).to_public_dict()
        put_artifact(state, "judge_result", judge_result)
        append_timeline_event(state, agent_result_to_timeline(judge_result))

    log_step(
        db,
        run_id=state.run_id,
        step_name="FINALIZE",
        status="DONE",
        output={"artifacts": list(state.artifacts.keys())},
        agent="LangGraph",
    )
    return state
