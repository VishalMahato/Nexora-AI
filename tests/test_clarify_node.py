from __future__ import annotations

from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.nodes.clarify import clarify
from graph.state import RunState


def _run_clarify(artifacts: dict) -> RunState:
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent="clarify test",
            wallet_address="0x1111111111111111111111111111111111111111",
            chain_id=1,
        )
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=RunStatus.CREATED,
            chain_id=run.chain_id,
            wallet_address=run.wallet_address,
            artifacts=artifacts,
        )
        config = {"configurable": {"db": db}}
        return clarify(state, config)
    finally:
        db.close()


def test_clarify_fills_questions():
    state = _run_clarify(
        {
            "needs_input": {
                "questions": [],
                "missing": ["wallet_address", "amount_in"],
                "resume_from": "PLAN_TX",
            }
        }
    )
    needs = state.artifacts.get("needs_input") or {}
    assert needs.get("questions")
    assert needs.get("missing") == ["wallet_address", "amount_in"]
    assert needs.get("resume_from") == "PLAN_TX"


def test_clarify_keeps_existing_questions():
    state = _run_clarify(
        {
            "needs_input": {
                "questions": ["What wallet address should I use?"],
                "missing": ["wallet_address"],
                "resume_from": "PLAN_TX",
            }
        }
    )
    needs = state.artifacts.get("needs_input") or {}
    assert needs.get("questions") == ["What wallet address should I use?"]
