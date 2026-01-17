from __future__ import annotations

from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.nodes.precheck import precheck
from graph.state import RunState


def _run_precheck(*, intent: str, chain_id, wallet_address):
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent=intent,
            wallet_address=wallet_address or "0x1111111111111111111111111111111111111111",
            chain_id=chain_id or 1,
        )
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=RunStatus.RUNNING,
            chain_id=chain_id,
            wallet_address=wallet_address,
            artifacts={"normalized_intent": intent},
        )
        config = {"configurable": {"db": db}}
        return precheck(state, config)
    finally:
        db.close()


def test_precheck_missing_chain_id_sets_needs_input():
    state = _run_precheck(intent="swap 1 usdc to weth", chain_id=None, wallet_address="0x1111111111111111111111111111111111111111")
    needs = state.artifacts.get("needs_input") or {}
    assert "chain_id" in needs.get("missing", [])


def test_precheck_invalid_wallet_sets_needs_input():
    state = _run_precheck(intent="swap 1 usdc to weth", chain_id=1, wallet_address="0x123")
    needs = state.artifacts.get("needs_input") or {}
    assert "wallet_address" in needs.get("missing", [])


def test_precheck_empty_intent_sets_needs_input():
    state = _run_precheck(intent="   ", chain_id=1, wallet_address="0x1111111111111111111111111111111111111111")
    needs = state.artifacts.get("needs_input") or {}
    assert "intent" in needs.get("missing", [])


def test_precheck_valid_inputs_no_needs_input():
    state = _run_precheck(intent="swap 1 usdc to weth", chain_id=1, wallet_address="0x1111111111111111111111111111111111111111")
    assert "needs_input" not in state.artifacts
    assert "fatal_error" not in state.artifacts
