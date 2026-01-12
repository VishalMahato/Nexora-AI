from __future__ import annotations

from eth_abi import encode as encode_abi

from defi.compiler_uniswap_v2 import compile_uniswap_v2_plan


def test_compile_uniswap_v2_approve_and_swap():
    allowlisted_tokens = {
        "USDC": {
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "decimals": 6,
        },
        "ETH": {
            "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "decimals": 18,
            "is_native": True,
        },
    }
    allowlisted_routers = {
        "UNISWAP_V2_ROUTER": {
            "address": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
        }
    }

    actions = [
        {
            "action": "APPROVE",
            "token": "USDC",
            "spender": "UNISWAP_V2_ROUTER",
            "amount": "20",
        },
        {
            "action": "SWAP",
            "token_in": "USDC",
            "token_out": "ETH",
            "amount_in": "20",
            "slippage_bps": 50,
            "recipient": "0x1111111111111111111111111111111111111111",
            "router_key": "UNISWAP_V2_ROUTER",
            "deadline_seconds": 1200,
        },
    ]

    def fake_get_amounts_out(_router_address, _data):
        encoded = encode_abi(["uint256[]"], [[20000000, 2000000]]).hex()
        return "0x" + encoded

    tx_requests, candidates, quotes = compile_uniswap_v2_plan(
        chain_id=1,
        actions=actions,
        wallet_address="0x1111111111111111111111111111111111111111",
        allowlisted_tokens=allowlisted_tokens,
        allowlisted_routers=allowlisted_routers,
        get_amounts_out=fake_get_amounts_out,
        block_number=123,
        default_slippage_bps=50,
        default_deadline_seconds=1200,
        now_ts=1700000000,
    )

    assert len(tx_requests) == 2
    assert len(candidates) == 2
    assert quotes[0]["minOut"] == "1990000"
    assert tx_requests[0]["meta"]["kind"] == "APPROVE"
    assert tx_requests[1]["meta"]["kind"] == "SWAP"
    assert tx_requests[1]["meta"]["minOut"] == "1990000"


def test_compile_uniswap_v2_swap_base_units_guard():
    allowlisted_tokens = {
        "USDC": {
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "decimals": 6,
        },
        "WETH": {
            "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "decimals": 18,
        },
    }
    allowlisted_routers = {
        "UNISWAP_V2_ROUTER": {
            "address": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
        }
    }

    actions = [
        {
            "action": "SWAP",
            "token_in": "USDC",
            "token_out": "WETH",
            "amount_in": "1000000",
            "slippage_bps": 50,
            "recipient": "0x1111111111111111111111111111111111111111",
            "router_key": "UNISWAP_V2_ROUTER",
            "deadline_seconds": 1200,
        },
    ]

    def fake_get_amounts_out(_router_address, _data):
        encoded = encode_abi(["uint256[]"], [[1000000, 990000]]).hex()
        return "0x" + encoded

    tx_requests, candidates, quotes = compile_uniswap_v2_plan(
        chain_id=1,
        actions=actions,
        wallet_address="0x1111111111111111111111111111111111111111",
        allowlisted_tokens=allowlisted_tokens,
        allowlisted_routers=allowlisted_routers,
        get_amounts_out=fake_get_amounts_out,
        block_number=123,
        default_slippage_bps=50,
        default_deadline_seconds=1200,
        now_ts=1700000000,
    )

    assert len(tx_requests) == 1
    assert len(candidates) == 1
    assert quotes[0]["amountIn"] == "1000000"
    assert tx_requests[0]["meta"]["amountInBaseUnits"] == "1000000"
    assert tx_requests[0]["meta"]["amountInSource"] == "base_units_heuristic"
