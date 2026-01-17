from __future__ import annotations

from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.graph import run_graph
from db.repos.run_steps_repo import list_steps_for_run
from graph.state import RunState


def test_needs_input_routes_to_clarify_and_finalize():
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent="swap usdc",
            wallet_address="0x123",
            chain_id=1,
        )
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=RunStatus.RUNNING,
            chain_id=run.chain_id,
            wallet_address=run.wallet_address,
            artifacts={},
        )

        result = run_graph(db, state)
        needs = result.artifacts.get("needs_input") or {}
        assert needs.get("questions")
        assert "wallet_address" in needs.get("missing", [])
        assert "assistant_message" in result.artifacts
        assert "wallet" in result.artifacts["assistant_message"].lower()

        steps = list_steps_for_run(db, run_id=run.id)
        step_names = [s.step_name for s in steps]
        assert "PRECHECK" in step_names
        assert "WALLET_SNAPSHOT" not in step_names
    finally:
        db.close()
