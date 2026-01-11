from policy.engine import evaluate_policies


def test_policy_blocks_non_allowlisted_router():
    artifacts = {
        "tx_plan": {"type": "plan", "candidates": []},
        "simulation": {"status": "skipped"},
        "wallet_snapshot": {"native": {"balanceWei": "123"}},
        "tx_requests": [
            {
                "meta": {
                    "kind": "SWAP",
                    "tokenIn": "USDC",
                    "tokenOut": "ETH",
                    "routerKey": "BAD_ROUTER",
                    "slippageBps": 50,
                    "minOut": "1",
                }
            }
        ],
    }

    policy_result, decision = evaluate_policies(
        artifacts,
        allowlisted_to=set(),
        allowlisted_tokens={
            "USDC": {"address": "0x1", "decimals": 6},
            "ETH": {"address": "0x2", "decimals": 18},
        },
        allowlisted_routers={"UNISWAP_V2_ROUTER": {"address": "0x3"}},
        min_slippage_bps=10,
        max_slippage_bps=200,
    )

    assert decision.action == "BLOCK"
    checks = policy_result.model_dump()["checks"]
    assert any(c["id"] == "defi_allowlists" and c["status"] == "FAIL" for c in checks)
