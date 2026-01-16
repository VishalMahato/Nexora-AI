from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import get_settings
from db.models.run import RunStatus


VALID_WALLET = "0x1111111111111111111111111111111111111111"

pytestmark = pytest.mark.use_llm


def _create_run(client, *, intent: str):
    payload = {
        "intent": intent,
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    r = client.post("/v1/runs", json=payload)
    assert r.status_code == 200
    return r.json()["runId"]


def _fake_snapshot():
    return {
        "chainId": 1,
        "walletAddress": VALID_WALLET,
        "native": {"balanceWei": "1000000000000000000"},
        "erc20": [],
        "allowances": [],
    }


def _llm_plan(recipient: str):
    return {
        "plan_version": 1,
        "type": "plan",
        "normalized_intent": f"send 0.0001 eth to {recipient}",
        "actions": [
            {
                "action": "TRANSFER",
                "amount": "0.0001",
                "to": recipient,
                "chain_id": 1,
                "meta": {"asset": "ETH"},
            }
        ],
        "candidates": [
            {
                "chain_id": 1,
                "to": recipient,
                "data": "0x",
                "valueWei": "100000000000000",
                "meta": {"asset": "ETH"},
            }
        ],
    }


def test_repair_attempt_passes(client, monkeypatch):
    recipient = "0x9999999999999999999999999999999999999999"
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{recipient}\"]')
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    run_id = _create_run(client, intent=f"send 0.0001 eth to {recipient}")

    judge_outputs = [
        {
            "verdict": "NEEDS_REWORK",
            "reasoning_summary": "Mismatch between intent and plan.",
            "issues": [
                {
                    "code": "MISMATCH_INTENT_PLAN",
                    "severity": "MED",
                    "message": "Plan target does not match intent.",
                    "data": {},
                }
            ],
        },
        {
            "verdict": "PASS",
            "reasoning_summary": "Repaired plan is consistent.",
            "issues": [],
        },
    ]

    with (
        patch("llm.client.LLMClient.plan_tx", return_value=_llm_plan(recipient)),
        patch("llm.client.LLMClient.repair_plan_tx", return_value=_llm_plan(recipient)),
        patch("llm.client.LLMClient.judge", side_effect=judge_outputs),
        patch("chain.client.ChainClient.wallet_snapshot", return_value=_fake_snapshot()),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

    assert body["status"] == RunStatus.AWAITING_APPROVAL.value
    artifacts = body["artifacts"]
    assert artifacts["attempt"] == 2
    assert artifacts["repair_summary"]["success"] is True
    assert len(artifacts.get("tx_plan_history") or []) == 1
    assert any(e.get("step") == "REPAIR_ROUTER" for e in artifacts.get("timeline") or [])


def test_repair_attempt_still_needs_rework(client, monkeypatch):
    recipient = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{recipient}\"]')
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    run_id = _create_run(client, intent=f"send 0.0001 eth to {recipient}")

    judge_outputs = [
        {
            "verdict": "NEEDS_REWORK",
            "reasoning_summary": "Simulation inconsistent.",
            "issues": [
                {
                    "code": "SIMULATION_INCONSISTENT",
                    "severity": "HIGH",
                    "message": "Simulation failed for candidate 0.",
                    "data": {"index": 0},
                }
            ],
        },
        {
            "verdict": "NEEDS_REWORK",
            "reasoning_summary": "Still inconsistent.",
            "issues": [
                {
                    "code": "SIMULATION_INCONSISTENT",
                    "severity": "HIGH",
                    "message": "Simulation failed for candidate 0.",
                    "data": {"index": 0},
                }
            ],
        },
    ]

    with (
        patch("llm.client.LLMClient.plan_tx", return_value=_llm_plan(recipient)),
        patch("llm.client.LLMClient.repair_plan_tx", return_value=_llm_plan(recipient)),
        patch("llm.client.LLMClient.judge", side_effect=judge_outputs),
        patch("chain.client.ChainClient.wallet_snapshot", return_value=_fake_snapshot()),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

    assert body["status"] == RunStatus.AWAITING_APPROVAL.value
    artifacts = body["artifacts"]
    assert artifacts["attempt"] == 2
    assert artifacts["repair_summary"]["success"] is False
