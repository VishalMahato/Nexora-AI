from __future__ import annotations

import uuid
from sqlalchemy import text

from db.session import SessionLocal
from db.repos.run_steps_repo import log_step, list_steps_for_run
from db.repos.runs_repo import create_run


def test_log_step_creates_row():
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent="step test",
            wallet_address="0xabc",
            chain_id=1,
        )

        step = log_step(
            db,
            run_id=run.id,
            step_name="TEST_STEP",
            status="DONE",
            output={"ok": True},
            agent="TEST",
        )

        assert step.id is not None
        assert step.run_id == run.id
        assert step.step_name == "TEST_STEP"
    finally:
        db.close()


def test_list_steps_for_run_ordered():
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent="order test",
            wallet_address="0xdef",
            chain_id=1,
        )

        log_step(db, run_id=run.id, step_name="A", status="DONE")
        log_step(db, run_id=run.id, step_name="B", status="DONE")

        steps = list_steps_for_run(db, run_id=run.id)
        assert len(steps) == 2
        assert steps[0].step_name == "A"
        assert steps[1].step_name == "B"
    finally:
        db.close()
