from __future__ import annotations

from typing import Any

from web3 import Web3

from chain import rpc


def fetch_wallet_snapshot(
    *,
    chain_id: int,
    wallet_address: str,
    erc20_tokens: list[str] | None = None,
    allowances: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Pure snapshot helper (no DB logging).
    """
    wallet = Web3.to_checksum_address(wallet_address)

    native_balance_wei = int(rpc.get_native_balance(chain_id, wallet))

    token_balances: list[dict[str, Any]] = []
    for token in (erc20_tokens or []):
        token_cs = Web3.to_checksum_address(token)

        bal = int(rpc.erc20_balance(chain_id, token_cs, wallet))
        decimals = int(rpc.erc20_decimals(chain_id, token_cs))
        symbol = str(rpc.erc20_symbol(chain_id, token_cs))

        token_balances.append(
            {
                "token": token_cs,
                "symbol": symbol,
                "decimals": decimals,
                "balance": str(bal),
            }
        )

    allowance_rows: list[dict[str, Any]] = []
    for item in (allowances or []):
        token = Web3.to_checksum_address(item["token"])
        spender = Web3.to_checksum_address(item["spender"])

        allowance_val = int(rpc.erc20_allowance(chain_id, token, wallet, spender))

        allowance_rows.append(
            {
                "token": token,
                "spender": spender,
                "allowance": str(allowance_val),
            }
        )

    return {
        "chainId": chain_id,
        "walletAddress": wallet,
        "native": {"balanceWei": str(native_balance_wei)},
        "erc20": token_balances,
        "allowances": allowance_rows,
    }
