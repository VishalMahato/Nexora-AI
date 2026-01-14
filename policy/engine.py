# policy/engine.py
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple

from policy.rules import (
    rule_allowlist_targets,
    rule_no_signing_broadcast_invariant,
    rule_simulation_success,
    rule_required_artifacts_present,  
    rule_defi_allowlists,
    rule_approve_amount_sane,
    rule_swap_slippage_bounds,
    rule_swap_min_out_present,
)

from policy.types import (
    CheckStatus,
    Decision,
    DecisionAction,
    PolicyCheckResult,
    PolicyResult,
    Severity,
)


def _severity_from_score(score: int, has_fail: bool) -> Severity:
    if has_fail:
        return Severity.HIGH
    if score >= 60:
        return Severity.HIGH
    if score >= 25:
        return Severity.MED
    return Severity.LOW


def _score_checks(checks) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    for c in checks:
        if c.status == CheckStatus.WARN:
            # Simple MVP weights (tweak later)
            score += 15
            reasons.append(f"{c.title}: {c.reason or 'Warning'}")
        elif c.status == CheckStatus.FAIL:
            # FAILs handled separately (BLOCK)
            reasons.append(f"{c.title}: {c.reason or 'Failed'}")
    return min(score, 100), reasons


def evaluate_policies(
    artifacts: Dict[str, Any],
    *,
    allowlisted_to: Set[str] | None = None,
    allowlisted_tokens: Dict[str, Any] | None = None,
    allowlisted_routers: Dict[str, Any] | None = None,
    allowlist_targets_enabled: bool = True,
    min_slippage_bps: int = 10,
    max_slippage_bps: int = 200,
) -> Tuple[PolicyResult, Decision]:
    allowlisted_to = {a.lower() for a in (allowlisted_to or set())}
    allowlisted_tokens = allowlisted_tokens or {}
    allowlisted_routers = allowlisted_routers or {}

    checks = [
        rule_required_artifacts_present(artifacts),   
        rule_no_signing_broadcast_invariant(artifacts),
    ]

    if allowlist_targets_enabled:
        # Extend target allowlist with DeFi addresses so candidates from tx_requests
        # do not fail the generic allowlist check.
        allowlisted_to_extended = set(allowlisted_to)
        for meta in allowlisted_tokens.values():
            if isinstance(meta, dict) and meta.get("address"):
                allowlisted_to_extended.add(str(meta["address"]).lower())
        for meta in allowlisted_routers.values():
            if isinstance(meta, str):
                allowlisted_to_extended.add(meta.lower())
            elif isinstance(meta, dict) and meta.get("address"):
                allowlisted_to_extended.add(str(meta["address"]).lower())

        checks.append(
            rule_allowlist_targets(artifacts, allowlisted_to=allowlisted_to_extended)
        )
    else:
        checks.append(
            PolicyCheckResult(
                id="allowlist_targets",
                title="Allowlist: transaction targets",
                status=CheckStatus.PASS,
                reason="Target allowlist disabled by config.",
            )
        )

    checks.extend([
        rule_defi_allowlists(
            artifacts,
            allowlisted_tokens=allowlisted_tokens,
            allowlisted_routers=allowlisted_routers,
        ),
        rule_approve_amount_sane(artifacts),
        rule_swap_slippage_bounds(artifacts, min_bps=min_slippage_bps, max_bps=max_slippage_bps),
        rule_swap_min_out_present(artifacts),
        rule_simulation_success(artifacts),
    ])

    result = PolicyResult(checks=checks)

    has_fail = any(c.status == CheckStatus.FAIL for c in checks)
    score, reasons = _score_checks(checks)

    if has_fail:
        decision = Decision(
            action=DecisionAction.BLOCK,
            risk_score=100,
            severity=Severity.HIGH,
            summary="Blocked: one or more required safety checks failed.",
            reasons=reasons,
        )
        return result, decision

    # MVP: even if everything passes, we still require human approval.
    decision = Decision(
        action=DecisionAction.NEEDS_APPROVAL,
        risk_score=score,
        severity=_severity_from_score(score, has_fail=False),
        summary="Ready for review: policy checks completed.",
        reasons=reasons,
    )
    return result, decision
