from __future__ import annotations

from unittest.mock import patch

from app.config import get_settings
from db.models.run import Run, RunStatus
from db.repos.runs_repo import get_run
from db.session import SessionLocal


VALID_WALLET = "0x1111111111111111111111111111111111111111"


def _create_and_start_run(client, *, monkeypatch, recipient: str):
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{recipient}\"]')
    get_settings.cache_clear()

    payload = {
        "intent": f"send 0.0001 eth to {recipient}",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    fake_snapshot = {
        "chainId": 1,
        "walletAddress": VALID_WALLET,
        "native": {"balanceWei": "1000000000000000000"},
        "erc20": [],
        "allowances": [],
    }

    with (
        patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        start_body = s.json()

    return run_id, start_body


def test_execute_wrong_state_409(client):
    payload = {
        "intent": "execute before approval",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    e = client.post(f"/v1/runs/{run_id}/execute")
    assert e.status_code == 409


def test_execute_requires_final_status_ready(client):
    payload = {
        "intent": "final status execute guard",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        assert run is not None
        run.status = RunStatus.APPROVED_READY.value
        run.final_status = "NEEDS_INPUT"
        run.artifacts = {
            "tx_plan": {
                "candidates": [
                    {
                        "chain_id": 1,
                        "to": "0x1111111111111111111111111111111111111111",
                        "data": "0x",
                        "valueWei": "0",
                    }
                ]
            }
        }
        db.add(run)
        db.commit()
    finally:
        db.close()

    e = client.post(f"/v1/runs/{run_id}/execute")
    assert e.status_code == 409
    assert "cannot execute" in e.json()["detail"]
    assert "NEEDS_INPUT" in e.json()["detail"]


def test_execute_returns_tx_request_for_approved_run(client, monkeypatch):
    recipient = "0x2222222222222222222222222222222222222222"
    run_id, start_body = _create_and_start_run(client, monkeypatch=monkeypatch, recipient=recipient)
    assert start_body["status"] == RunStatus.AWAITING_APPROVAL.value

    a = client.post(f"/v1/runs/{run_id}/approve", json={"reviewer": "tester"})
    assert a.status_code == 200, a.text
    assert a.json()["status"] == RunStatus.APPROVED_READY.value

    e = client.post(f"/v1/runs/{run_id}/execute")
    assert e.status_code == 200, e.text
    body = e.json()

    candidate = start_body["artifacts"]["tx_plan"]["candidates"][0]
    candidate_chain_id = candidate.get("chainId") or candidate.get("chain_id")
    assert body["status"] == RunStatus.APPROVED_READY.value
    assert body["tx_request"]["chainId"] == candidate_chain_id
    assert body["tx_request"]["to"] == candidate["to"]
    assert body["tx_request"]["data"] == candidate["data"]
    assert body["tx_request"]["valueWei"] == candidate["valueWei"]


def test_tx_submitted_updates_status_and_artifacts(client, monkeypatch):
    recipient = "0x3333333333333333333333333333333333333333"
    run_id, start_body = _create_and_start_run(client, monkeypatch=monkeypatch, recipient=recipient)
    assert start_body["status"] == RunStatus.AWAITING_APPROVAL.value

    a = client.post(f"/v1/runs/{run_id}/approve", json={"reviewer": "tester"})
    assert a.status_code == 200, a.text

    payload = {"txHash": "0x" + ("a" * 64), "submittedBy": "manual"}
    t = client.post(f"/v1/runs/{run_id}/tx_submitted", json=payload)
    assert t.status_code == 200, t.text
    assert t.json()["status"] == RunStatus.SUBMITTED.value
    assert t.json()["txHash"] == payload["txHash"]

    db = SessionLocal()
    try:
        run = get_run(db, run_id)
        assert run is not None
        assert run.status == RunStatus.SUBMITTED.value
        assert run.artifacts.get("tx_hash") == payload["txHash"]
    finally:
        db.close()
