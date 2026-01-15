from app.domain.final_status import FinalStatus
from app.services import runs_service
from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.state import RunState


def _make_paused_run(*, intent: str, wallet: str, chain_id: int):
    db = SessionLocal()
    try:
        run = create_run(db, intent=intent, wallet_address=wallet, chain_id=chain_id)
        run.status = RunStatus.PAUSED.value
        run.final_status = FinalStatus.NEEDS_INPUT.value
        run.artifacts = {
            "normalized_intent": intent,
            "needs_input": {
                "questions": [],
                "missing": ["amount", "recipient"],
                "resume_from": "PLAN_TX",
                "data": {},
            },
        }
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    finally:
        db.close()


def test_resume_returns_409_when_no_checkpoint(client, monkeypatch):
    run = _make_paused_run(
        intent="send eth",
        wallet="0x1111111111111111111111111111111111111111",
        chain_id=1,
    )

    monkeypatch.setattr(runs_service, "_load_checkpoint_state", lambda run_id: None)

    response = client.post(
        f"/v1/runs/{run.id}/resume",
        json={"answers": {"amount": "0.1", "recipient": "0x2222222222222222222222222222222222222222"}},
    )

    assert response.status_code == 409
    assert "checkpoint" in response.json()["detail"].lower()


def test_resume_merges_answers_and_clears_needs_input(client, monkeypatch):
    run = _make_paused_run(
        intent="send eth",
        wallet="0x1111111111111111111111111111111111111111",
        chain_id=1,
    )

    state = RunState(
        run_id=run.id,
        intent=run.intent,
        status=RunStatus.PAUSED,
        chain_id=run.chain_id,
        wallet_address=run.wallet_address,
        artifacts=run.artifacts.copy(),
    )

    monkeypatch.setattr(runs_service, "_load_checkpoint_state", lambda run_id: state)

    captured = {}

    def fake_run_graph(_db, passed_state):
        captured["state"] = passed_state
        passed_state.artifacts["tx_plan"] = {"type": "plan", "actions": [], "candidates": []}
        passed_state.artifacts["simulation"] = {"status": "completed", "summary": {}}
        return passed_state

    monkeypatch.setattr(runs_service, "run_graph", fake_run_graph)

    recipient = "0x2222222222222222222222222222222222222222"
    response = client.post(
        f"/v1/runs/{run.id}/resume",
        json={"answers": {"amount": "0.1", "recipient": recipient}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == RunStatus.AWAITING_APPROVAL.value
    assert body["final_status"] == FinalStatus.READY.value

    resumed_state = captured["state"]
    assert "needs_input" not in resumed_state.artifacts
    assert resumed_state.artifacts["user_inputs"]["amount"] == "0.1"
    assert resumed_state.artifacts["user_inputs"]["recipient"] == recipient
    assert "send 0.1 eth to" in resumed_state.artifacts.get("normalized_intent", "")
