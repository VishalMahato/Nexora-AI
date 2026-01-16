from __future__ import annotations

from unittest.mock import patch

import pytest

from app.config import get_settings
from db.models.run import RunStatus
from db.repos.tool_calls_repo import list_tool_calls_for_run
from db.session import SessionLocal


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


def test_llm_plan_success_logged_and_used(client, monkeypatch):
    recipient = "0x7777777777777777777777777777777777777777"
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{recipient}\"]')
    monkeypatch.setenv("ALLOWLIST_TO_ALL", "false")
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    run_id = _create_run(client, intent=f"send 0.0002 eth to {recipient}")

    llm_plan = {
        "plan_version": 1,
        "type": "plan",
        "normalized_intent": f"send 0.0002 eth to {recipient}",
        "actions": [
            {
                "action": "TRANSFER",
                "amount": "0.0002",
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
                "valueWei": "200000000000000",
                "meta": {"asset": "ETH"},
            }
        ],
    }
    judge_output = {
        "verdict": "PASS",
        "reasoning_summary": "Plan and simulation are consistent.",
        "issues": [],
    }

    with (
        patch("llm.client.LLMClient.plan_tx", return_value=llm_plan),
        patch("llm.client.LLMClient.judge", return_value=judge_output),
        patch("chain.client.ChainClient.wallet_snapshot", return_value=_fake_snapshot()),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

    assert body["status"] == RunStatus.AWAITING_APPROVAL.value
    assert body["final_status"] == "READY"
    assert body["artifacts"]["tx_plan"]["type"] == "plan"
    assert body["artifacts"]["decision"]["action"] == "NEEDS_APPROVAL"

    db = SessionLocal()
    try:
        tool_calls = list_tool_calls_for_run(db, run_id=run_id)
        assert any(tc.tool_name == "llm.plan_tx" for tc in tool_calls)
    finally:
        db.close()


def test_llm_invalid_plan_falls_back_to_stub(client, monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    run_id = _create_run(client, intent="swap 1 eth to usdc")
    judge_output = {
        "verdict": "PASS",
        "reasoning_summary": "No issues detected.",
        "issues": [],
    }

    with (
        patch("llm.client.LLMClient.plan_tx", return_value={"type": "plan", "actions": []}),
        patch("llm.client.LLMClient.judge", return_value=judge_output),
        patch("chain.client.ChainClient.wallet_snapshot", return_value=_fake_snapshot()),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

    assert body["status"] == RunStatus.PAUSED.value
    assert body["final_status"] == "NOOP"
    assert body["artifacts"]["tx_plan"]["type"] == "noop"
    assert "planner_warnings" in body["artifacts"]
    assert body["artifacts"]["planner_fallback"]["used"] is True


def test_llm_plan_non_allowlisted_is_blocked(client, monkeypatch):
    allowed = "0x8888888888888888888888888888888888888888"
    recipient = "0x9999999999999999999999999999999999999999"
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{allowed}\"]')
    monkeypatch.setenv("ALLOWLIST_TO_ALL", "false")
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    run_id = _create_run(client, intent=f"send 0.0003 eth to {recipient}")

    llm_plan = {
        "plan_version": 1,
        "type": "plan",
        "normalized_intent": f"send 0.0003 eth to {recipient}",
        "actions": [
            {
                "action": "TRANSFER",
                "amount": "0.0003",
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
                "valueWei": "300000000000000",
                "meta": {"asset": "ETH"},
            }
        ],
    }
    judge_output = {
        "verdict": "PASS",
        "reasoning_summary": "Plan is ready.",
        "issues": [],
    }

    with (
        patch("llm.client.LLMClient.plan_tx", return_value=llm_plan),
        patch("llm.client.LLMClient.judge", return_value=judge_output),
        patch("chain.client.ChainClient.wallet_snapshot", return_value=_fake_snapshot()),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

    assert body["status"] == RunStatus.BLOCKED.value
    assert body["artifacts"]["decision"]["action"] == "BLOCK"
