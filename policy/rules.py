# policy/rules.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from policy.types import CheckStatus, PolicyCheckResult

MAX_UINT256 = (1 << 256) - 1


def _get_tx_candidates(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    tx_plan = artifacts.get("tx_plan") or {}
    # Support a few likely shapes without forcing schema changes:
    # - {"type": "noop"}  (current)
    # - {"txs": [...]}    (future)
    # - {"candidates": [...]} (future)
    if isinstance(tx_plan, dict):
        if tx_plan.get("type") == "noop":
            return []
        if isinstance(tx_plan.get("txs"), list):
            return tx_plan["txs"]
        if isinstance(tx_plan.get("candidates"), list):
            return tx_plan["candidates"]
    return []


def rule_allowlist_targets(
    artifacts: Dict[str, Any],
    allowlisted_to: Set[str],
) -> PolicyCheckResult:
    if not allowlisted_to:
        return PolicyCheckResult(
            id="allowlist_targets",
            title="Allowlist: transaction targets",
            status=CheckStatus.PASS,
            reason="Target allowlist is empty; skipping check.",
        )
    txs = _get_tx_candidates(artifacts)
    if not txs:
        return PolicyCheckResult(
            id="allowlist_targets",
            title="Allowlist: transaction targets",
            status=CheckStatus.PASS,
            reason="No transactions to validate (noop).",
        )

    bad: List[str] = []
    for tx in txs:
        to_addr = (tx.get("to") or "").lower()
        if to_addr and to_addr not in allowlisted_to:
            bad.append(to_addr)

    if bad:
        return PolicyCheckResult(
            id="allowlist_targets",
            title="Allowlist: transaction targets",
            status=CheckStatus.FAIL,
            reason="Transaction targets include non-allowlisted addresses.",
            metadata={"non_allowlisted_to": sorted(set(bad))},
        )

    return PolicyCheckResult(
        id="allowlist_targets",
        title="Allowlist: transaction targets",
        status=CheckStatus.PASS,
        reason="All transaction targets are allowlisted.",
    )


def rule_simulation_success(
    artifacts: Dict[str, Any],
) -> PolicyCheckResult:
    txs = _get_tx_candidates(artifacts)
    simulation = artifacts.get("simulation") or {}

    if not txs:
        return PolicyCheckResult(
            id="simulation_success",
            title="Simulation: must succeed",
            status=CheckStatus.PASS,
            reason="No transactions to simulate (noop).",
        )

    # Support shapes:
    # - {"status": "skipped"} (current)
    # - {"success": true/false, "error": "..."} (future)
    # - {"results": [{"success": ...}, ...]} (future)
    if simulation.get("status") == "skipped":
        return PolicyCheckResult(
            id="simulation_success",
            title="Simulation: must succeed",
            status=CheckStatus.WARN,
            reason="Simulation was skipped for a non-noop plan.",
        )

    if simulation.get("status") == "completed":
        results = simulation.get("results")
        if isinstance(results, list):
            failures = [r for r in results if r.get("success") is False]
            if failures:
                errors = [r.get("error") for r in failures if r.get("error")]
                return PolicyCheckResult(
                    id="simulation_success",
                    title="Simulation: must succeed",
                    status=CheckStatus.FAIL,
                    reason="Simulation failed/reverted.",
                    metadata={
                        "num_failed": len(failures),
                        "errors": errors[:3],
                    },
                )
            if results:
                return PolicyCheckResult(
                    id="simulation_success",
                    title="Simulation: must succeed",
                    status=CheckStatus.PASS,
                    reason="Simulation succeeded for all candidates.",
                )
            return PolicyCheckResult(
                id="simulation_success",
                title="Simulation: must succeed",
                status=CheckStatus.WARN,
                reason="Simulation completed without results.",
            )

    if "success" in simulation:
        if simulation.get("success") is True:
            return PolicyCheckResult(
                id="simulation_success",
                title="Simulation: must succeed",
                status=CheckStatus.PASS,
                reason="Simulation succeeded.",
            )
        return PolicyCheckResult(
            id="simulation_success",
            title="Simulation: must succeed",
            status=CheckStatus.FAIL,
            reason="Simulation failed/reverted.",
            metadata={"error": simulation.get("error")},
        )

    # If unknown structure, be conservative:
    return PolicyCheckResult(
        id="simulation_success",
        title="Simulation: must succeed",
        status=CheckStatus.WARN,
        reason="Simulation output format is unknown; cannot confirm success.",
    )


def rule_no_signing_broadcast_invariant(
    artifacts: Dict[str, Any],
) -> PolicyCheckResult:
    # MVP invariant: system must not attempt broadcast/signing.
    tx_plan = artifacts.get("tx_plan") or {}
    if isinstance(tx_plan, dict) and tx_plan.get("broadcast") is True:
        return PolicyCheckResult(
            id="no_broadcast",
            title="Invariant: no signing/broadcasting",
            status=CheckStatus.FAIL,
            reason="tx_plan requested broadcast, which is not allowed in MVP.",
        )
    return PolicyCheckResult(
        id="no_broadcast",
        title="Invariant: no signing/broadcasting",
        status=CheckStatus.PASS,
        reason="No signing/broadcasting requested.",
    )



def rule_required_artifacts_present(artifacts: Dict[str, Any]) -> PolicyCheckResult:
    required = ["wallet_snapshot", "tx_plan", "simulation"]
    missing = [k for k in required if k not in (artifacts or {})]

    if missing:
        return PolicyCheckResult(
            id="required_artifacts",
            title="Required artifacts present",
            status=CheckStatus.FAIL,
            reason="Missing required artifacts needed for safe evaluation.",
            metadata={"missing": missing},
        )

    return PolicyCheckResult(
        id="required_artifacts",
        title="Required artifacts present",
        status=CheckStatus.PASS,
        reason="All required artifacts are present.",
    )


def _get_tx_requests(artifacts: Dict[str, Any]) -> List[Dict[str, Any]]:
    tx_requests = artifacts.get("tx_requests") or []
    if isinstance(tx_requests, list):
        return [r for r in tx_requests if isinstance(r, dict)]
    return []


def rule_defi_allowlists(
    artifacts: Dict[str, Any],
    *,
    allowlisted_tokens: Dict[str, Any],
    allowlisted_routers: Dict[str, Any],
) -> PolicyCheckResult:
    tx_requests = _get_tx_requests(artifacts)
    if not tx_requests:
        return PolicyCheckResult(
            id="defi_allowlists",
            title="DeFi: tokens and routers allowlisted",
            status=CheckStatus.PASS,
            reason="No DeFi tx requests to validate.",
        )

    token_allowset = {k.upper() for k in (allowlisted_tokens or {}).keys()}
    router_allowset = {k.upper() for k in (allowlisted_routers or {}).keys()}

    violations: List[str] = []
    for tx in tx_requests:
        meta = tx.get("meta") or {}
        kind = (meta.get("kind") or "").upper()
        if kind == "APPROVE":
            token = (meta.get("token") or "").upper()
            router_key = (meta.get("spender") or meta.get("routerKey") or "").upper()
            if token and token not in token_allowset:
                violations.append(f"token:{token}")
            if router_key and router_key not in router_allowset:
                violations.append(f"router:{router_key}")
        elif kind == "SWAP":
            token_in = (meta.get("tokenIn") or "").upper()
            token_out = (meta.get("tokenOut") or "").upper()
            router_key = (meta.get("routerKey") or "").upper()
            if token_in and token_in not in token_allowset:
                violations.append(f"token_in:{token_in}")
            if token_out and token_out not in token_allowset:
                violations.append(f"token_out:{token_out}")
            if router_key and router_key not in router_allowset:
                violations.append(f"router:{router_key}")

    if violations:
        return PolicyCheckResult(
            id="defi_allowlists",
            title="DeFi: tokens and routers allowlisted",
            status=CheckStatus.FAIL,
            reason="DeFi actions include non-allowlisted token or router.",
            metadata={"violations": sorted(set(violations))},
        )

    return PolicyCheckResult(
        id="defi_allowlists",
        title="DeFi: tokens and routers allowlisted",
        status=CheckStatus.PASS,
        reason="All DeFi tokens and routers are allowlisted.",
    )


def rule_approve_amount_sane(artifacts: Dict[str, Any]) -> PolicyCheckResult:
    tx_requests = _get_tx_requests(artifacts)
    if not tx_requests:
        return PolicyCheckResult(
            id="approve_amount_sane",
            title="Approve: amount bounds",
            status=CheckStatus.PASS,
            reason="No approve tx requests to validate.",
        )

    invalid: List[str] = []
    for tx in tx_requests:
        meta = tx.get("meta") or {}
        if (meta.get("kind") or "").upper() != "APPROVE":
            continue
        amount = meta.get("amountBaseUnits")
        try:
            value = int(str(amount))
        except Exception:
            invalid.append("invalid_amount")
            continue
        if value <= 0:
            invalid.append("non_positive")
        if value >= MAX_UINT256:
            invalid.append("unlimited")

    if invalid:
        return PolicyCheckResult(
            id="approve_amount_sane",
            title="Approve: amount bounds",
            status=CheckStatus.FAIL,
            reason="Approve amount is unsafe or invalid.",
            metadata={"issues": sorted(set(invalid))},
        )

    return PolicyCheckResult(
        id="approve_amount_sane",
        title="Approve: amount bounds",
        status=CheckStatus.PASS,
        reason="Approve amounts are within safe bounds.",
    )


def rule_swap_slippage_bounds(
    artifacts: Dict[str, Any],
    *,
    min_bps: int,
    max_bps: int,
) -> PolicyCheckResult:
    tx_requests = _get_tx_requests(artifacts)
    if not tx_requests:
        return PolicyCheckResult(
            id="swap_slippage_bounds",
            title="Swap: slippage bounds",
            status=CheckStatus.PASS,
            reason="No swap tx requests to validate.",
        )

    violations: List[int] = []
    for tx in tx_requests:
        meta = tx.get("meta") or {}
        if (meta.get("kind") or "").upper() != "SWAP":
            continue
        slippage = meta.get("slippageBps")
        if slippage is None:
            violations.append(-1)
            continue
        try:
            slippage_val = int(slippage)
        except Exception:
            violations.append(-1)
            continue
        if slippage_val < min_bps or slippage_val > max_bps:
            violations.append(slippage_val)

    if violations:
        return PolicyCheckResult(
            id="swap_slippage_bounds",
            title="Swap: slippage bounds",
            status=CheckStatus.FAIL,
            reason="Swap slippage is outside allowed bounds.",
            metadata={"violations": violations, "min_bps": min_bps, "max_bps": max_bps},
        )

    return PolicyCheckResult(
        id="swap_slippage_bounds",
        title="Swap: slippage bounds",
        status=CheckStatus.PASS,
        reason="Swap slippage is within allowed bounds.",
    )


def rule_swap_min_out_present(artifacts: Dict[str, Any]) -> PolicyCheckResult:
    tx_requests = _get_tx_requests(artifacts)
    if not tx_requests:
        return PolicyCheckResult(
            id="swap_min_out",
            title="Swap: min out present",
            status=CheckStatus.PASS,
            reason="No swap tx requests to validate.",
        )

    missing = []
    for tx in tx_requests:
        meta = tx.get("meta") or {}
        if (meta.get("kind") or "").upper() != "SWAP":
            continue
        min_out = meta.get("minOut")
        try:
            if min_out is None or int(str(min_out)) <= 0:
                missing.append(min_out)
        except Exception:
            missing.append(min_out)

    if missing:
        return PolicyCheckResult(
            id="swap_min_out",
            title="Swap: min out present",
            status=CheckStatus.FAIL,
            reason="Swap minOut is missing or invalid.",
        )

    return PolicyCheckResult(
        id="swap_min_out",
        title="Swap: min out present",
        status=CheckStatus.PASS,
        reason="Swap minOut is present.",
    )
