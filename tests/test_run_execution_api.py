from __future__ import annotations

from unittest.mock import patch

from db.session import SessionLocal
from db.repos.run_steps_repo import list_steps_for_run
from db.models.run import RunStatus


VALID_WALLET = "0x1111111111111111111111111111111111111111"



def test_start_run_transitions_and_logs_steps(client):
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

    with patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text

        body = s.json()
        assert body["status"] == RunStatus.AWAITING_APPROVAL.value

        artifacts = body["artifacts"]
        assert artifacts["normalized_intent"] == "Start Run Test"
        assert artifacts["wallet_snapshot"]["native"]["balanceWei"] == "123"
        assert artifacts["tx_plan"]["type"] == "noop"
        assert artifacts["simulation"]["status"] == "skipped"

        # --- NEW (F12) ---
        assert "policy_result" in artifacts
        assert "decision" in artifacts
        assert artifacts["decision"]["action"] == "NEEDS_APPROVAL"

    db = SessionLocal()
    try:
        steps = list_steps_for_run(db, run_id=run_id)
        step_names = [x.step_name for x in steps]

        assert "INPUT_NORMALIZE" in step_names
        assert "WALLET_SNAPSHOT" in step_names
        assert "BUILD_TXS" in step_names
        assert "SIMULATE_TXS" in step_names
        assert "POLICY_EVAL" in step_names   # --- NEW ---
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

    with patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot):
        s1 = client.post(f"/v1/runs/{run_id}/start")
        assert s1.status_code == 200

    s2 = client.post(f"/v1/runs/{run_id}/start")
    assert s2.status_code == 409

def test_start_run_blocked_by_policy(client, monkeypatch):
    payload = {
        "intent": "Block me",
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

    # Patch the function where it's imported from (policy.engine)
    from policy.types import Decision, DecisionAction, PolicyResult, Severity

    def fake_eval(artifacts, *, allowlisted_to=None):
        return (
            PolicyResult(checks=[]),
            Decision(
                action=DecisionAction.BLOCK,
                risk_score=100,
                severity=Severity.HIGH,
                summary="Blocked by test policy",
                reasons=["test"],
            ),
        )

    monkeypatch.setattr("policy.engine.evaluate_policies", fake_eval)

    with patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

        assert body["status"] == RunStatus.BLOCKED.value
        assert body["artifacts"]["decision"]["action"] == "BLOCK"
