from policy.engine import evaluate_policies


def test_policy_warns_on_assumed_simulation_success():
    artifacts = {
        "tx_plan": {"type": "plan", "candidates": []},
        "wallet_snapshot": {"native": {"balanceWei": "123"}},
        "tx_requests": [
            {
                "txRequestId": "approve-1",
                "meta": {
                    "kind": "APPROVE",
                    "token": "USDC",
                    "spender": "UNISWAP_V2_ROUTER",
                    "amountBaseUnits": "1000000",
                },
            },
            {
                "txRequestId": "swap-1",
                "meta": {
                    "kind": "SWAP",
                    "tokenIn": "USDC",
                    "tokenOut": "ETH",
                    "routerKey": "UNISWAP_V2_ROUTER",
                    "slippageBps": 50,
                    "minOut": "1",
                },
            },
        ],
        "simulation": {
            "status": "completed",
            "mode": "sequential",
            "results": [
                {
                    "txRequestId": "approve-1",
                    "success": True,
                    "assumed_success": False,
                },
                {
                    "txRequestId": "swap-1",
                    "success": True,
                    "assumed_success": True,
                    "assumption_reason": "ALLOWANCE_NOT_APPLIED_IN_SIMULATION",
                },
            ],
            "summary": {"num_success": 2, "num_failed": 0},
        },
    }

    policy_result, decision = evaluate_policies(
        artifacts,
        allowlisted_to=set(),
        allowlisted_tokens={
            "USDC": {"address": "0x1", "decimals": 6},
            "ETH": {"address": "0x2", "decimals": 18},
        },
        allowlisted_routers={"UNISWAP_V2_ROUTER": {"address": "0x3"}},
    )

    checks = policy_result.model_dump()["checks"]
    sim_check = [c for c in checks if c["id"] == "simulation_success"][0]
    assert sim_check["status"] == "WARN"
    assert decision.action != "BLOCK"
