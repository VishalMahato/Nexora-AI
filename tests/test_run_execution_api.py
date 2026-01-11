from __future__ import annotations

from unittest.mock import patch

from web3 import Web3

from app.config import get_settings
from db.session import SessionLocal
from db.repos.runs_repo import get_run
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

    with (
        patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot),
        patch("chain.client.ChainClient.eth_call", return_value=b""),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text

        body = s.json()
        assert body["status"] == RunStatus.AWAITING_APPROVAL.value

        artifacts = body["artifacts"]
        assert artifacts["normalized_intent"] == "Start Run Test"
        assert artifacts["wallet_snapshot"]["native"]["balanceWei"] == "123"
        assert artifacts["tx_plan"]["type"] == "noop"
        assert artifacts["tx_plan"]["plan_version"] == 1
        assert artifacts["simulation"]["status"] == "skipped"

        # --- NEW (F12) ---
        assert "policy_result" in artifacts
        assert "decision" in artifacts
        assert artifacts["decision"]["action"] == "NEEDS_APPROVAL"

        # --- NEW (F20) ---
        assert "planner_result" in artifacts
        assert "security_result" in artifacts
        assert "judge_result" in artifacts
        assert isinstance(artifacts.get("timeline"), list)
        assert len(artifacts.get("timeline")) >= 2

    db = SessionLocal()
    try:
        persisted = get_run(db, run_id)
        assert persisted is not None
        assert persisted.artifacts is not None
        assert persisted.artifacts.get("tx_plan", {}).get("plan_version") == 1

        steps = list_steps_for_run(db, run_id=run_id)
        step_names = [x.step_name for x in steps]

        assert "INPUT_NORMALIZE" in step_names
        assert "WALLET_SNAPSHOT" in step_names
        assert "PLAN_TX" in step_names
        assert "BUILD_TXS" in step_names
        assert "SIMULATE_TXS" in step_names
        assert "POLICY_EVAL" in step_names   # --- NEW ---
        assert "SECURITY_EVAL" in step_names
        assert "JUDGE_AGENT" in step_names
        assert "REPAIR_ROUTER" in step_names
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

    with (
        patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot),
        patch("chain.client.ChainClient.eth_call", return_value=b""),
        patch("chain.client.ChainClient.estimate_gas", return_value=21000),
        patch("chain.client.ChainClient.get_fee_quote", return_value={"gasPrice": "100"}),
    ):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        body = s.json()

        assert body["status"] == RunStatus.BLOCKED.value
        assert body["artifacts"]["decision"]["action"] == "BLOCK"


def test_start_run_plan_validation_failure_returns_500(client, monkeypatch):
    payload = {
        "intent": "Plan should fail",
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

    def bad_plan(_planner_input):
        return {"type": "plan", "actions": []}

    import importlib

    plan_tx_module = importlib.import_module("graph.nodes.plan_tx")
    if hasattr(plan_tx_module, "_plan_tx_stub"):
        monkeypatch.setattr(plan_tx_module, "_plan_tx_stub", bad_plan)
    else:
        monkeypatch.setattr("graph.nodes._plan_tx_stub", bad_plan)

    with patch("chain.client.ChainClient.wallet_snapshot", return_value=fake_snapshot):
        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 500, s.text


def test_start_run_native_transfer_plan_creates_candidate(client, monkeypatch):
    recipient = "0x2222222222222222222222222222222222222222"
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

        artifacts = body["artifacts"]
        assert artifacts["tx_plan"]["type"] == "plan"
        assert len(artifacts["tx_plan"]["candidates"]) == 1
        candidate = artifacts["tx_plan"]["candidates"][0]
        assert candidate["to"] == Web3.to_checksum_address(recipient)
        assert candidate["valueWei"] != "0"
        assert artifacts["decision"]["action"] == "NEEDS_APPROVAL"

    db = SessionLocal()
    try:
        run = get_run(db, run_id)
        assert run is not None
        persisted = run.artifacts.get("tx_plan", {})
        assert persisted["candidates"][0]["to"] == Web3.to_checksum_address(recipient)
    finally:
        db.close()


def test_start_run_native_transfer_accepts_extra_whitespace(client, monkeypatch):
    recipient = "0x3333333333333333333333333333333333333333"
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{recipient}\"]')
    get_settings.cache_clear()

    payload = {
        "intent": f"  send   0.0001   eth   to   {recipient}  ",
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

        artifacts = s.json()["artifacts"]
        assert artifacts["tx_plan"]["type"] == "plan"
        assert artifacts["tx_plan"]["candidates"][0]["to"] == Web3.to_checksum_address(recipient)


def test_start_run_native_transfer_rejects_scientific_notation(client, monkeypatch):
    recipient = "0x4444444444444444444444444444444444444444"
    monkeypatch.setenv("ALLOWLIST_TO", f'[\"{recipient}\"]')
    get_settings.cache_clear()

    payload = {
        "intent": f"send 1e-4 eth to {recipient}",
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

        artifacts = s.json()["artifacts"]
        assert artifacts["tx_plan"]["type"] == "noop"


def test_start_run_judge_verdict_mapping(client, monkeypatch):
    payload = {
        "intent": "Judge mapping test",
        "walletAddress": VALID_WALLET,
        "chainId": 1,
    }
    verdict_cases = [
        ("PASS", RunStatus.AWAITING_APPROVAL.value),
        ("NEEDS_REWORK", RunStatus.AWAITING_APPROVAL.value),
        ("BLOCK", RunStatus.BLOCKED.value),
    ]

    for verdict, expected in verdict_cases:
        r = client.post("/v1/runs", json=payload)
        assert r.status_code == 200
        run_id = r.json()["runId"]

        artifacts = {
            "decision": {"action": "NEEDS_APPROVAL"},
            "judge_result": {"output": {"verdict": verdict}},
        }

        def fake_run_graph(_db, _state, *, _artifacts=artifacts):
            return {"artifacts": _artifacts}

        monkeypatch.setattr("api.v1.run_execution.run_graph", fake_run_graph)

        s = client.post(f"/v1/runs/{run_id}/start")
        assert s.status_code == 200, s.text
        assert s.json()["status"] == expected
