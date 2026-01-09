from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from web3 import Web3

from tools.tool_runner import run_tool
from chain import rpc


class ChainClient:
    """
    High-level Web3 client (in-repo) that:
    - Calls RPC via chain.rpc
    - Instruments all calls via tools.run_tool (ToolCalls DB table)
    - Returns JSON-serializable dict outputs
    """

    # ---------------------------
    # Wallet snapshot
    # ---------------------------

    def wallet_snapshot(
        self,
        *,
        db: Session,
        run_id,
        step_id,
        chain_id: int,
        wallet_address: str,
        erc20_tokens: list[str] | None = None,
        allowances: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Snapshot wallet:
        - native balance (wei)
        - optional ERC20 balances for provided token addresses
        - optional allowances for provided (token, spender) pairs

        allowances item format:
          {"token": "0x...", "spender": "0x..."}
        """
        wallet = Web3.to_checksum_address(wallet_address)

        native_balance_wei = run_tool(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name="web3.eth_getBalance",
            request={"chainId": chain_id, "walletAddress": wallet},
            fn=lambda: int(rpc.get_native_balance(chain_id, wallet)),
        )

        token_balances: list[dict[str, Any]] = []
        for token in (erc20_tokens or []):
            token_cs = Web3.to_checksum_address(token)

            bal = run_tool(
                db,
                run_id=run_id,
                step_id=step_id,
                tool_name="web3.erc20.balanceOf",
                request={
                    "chainId": chain_id,
                    "token": token_cs,
                    "owner": wallet,
                },
                fn=lambda token_addr=token_cs: int(
                    rpc.erc20_balance(chain_id, token_addr, wallet)
                ),
            )

            decimals = run_tool(
                db,
                run_id=run_id,
                step_id=step_id,
                tool_name="web3.erc20.decimals",
                request={"chainId": chain_id, "token": token_cs},
                fn=lambda token_addr=token_cs: int(rpc.erc20_decimals(chain_id, token_addr)),
            )

            symbol = run_tool(
                db,
                run_id=run_id,
                step_id=step_id,
                tool_name="web3.erc20.symbol",
                request={"chainId": chain_id, "token": token_cs},
                fn=lambda token_addr=token_cs: str(rpc.erc20_symbol(chain_id, token_addr)),
            )

            token_balances.append(
                {
                    "token": token_cs,
                    "symbol": symbol,
                    "decimals": decimals,
                    "balance": str(bal),  # store as string for JSON safety
                }
            )

        allowance_rows: list[dict[str, Any]] = []
        for item in (allowances or []):
            token = Web3.to_checksum_address(item["token"])
            spender = Web3.to_checksum_address(item["spender"])

            allowance_val = run_tool(
                db,
                run_id=run_id,
                step_id=step_id,
                tool_name="web3.erc20.allowance",
                request={
                    "chainId": chain_id,
                    "token": token,
                    "owner": wallet,
                    "spender": spender,
                },
                fn=lambda token_addr=token, sp=spender: int(
                    rpc.erc20_allowance(chain_id, token_addr, wallet, sp)
                ),
            )

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

    # ---------------------------
    # Tx builders (templates only)
    # ---------------------------

    def build_approve_tx(
        self,
        *,
        chain_id: int,
        owner: str,
        token: str,
        spender: str,
        amount: str,
    ) -> dict[str, Any]:
        """
        Build a basic ERC20 approve tx dict template.

        NOTE: This does NOT sign or send.
        You can simulate it with simulate_tx().
        """
        owner_cs = Web3.to_checksum_address(owner)
        token_cs = Web3.to_checksum_address(token)
        spender_cs = Web3.to_checksum_address(spender)

        # Build calldata for approve(spender, amount)
        # We avoid needing a full ABI here by using the contract helper from rpc module.
        contract = rpc._erc20_contract(chain_id, token_cs)  # internal helper OK within package
        data = contract.encodeABI(fn_name="approve", args=[spender_cs, int(amount)])

        return {
            "from": owner_cs,
            "to": token_cs,
            "data": data,
            "value": "0",
            # gas fields intentionally omitted (filled by estimate_gas)
        }

    def build_swap_tx(self, **kwargs) -> dict[str, Any]:
        """
        Placeholder for swap tx building.
        Real swap building needs a DEX router integration (Uniswap, 0x, etc).
        For MVP F11, we keep it as a stub/template.
        """
        return {
            "type": "UNIMPLEMENTED_SWAP_TEMPLATE",
            "note": "Swap tx builder not implemented in F11 MVP. Add DEX integration later.",
            "input": kwargs,
        }

    # ---------------------------
    # Simulation
    # ---------------------------

    def _normalize_tx_dict(self, tx: dict[str, Any]) -> dict[str, Any]:
        tx_norm: dict[str, Any] = dict(tx)
        if "from" in tx_norm and isinstance(tx_norm["from"], str):
            tx_norm["from"] = Web3.to_checksum_address(tx_norm["from"])
        if "to" in tx_norm and isinstance(tx_norm["to"], str):
            tx_norm["to"] = Web3.to_checksum_address(tx_norm["to"])
        if "value" in tx_norm and isinstance(tx_norm["value"], str):
            tx_norm["value"] = int(tx_norm["value"])
        return tx_norm

    def eth_call(
        self,
        *,
        db: Session,
        run_id,
        step_id,
        chain_id: int,
        tx: dict[str, Any],
    ) -> str:
        tx_norm = self._normalize_tx_dict(tx)
        result = run_tool(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name="rpc.eth_call",
            request={"chainId": chain_id, "tx": tx},
            fn=lambda: rpc.eth_call(chain_id, tx_norm),
        )
        if isinstance(result, (bytes, bytearray)):
            return "0x" + result.hex()
        return str(result)

    def estimate_gas(
        self,
        *,
        db: Session,
        run_id,
        step_id,
        chain_id: int,
        tx: dict[str, Any],
    ) -> int:
        tx_norm = self._normalize_tx_dict(tx)
        return run_tool(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name="rpc.estimate_gas",
            request={"chainId": chain_id, "tx": tx},
            fn=lambda: int(rpc.estimate_gas(chain_id, tx_norm)),
        )

    def get_fee_quote(
        self,
        *,
        db: Session,
        run_id,
        step_id,
        chain_id: int,
    ) -> dict[str, Any]:
        fee_quote = run_tool(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name="rpc.fee_quote",
            request={"chainId": chain_id},
            fn=lambda: rpc.get_fee_quote(chain_id),
        )
        return {k: str(v) for k, v in fee_quote.items()}

    def simulate_tx(
        self,
        *,
        db: Session,
        run_id,
        step_id,
        chain_id: int,
        tx: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Simulate a tx using:
        - eth_call (for revert detection / return data)
        - estimateGas (for gas estimate)

        Returns JSON-safe fields.
        """
        # Normalize checksum addresses if present
        tx_norm = self._normalize_tx_dict(tx)

        call_result = run_tool(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name="web3.eth_call",
            request={"chainId": chain_id, "tx": tx},
            fn=lambda: rpc.eth_call(chain_id, tx_norm),
        )

        gas_estimate = run_tool(
            db,
            run_id=run_id,
            step_id=step_id,
            tool_name="web3.estimate_gas",
            request={"chainId": chain_id, "tx": tx},
            fn=lambda: int(rpc.estimate_gas(chain_id, tx_norm)),
        )

        # call_result is bytes; return hex string for JSON
        return {
            "ok": True,
            "chainId": chain_id,
            "gasEstimate": str(gas_estimate),
            "callResult": call_result.hex() if isinstance(call_result, (bytes, bytearray)) else str(call_result),
        }
