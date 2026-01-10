from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.agent_result import AgentResult, Explanation


def test_agent_result_schema_validates():
    result = AgentResult(
        agent="planner",
        step_name="PLAN_TX",
        status="OK",
        output={"foo": "bar"},
        explanation=Explanation(summary="ok"),
    )
    payload = result.model_dump()
    assert payload["agent"] == "planner"
    assert payload["explanation"]["summary"] == "ok"


def test_agent_result_invalid_status_rejected():
    with pytest.raises(ValidationError):
        AgentResult(
            agent="planner",
            step_name="PLAN_TX",
            status="BAD",
            output={"foo": "bar"},
            explanation=Explanation(summary="bad"),
        )


def test_explanation_requires_summary():
    with pytest.raises(ValidationError):
        Explanation()
