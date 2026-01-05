from __future__ import annotations

from db.session import SessionLocal
from db.repos.runs_repo import create_run
from db.repos.run_steps_repo import log_step
from db.repos.tool_calls_repo import log_tool_call, list_tool_calls_for_run


def test_log_tool_call_creates_row():
    db = SessionLocal()
    try:
        run = create_run(db, intent="tc test", wallet_address="0xabc", chain_id=1)
        step = log_step(db, run_id=run.id, step_name="S", status="DONE")

        call = log_tool_call(
            db,
            run_id=run.id,
            step_id=step.id,
            tool_name="test_tool",
            request={"a": 1},
            response={"b": 2},
        )

        assert call.id is not None
        assert call.run_id == run.id
        assert call.step_id == step.id
        assert call.tool_name == "test_tool"
    finally:
        db.close()


def test_list_tool_calls_for_run_ordered():
    db = SessionLocal()
    try:
        run = create_run(db, intent="order", wallet_address="0xdef", chain_id=1)
        log_tool_call(db, run_id=run.id, tool_name="A")
        log_tool_call(db, run_id=run.id, tool_name="B")

        calls = list_tool_calls_for_run(db, run_id=run.id)
        assert len(calls) == 2
        assert calls[0].tool_name == "A"
        assert calls[1].tool_name == "B"
    finally:
        db.close()
