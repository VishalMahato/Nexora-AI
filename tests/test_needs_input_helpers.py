from __future__ import annotations

import uuid

from db.models.run import RunStatus
from graph.state import RunState
from graph.utils.needs_input import clear_needs_input, set_needs_input


def test_set_and_clear_needs_input():
    state = RunState(
        run_id=uuid.uuid4(),
        intent="needs input test",
        status=RunStatus.CREATED,
    )

    set_needs_input(
        state,
        questions=["What wallet address should I use?"],
        missing=["wallet_address"],
        resume_from="PLAN_TX",
        data={"chains": [1]},
    )

    needs = state.artifacts.get("needs_input") or {}
    assert needs["questions"] == ["What wallet address should I use?"]
    assert needs["missing"] == ["wallet_address"]
    assert needs["resume_from"] == "PLAN_TX"
    assert needs["data"] == {"chains": [1]}

    clear_needs_input(state)
    assert "needs_input" not in state.artifacts
