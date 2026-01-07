from __future__ import annotations

from unittest.mock import patch

from db.session import SessionLocal
from db.repos.run_steps_repo import list_steps_for_run
from db.repos.runs_repo import get_run, update_run_status
from db.models.run import RunStatus


VALID_WALLET = "0x1111111111111111111111111111111111111111"


def test_start_run_transitions_and_logs_steps(client):
    # 1) Create run
    payload = {
        "intent": "  Start Run Test  ",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200 
    run_id = r.json()["runId"]

    fake_snapshot = {
        "chainId": 1,
        "walletAddress": VALID_WALLET,
        "native": {"balanceWei": "123"},
        "erc20": [],
        "allowances": [],
    }

    # 2) Start run (mock wallet snapshot → no real RPC)
    with patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text

        body = s.json()
        assert body["status"] == RunStatus.AWAITING_APPROVAL.value
        assert body["artifacts"]["normalized_intent"] == "Start Run Test"
        assert body["artifacts"]["wallet_snapshot"]["native"]["balanceWei"] == "123"
        assert body["artifacts"]["tx_plan"]["type"] == "noop"
        assert body["artifacts"]["simulation"]["status"] == "skipped"



    # 3) Ensure steps are logged
    db = SessionLocal()
    try:
        steps = list_steps_for_run(db, run_id=run_id)
        step_names = [x.step_name for x in steps]

        assert "BUILD_TXS" in step_names
        assert "SIMULATE_TXS" in step_names
        assert "INPUT_NORMALIZE" in step_names
        assert "WALLET_SNAPSHOT" in step_names
        assert "FINALIZE" in step_names
    finally:
        db.close()

def test_start_run_invalid_transition_409(client):
    payload = {
        "intent": "Invalid transition",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    fake_snapshot = {
        "chainId": 1,
        "walletAddress": VALID_WALLET,
        "native": {"balanceWei": "123"},
        "erc20": [],
        "allowances": [],
    }

    # First start → OK
    with patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot):
        s1 = client.post(f"/v1/runs/{run_id}/start")
        assert s1.status_code == 200

    # Second start → should fail (not in CREATED anymore)
    s2 = client.post(f"/v1/runs/{run_id}/start")
    assert s2.status_code == 409
