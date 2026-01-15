from __future__ import annotations

from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.graph import run_graph
from graph.state import RunState


def test_needs_input_routes_to_clarify_and_finalize():
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent="swap usdc",
            wallet_address="0x1111111111111111111111111111111111111111",
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
        assert "token_out" in needs.get("missing", [])
        assert "assistant_message" in result.artifacts
        assert "token" in result.artifacts["assistant_message"].lower()
    finally:
        db.close()
