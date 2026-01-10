from __future__ import annotations

from typing import Any, Dict

from app.contracts.agent_result import AgentResult
from graph.state import RunState


def put_artifact(state: RunState, key: str, value: Any) -> None:
    state.artifacts[key] = value


def append_timeline_event(state: RunState, event: Dict[str, Any]) -> None:
    timeline = state.artifacts.get("timeline")
    if not isinstance(timeline, list):
        timeline = []
    timeline.append(event)
    state.artifacts["timeline"] = timeline


def agent_result_to_timeline(agent_result: AgentResult | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(agent_result, AgentResult):
        payload = agent_result.model_dump()
    else:
        payload = dict(agent_result)

    explanation = payload.get("explanation") or {}
    return {
        "step": payload.get("step_name"),
        "status": payload.get("status"),
        "title": payload.get("agent") or payload.get("step_name"),
        "summary": explanation.get("summary"),
    }
