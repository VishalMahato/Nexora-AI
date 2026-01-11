from __future__ import annotations

from typing import Any

from app.config import get_settings
from chain.snapshot import fetch_wallet_snapshot


def _allowlisted_token_addresses(tokens: dict[str, dict[str, Any]]) -> list[str]:
    token_addresses = []
    for meta in (tokens or {}).values():
        if not isinstance(meta, dict):
            continue
        if meta.get("is_native"):
            continue
        address = meta.get("address")
        if address:
            token_addresses.append(address)
    return token_addresses


def _allowlisted_router_addresses(routers: dict[str, Any]) -> list[str]:
    router_addresses = []
    for meta in (routers or {}).values():
        if isinstance(meta, str):
            router_addresses.append(meta)
        elif isinstance(meta, dict) and meta.get("address"):
            router_addresses.append(meta["address"])
    return router_addresses


def get_allowlists(chain_id: int) -> dict[str, Any]:
    settings = get_settings()
    tokens = settings.allowlisted_tokens_for_chain(chain_id)
    routers = settings.allowlisted_routers_for_chain(chain_id)
    return {
        "chain_id": chain_id,
        "tokens": tokens,
        "routers": routers,
    }


def get_wallet_snapshot(wallet_address: str, chain_id: int) -> dict[str, Any]:
    settings = get_settings()
    allowlisted_tokens = settings.allowlisted_tokens_for_chain(chain_id)
    allowlisted_routers = settings.allowlisted_routers_for_chain(chain_id)

    token_addresses = _allowlisted_token_addresses(allowlisted_tokens)
    router_addresses = _allowlisted_router_addresses(allowlisted_routers)

    allowances = []
    for token in token_addresses:
        for router in router_addresses:
            allowances.append({"token": token, "spender": router})

    return fetch_wallet_snapshot(
        chain_id=chain_id,
        wallet_address=wallet_address,
        erc20_tokens=token_addresses,
        allowances=allowances,
    )


def get_token_balance(wallet_address: str, chain_id: int, token_symbol: str) -> dict[str, Any]:
    snapshot = get_wallet_snapshot(wallet_address, chain_id)
    token_symbol_upper = token_symbol.strip().upper()

    for token in snapshot.get("erc20", []):
        if str(token.get("symbol", "")).upper() == token_symbol_upper:
            return {
                "symbol": token.get("symbol"),
                "balance": token.get("balance"),
                "decimals": token.get("decimals"),
                "token": token.get("token"),
            }

    return {
        "symbol": token_symbol_upper,
        "balance": None,
        "decimals": None,
        "token": None,
    }
