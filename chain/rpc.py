from __future__ import annotations

from functools import lru_cache
from typing import Any

from web3 import Web3
from web3.exceptions import ContractLogicError

from chain.chains import get_rpc_url
from chain.abis import ERC20_ABI


class Web3RPCError(RuntimeError):
    pass


@lru_cache
def _get_web3(chain_id: int) -> Web3:
    """
    Lazily create and cache a Web3 instance per chain_id.
    """
    rpc_url = get_rpc_url(chain_id)
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if not w3.is_connected():
        raise Web3RPCError(f"Unable to connect to RPC for chain_id={chain_id}")

    return w3


# ---------------------------
# Native chain helpers
# ---------------------------

def get_native_balance(chain_id: int, address: str) -> int:
    """
    Return native token balance in wei.
    """
    w3 = _get_web3(chain_id)
    try:
        return w3.eth.get_balance(Web3.to_checksum_address(address))
    except Exception as e:
        raise Web3RPCError(f"get_native_balance failed: {e}") from e


# ---------------------------
# ERC20 helpers
# ---------------------------

def _erc20_contract(chain_id: int, token_address: str):
    w3 = _get_web3(chain_id)
    return w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI,
    )


def erc20_balance(chain_id: int, token_address: str, owner: str) -> int:
    """
    Return ERC20 balance (raw uint256).
    """
    try:
        contract = _erc20_contract(chain_id, token_address)
        return contract.functions.balanceOf(
            Web3.to_checksum_address(owner)
        ).call()
    except ContractLogicError as e:
        raise Web3RPCError(f"erc20_balance reverted: {e}") from e
    except Exception as e:
        raise Web3RPCError(f"erc20_balance failed: {e}") from e


def erc20_allowance(
    chain_id: int,
    token_address: str,
    owner: str,
    spender: str,
) -> int:
    """
    Return ERC20 allowance (raw uint256).
    """
    try:
        contract = _erc20_contract(chain_id, token_address)
        return contract.functions.allowance(
            Web3.to_checksum_address(owner),
            Web3.to_checksum_address(spender),
        ).call()
    except ContractLogicError as e:
        raise Web3RPCError(f"erc20_allowance reverted: {e}") from e
    except Exception as e:
        raise Web3RPCError(f"erc20_allowance failed: {e}") from e


def erc20_decimals(chain_id: int, token_address: str) -> int:
    """
    Return ERC20 decimals.
    """
    try:
        contract = _erc20_contract(chain_id, token_address)
        return contract.functions.decimals().call()
    except Exception as e:
        raise Web3RPCError(f"erc20_decimals failed: {e}") from e


def erc20_symbol(chain_id: int, token_address: str) -> str:
    """
    Return ERC20 symbol.
    """
    try:
        contract = _erc20_contract(chain_id, token_address)
        return contract.functions.symbol().call()
    except Exception as e:
        raise Web3RPCError(f"erc20_symbol failed: {e}") from e


# ---------------------------
# Simulation helpers
# ---------------------------

def eth_call(chain_id: int, tx: dict[str, Any]) -> bytes:
    """
    Perform eth_call (no state change).
    """
    w3 = _get_web3(chain_id)
    try:
        return w3.eth.call(tx)
    except ContractLogicError as e:
        raise Web3RPCError(f"eth_call reverted: {e}") from e
    except Exception as e:
        raise Web3RPCError(f"eth_call failed: {e}") from e


def estimate_gas(chain_id: int, tx: dict[str, Any]) -> int:
    """
    Estimate gas for a transaction dict.
    """
    w3 = _get_web3(chain_id)
    try:
        return w3.eth.estimate_gas(tx)
    except ContractLogicError as e:
        raise Web3RPCError(f"estimate_gas reverted: {e}") from e
    except Exception as e:
        raise Web3RPCError(f"estimate_gas failed: {e}") from e


def get_fee_quote(chain_id: int) -> dict[str, Any]:
    """
    Return either legacy gasPrice or EIP-1559 fee fields.
    """
    w3 = _get_web3(chain_id)
    try:
        block = w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas")
        if base_fee is not None:
            try:
                max_priority = w3.eth.max_priority_fee
            except Exception:
                max_priority = None

            if max_priority is None:
                gas_price = w3.eth.gas_price
                max_priority = max(gas_price - base_fee, 0)

            max_fee = base_fee + (max_priority * 2)
            return {
                "maxFeePerGas": int(max_fee),
                "maxPriorityFeePerGas": int(max_priority),
            }

        return {"gasPrice": int(w3.eth.gas_price)}
    except Exception as e:
        raise Web3RPCError(f"get_fee_quote failed: {e}") from e
