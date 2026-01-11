from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, List, Tuple

from eth_abi import decode as decode_abi
from web3 import Web3

from chain.abis import ERC20_ABI


UNISWAP_V2_ROUTER_ABI: list[dict[str, Any]] = [
    {
        "name": "getAmountsOut",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
    },
    {
        "name": "swapExactTokensForTokens",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
    },
    {
        "name": "swapExactTokensForETH",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
    },
]


MAX_UINT256 = (1 << 256) - 1


@dataclass
class TokenMeta:
    symbol: str
    address: str
    decimals: int
    is_native: bool = False


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _token_meta(allowlisted_tokens: dict[str, dict[str, Any]], symbol: str) -> TokenMeta:
    lookup = {k.upper(): v for k, v in (allowlisted_tokens or {}).items()}
    meta = lookup.get(_normalize_symbol(symbol))
    if not meta:
        raise ValueError(f"token not allowlisted: {symbol}")
    address = meta.get("address")
    decimals = meta.get("decimals")
    if not address or decimals is None:
        raise ValueError(f"invalid token metadata for {symbol}")
    return TokenMeta(
        symbol=_normalize_symbol(symbol),
        address=Web3.to_checksum_address(address),
        decimals=int(decimals),
        is_native=bool(meta.get("is_native")),
    )


def _router_address(allowlisted_routers: dict[str, Any], router_key: str | None) -> Tuple[str, str]:
    if not allowlisted_routers:
        raise ValueError("no allowlisted routers configured")
    if router_key:
        meta = allowlisted_routers.get(router_key) or allowlisted_routers.get(router_key.upper())
        if meta is None:
            raise ValueError(f"router not allowlisted: {router_key}")
        if isinstance(meta, str):
            return router_key, Web3.to_checksum_address(meta)
        if isinstance(meta, dict) and meta.get("address"):
            return router_key, Web3.to_checksum_address(meta["address"])
        raise ValueError(f"invalid router metadata for {router_key}")

    first_key = sorted(allowlisted_routers.keys())[0]
    meta = allowlisted_routers[first_key]
    if isinstance(meta, str):
        return first_key, Web3.to_checksum_address(meta)
    if isinstance(meta, dict) and meta.get("address"):
        return first_key, Web3.to_checksum_address(meta["address"])
    raise ValueError("invalid router metadata")


def _to_base_units(amount_str: str, decimals: int) -> str:
    try:
        dec = Decimal(amount_str)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"invalid amount: {amount_str}") from exc
    if dec <= 0:
        raise ValueError(f"amount must be positive: {amount_str}")
    quant = Decimal(10) ** decimals
    base_units = int((dec * quant).to_integral_value(rounding=ROUND_DOWN))
    if base_units <= 0:
        raise ValueError("amount too small after decimals conversion")
    return str(base_units)


def _erc20_approve_data(token_address: str, spender: str, amount: str) -> str:
    w3 = Web3()
    contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
    return contract.encode_abi("approve", args=[Web3.to_checksum_address(spender), int(amount)])


def _router_contract(router_address: str):
    w3 = Web3()
    return w3.eth.contract(address=Web3.to_checksum_address(router_address), abi=UNISWAP_V2_ROUTER_ABI)


def _encode_get_amounts_out(router_address: str, amount_in: str, path: list[str]) -> str:
    contract = _router_contract(router_address)
    return contract.encode_abi("getAmountsOut", args=[int(amount_in), path])


def _decode_amounts_out(output_hex: str) -> list[str]:
    if not output_hex or not isinstance(output_hex, str):
        raise ValueError("empty getAmountsOut response")
    data = output_hex[2:] if output_hex.startswith("0x") else output_hex
    raw = bytes.fromhex(data)
    decoded = decode_abi(["uint256[]"], raw)[0]
    return [str(int(x)) for x in decoded]


def _encode_swap(
    *,
    router_address: str,
    amount_in: str,
    min_out: str,
    path: list[str],
    recipient: str,
    deadline: int,
    token_out_is_native: bool,
) -> str:
    contract = _router_contract(router_address)
    fn_name = "swapExactTokensForETH" if token_out_is_native else "swapExactTokensForTokens"
    return contract.encode_abi(
        fn_name,
        args=[int(amount_in), int(min_out), path, Web3.to_checksum_address(recipient), int(deadline)],
    )


