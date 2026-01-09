from __future__ import annotations

from unittest.mock import patch

from db.models.run import RunStatus
from db.repos.run_steps_repo import list_steps_for_run
from db.session import SessionLocal

VALID_WALLET = "0x1111111111111111111111111111111111111111"


def _create_and_start_run(client, *, monkeypatch=None, monkeypatch_block: bool = False):
    payload = {
        "intent": "Approval test",
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

    if monkeypatch_block:
        assert monkeypatch is not None, "monkeypatch fixture must be passed when monkeypatch_block=True"

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
        start_body = s.json()

    return run_id, start_body


def test_approve_happy_path(client):
    run_id, start_body = _create_and_start_run(client)
    assert start_body["status"] == RunStatus.AWAITING_APPROVAL.value

    a = client.post(
        f"/v1/runs/{run_id}/approve",
        json={"reviewer": "visha", "notes": "looks good"},
    )
    assert a.status_code == 200, a.text
    assert a.json()["status"] == RunStatus.APPROVED_READY.value

    db = SessionLocal()
    try:
        steps = list_steps_for_run(db, run_id=run_id)
        names = [s.step_name for s in steps]
        assert "HUMAN_APPROVAL" in names
    finally:
        db.close()


def test_reject_happy_path(client):
    run_id, start_body = _create_and_start_run(client)
    assert start_body["status"] == RunStatus.AWAITING_APPROVAL.value

    r = client.post(
        f"/v1/runs/{run_id}/reject",
        json={"reviewer": "vishal;", "reason": "not comfortable"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == RunStatus.REJECTED.value

    db = SessionLocal()
    try:
        steps = list_steps_for_run(db, run_id=run_id)
        names = [s.step_name for s in steps]
        assert "HUMAN_APPROVAL" in names
    finally:
        db.close()


def test_approve_before_start_409(client):
    payload = {
        "intent": "approve before start",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    run_id = r.json()["runId"]

    a = client.post(f"/v1/runs/{run_id}/approve", json={})
    assert a.status_code == 409


def test_approve_blocked_run_409(client, monkeypatch):
    run_id, start_body = _create_and_start_run(client, monkeypatch=monkeypatch, monkeypatch_block=True)
    assert start_body["status"] == RunStatus.BLOCKED.value
    assert start_body["artifacts"]["decision"]["action"] == "BLOCK"

    a = client.post(f"/v1/runs/{run_id}/approve", json={})
    assert a.status_code == 409
