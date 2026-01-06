from __future__ import annotations

from db.session import SessionLocal
from db.repos.run_steps_repo import list_steps_for_run


def test_start_run_transitions_and_logs_steps(client):
    # create run
    payload = {
        "intent": "  Start Run Test  ",
        "walletAddress": "0xabc123",
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    # start
    s = client.post(f"/v1/runs/{run_id}/start")
    assert s.status_code == 200, s.text
    assert s.json()["status"] == "AWAITING_APPROVAL"
    assert s.json()["artifacts"]["normalized_intent"] == "Start Run Test"

    # ensure graph steps exist
    db = SessionLocal()
    try:
        steps = list_steps_for_run(db, run_id=run_id)
        step_names = [x.step_name for x in steps]
        assert "INPUT_NORMALIZE" in step_names
        assert "FINALIZE" in step_names
    finally:
        db.close()


def test_start_run_invalid_transition_409(client):
    payload = {
        "intent": "Invalid transition",
        "walletAddress": "0xabc123",
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    # first start ok
    s1 = client.post(f"/v1/runs/{run_id}/start")
    assert s1.status_code == 200

    # second start should fail
    s2 = client.post(f"/v1/runs/{run_id}/start")
    assert s2.status_code == 409