def compile_uniswap_v2_plan(
    *,
    chain_id: int,
    actions: list[dict[str, Any]],
    wallet_address: str,
    allowlisted_tokens: dict[str, dict[str, Any]],
    allowlisted_routers: dict[str, Any],
    get_amounts_out: callable,
    block_number: int | None,
    default_slippage_bps: int,
    default_deadline_seconds: int,
    now_ts: int,
) -> Tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (tx_requests, candidates, quotes).
    """
    tx_requests: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    quotes: list[dict[str, Any]] = []

    approve_idx = 0
    swap_idx = 0

    for action in actions:
        action_type = action.get("action")
        if action_type == "APPROVE":
            approve_idx += 1
            token_symbol = action.get("token") or ""
            spender_key = action.get("spender")
            amount_str = action.get("amount") or ""

            token_meta = _token_meta(allowlisted_tokens, token_symbol)
            router_key, router_address = _router_address(allowlisted_routers, spender_key)
            amount_base_units = _to_base_units(amount_str, token_meta.decimals)

            if int(amount_base_units) >= MAX_UINT256:
                raise ValueError("approve amount exceeds maximum safe value")

            data = _erc20_approve_data(token_meta.address, router_address, amount_base_units)
            tx_request = {
                "txRequestId": f"approve-{approve_idx}",
                "chainId": chain_id,
                "to": token_meta.address,
                "data": data,
                "valueWei": "0",
                "meta": {
                    "kind": "APPROVE",
                    "token": token_meta.symbol,
                    "spender": router_key,
                    "amount": amount_str,
                    "amountBaseUnits": amount_base_units,
                },
            }
            candidate = {
                "chain_id": chain_id,
                "to": token_meta.address,
                "data": data,
                "valueWei": "0",
                "meta": tx_request["meta"],
            }
            tx_requests.append(tx_request)
            candidates.append(candidate)
            continue

        if action_type == "SWAP":
            swap_idx += 1
            token_in_symbol = action.get("token_in") or ""
            token_out_symbol = action.get("token_out") or ""
            amount_in_str = action.get("amount_in") or ""

            slippage_bps = action.get("slippage_bps")
            if slippage_bps is None:
                slippage_bps = default_slippage_bps
            slippage_bps = int(slippage_bps)

            deadline_seconds = action.get("deadline_seconds")
            if deadline_seconds is None:
                deadline_seconds = default_deadline_seconds
            deadline_seconds = int(deadline_seconds)
            deadline = now_ts + deadline_seconds

            router_key = action.get("router_key")
            recipient = action.get("recipient") or wallet_address

            token_in_meta = _token_meta(allowlisted_tokens, token_in_symbol)
            token_out_meta = _token_meta(allowlisted_tokens, token_out_symbol)
            router_key, router_address = _router_address(allowlisted_routers, router_key)

            amount_in_base_units = _to_base_units(amount_in_str, token_in_meta.decimals)
            path = [token_in_meta.address, token_out_meta.address]

            call_data = _encode_get_amounts_out(router_address, amount_in_base_units, path)
            raw_out = get_amounts_out(router_address, call_data)
            amounts_out = _decode_amounts_out(raw_out)
            min_out = str(int(int(amounts_out[-1]) * (10_000 - slippage_bps) // 10_000))

            quote = {
                "router": router_address,
                "routerKey": router_key,
                "path": path,
                "amountIn": amount_in_base_units,
                "amountsOut": amounts_out,
                "minOut": min_out,
                "slippageBps": slippage_bps,
                "blockNumber": block_number,
            }
            quotes.append(quote)

            data = _encode_swap(
                router_address=router_address,
                amount_in=amount_in_base_units,
                min_out=min_out,
                path=path,
                recipient=recipient,
                deadline=deadline,
                token_out_is_native=token_out_meta.is_native,
            )

            tx_request = {
                "txRequestId": f"swap-{swap_idx}",
                "chainId": chain_id,
                "to": router_address,
                "data": data,
                "valueWei": "0",
                "meta": {
                    "kind": "SWAP",
                    "tokenIn": token_in_meta.symbol,
                    "tokenOut": token_out_meta.symbol,
                    "amountIn": amount_in_str,
                    "amountInBaseUnits": amount_in_base_units,
                    "minOut": min_out,
                    "slippageBps": slippage_bps,
                    "deadlineSeconds": deadline_seconds,
                    "routerKey": router_key,
                },
            }
            candidate = {
                "chain_id": chain_id,
                "to": router_address,
                "data": data,
                "valueWei": "0",
                "meta": tx_request["meta"],
            }
            tx_requests.append(tx_request)
            candidates.append(candidate)
            continue

    return tx_requests, candidates, quotes
