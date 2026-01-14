from __future__ import annotations

import pytest

from app.config import get_settings
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.nodes.finalize import finalize
from graph.state import RunState


def _run_finalize(*, artifacts: dict, intent: str = "swap 1 usdc to weth"):
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent=intent,
            wallet_address="0x1111111111111111111111111111111111111111",
            chain_id=1,
        )
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=run.status,
            chain_id=run.chain_id,
            wallet_address=run.wallet_address,
            artifacts=artifacts,
        )
        config = {"configurable": {"db": db}}
        return finalize(state, config)
    finally:
        db.close()


def test_finalize_fallback_sets_assistant_message():
    state = _run_finalize(artifacts={"normalized_intent": "swap 1 usdc to weth"})
    assert "assistant_message" in state.artifacts
    assert state.artifacts["assistant_message"]


def test_finalize_needs_input_includes_questions():
    state = _run_finalize(
        artifacts={
            "normalized_intent": "swap",
            "needs_input": {"questions": ["Which token are you swapping from?"]},
        }
    )
    message = state.artifacts.get("assistant_message", "")
    assert "Which token are you swapping from?" in message


@pytest.mark.use_llm
def test_finalize_llm_failure_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    def boom(*_args, **_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr("llm.client.LLMClient.finalize", boom)

    state = _run_finalize(artifacts={"normalized_intent": "swap 1 usdc to weth"})
    assert state.artifacts.get("assistant_message")
    summary = state.artifacts.get("finalize_summary") or {}
    assert summary.get("llm_error")
