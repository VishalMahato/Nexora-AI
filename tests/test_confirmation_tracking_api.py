from __future__ import annotations

from unittest.mock import patch

from app.config import get_settings
from db.models.run import RunStatus
from db.repos.run_steps_repo import list_steps_for_run
from db.repos.runs_repo import get_run
from db.session import SessionLocal


VALID_WALLET = "0x1111111111111111111111111111111111111111"


def _create_and_submit_run(client, *, monkeypatch, recipient: str):
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
        assert start_body["status"] == RunStatus.AWAITING_APPROVAL.value

    a = client.post(f"/v1/runs/{run_id}/approve", json={"reviewer": "tester"})
    assert a.status_code == 200, a.text
    assert a.json()["status"] == RunStatus.APPROVED_READY.value

    payload = {"txHash": "0x" + ("a" * 64), "submittedBy": "manual"}
    t = client.post(f"/v1/runs/{run_id}/tx_submitted", json=payload)
    assert t.status_code == 200, t.text
    assert t.json()["status"] == RunStatus.SUBMITTED.value

    return run_id, payload["txHash"]


def test_poll_tx_before_mined_returns_pending(client, monkeypatch):
    recipient = "0x4444444444444444444444444444444444444444"
    run_id, tx_hash = _create_and_submit_run(client, monkeypatch=monkeypatch, recipient=recipient)

    with patch("chain.client.ChainClient.get_tx_receipt", return_value=None):
        r = client.post(f"/v1/runs/{run_id}/poll_tx")
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["status"] == RunStatus.SUBMITTED.value
    assert body["mined"] is False
    assert body["tx_hash"] == tx_hash
    assert body["receipt"] is None

    db = SessionLocal()
    try:
        run = get_run(db, run_id)
        assert run is not None
        assert run.status == RunStatus.SUBMITTED.value
    finally:
        db.close()


def test_poll_tx_confirms_run_on_success_receipt(client, monkeypatch):
    recipient = "0x5555555555555555555555555555555555555555"
    run_id, tx_hash = _create_and_submit_run(client, monkeypatch=monkeypatch, recipient=recipient)

    receipt = {"status": 1, "blockNumber": 123, "gasUsed": 21000, "transactionHash": "0x" + ("b" * 64)}
    with patch("chain.client.ChainClient.get_tx_receipt", return_value=receipt):
        r = client.post(f"/v1/runs/{run_id}/poll_tx")
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["status"] == RunStatus.CONFIRMED.value
    assert body["mined"] is True
    assert body["tx_hash"] == tx_hash
    assert body["receipt"] == receipt

    db = SessionLocal()
    try:
        run = get_run(db, run_id)
        assert run is not None
        assert run.status == RunStatus.CONFIRMED.value
        assert run.artifacts.get("tx_receipt") == receipt

        steps = list_steps_for_run(db, run_id=run_id)
        names = [s.step_name for s in steps]
        assert "TX_CONFIRMED" in names
    finally:
        db.close()

 
def test_poll_tx_marks_reverted_on_failure_receipt(client, monkeypatch):
    recipient = "0x6666666666666666666666666666666666666666"
    run_id, tx_hash = _create_and_submit_run(client, monkeypatch=monkeypatch, recipient=recipient)

    receipt = {"status": 0, "blockNumber": 124, "gasUsed": 21000, "transactionHash": "0x" + ("c" * 64)}
    with patch("chain.client.ChainClient.get_tx_receipt", return_value=receipt):
        r = client.post(f"/v1/runs/{run_id}/poll_tx")
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["status"] == RunStatus.REVERTED.value
    assert body["mined"] is True
    assert body["tx_hash"] == tx_hash
    assert body["receipt"] == receipt

    db = SessionLocal()
    try:
        run = get_run(db, run_id)
        assert run is not None
        assert run.status == RunStatus.REVERTED.value
        assert run.artifacts.get("tx_receipt") == receipt

        steps = list_steps_for_run(db, run_id=run_id)
        names = [s.step_name for s in steps]
        assert "TX_REVERTED" in names
    finally:
        db.close()
