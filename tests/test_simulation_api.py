from __future__ import annotations

from unittest.mock import patch

from app.config import get_settings
from db.models.run import RunStatus


VALID_WALLET = "0x1111111111111111111111111111111111111111"


def test_simulation_success_populates_gas_and_fee(client, monkeypatch):
    recipient = "0x9999999999999999999999999999999999999999"
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
        "native": {"balanceWei": "123"},
        "erc20": [],
        "allowances": [],
    }

    with (
        patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot),
        patch("chain.client.ChainClient.eth_call", return_value="0x"),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text

        body = s.json()
        assert body["status"] == RunStatus.AWAITING_APPROVAL.value

        simulation = body["artifacts"]["simulation"]
        assert simulation["status"] == "completed"
        assert simulation["summary"]["num_success"] == 1
        assert simulation["summary"]["num_failed"] == 0
        assert simulation["results"][0]["success"] is True
        assert simulation["results"][0]["gasEstimate"] == "21000"
        assert simulation["results"][0]["fee"]["gasPrice"] == "100"

        assert body["artifacts"]["decision"]["action"] == "NEEDS_APPROVAL"


def test_simulation_failure_blocks_run(client, monkeypatch):
    recipient = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
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
        "native": {"balanceWei": "123"},
        "erc20": [],
        "allowances": [],
    }

    def raise_revert(*_args, **_kwargs):
        raise Exception("execution reverted")

    with (
        patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot),
        patch("chain.client.ChainClient.eth_call", return_value="0x"),
        patch("chain.client.ChainClient.estimate_gas", side_effect=raise_revert),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text

        body = s.json()
        assert body["status"] == RunStatus.BLOCKED.value
        assert body["artifacts"]["decision"]["action"] == "BLOCK"

        simulation = body["artifacts"]["simulation"]
        assert simulation["status"] == "completed"
        assert simulation["summary"]["num_success"] == 0
        assert simulation["summary"]["num_failed"] == 1
        assert simulation["results"][0]["success"] is False
        assert "execution reverted" in (simulation["results"][0]["error"] or "")
