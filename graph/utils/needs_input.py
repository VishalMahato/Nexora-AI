from __future__ import annotations

from typing import Any

from graph.state import RunState


def set_needs_input(
    state: RunState,
    *,
    questions: list[str] | None = None,
    missing: list[str] | None = None,
    resume_from: str,
    data: dict[str, Any] | None = None,
) -> None:
    state.artifacts["needs_input"] = {
        "questions": list(questions or []),
        "missing": list(missing or []),
        "resume_from": resume_from,
        "data": dict(data or {}),
    }


def clear_needs_input(state: RunState) -> None:
    state.artifacts.pop("needs_input", None)
