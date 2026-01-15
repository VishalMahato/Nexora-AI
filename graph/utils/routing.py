from __future__ import annotations

from graph.state import RunState


def route_post_step(state: RunState, default_next: str) -> str:
    artifacts = state.artifacts
    if artifacts.get("fatal_error"):
        return "FINALIZE"
    if artifacts.get("needs_input"):
        return "CLARIFY"
    return default_next
