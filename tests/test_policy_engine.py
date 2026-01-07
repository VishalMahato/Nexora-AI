from policy.engine import evaluate_policies

def test_policy_engine_is_deterministic():
    artifacts = {
        "tx_plan": {"type": "noop", "candidates": []},
        "simulation": {"status": "skipped"},
        "wallet_snapshot": {"native": {"balanceWei": "123"}},
    }

    r1, d1 = evaluate_policies(artifacts, allowlisted_to=set())
    r2, d2 = evaluate_policies(artifacts, allowlisted_to=set())

    assert r1.model_dump() == r2.model_dump()
    assert d1.model_dump() == d2.model_dump()


def test_policy_blocks_when_required_artifacts_missing():
    artifacts = {
        "tx_plan": {"type": "noop", "candidates": []},
        # missing wallet_snapshot, simulation
    }

    policy_result, decision = evaluate_policies(artifacts, allowlisted_to=set())

    assert decision.action == "BLOCK"
    assert decision.risk_score == 100

    checks = policy_result.model_dump()["checks"]
    required = [c for c in checks if c["id"] == "required_artifacts"][0]
    assert required["status"] == "FAIL"
    assert "missing" in required["metadata"]
