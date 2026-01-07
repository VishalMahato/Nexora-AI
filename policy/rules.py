# policy/rules.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from policy.types import CheckStatus, PolicyCheckResult


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