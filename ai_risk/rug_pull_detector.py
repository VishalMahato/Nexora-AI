from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from ai_risk.types import RugPullAnalysis, RugPullSignal


class RugPullDetector:
    def analyze(
        self,
        *,
        artifacts: Dict[str, Any],
        chain_id: int | None,
        allowlisted_tokens: Dict[str, Dict[str, Any]] | None = None,
    ) -> RugPullAnalysis:
        allowlisted_tokens = allowlisted_tokens or {}
        signals: List[RugPullSignal] = []

        tx_plan = artifacts.get("tx_plan") or {}
        actions = tx_plan.get("actions") if isinstance(tx_plan, dict) else None
        actions = actions if isinstance(actions, list) else []

        allowed_symbols, allowed_addresses = _build_allowlists(allowlisted_tokens)

        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = (action.get("action") or "").upper()
            if action_type != "SWAP":
                continue
            token_in = _coerce_token(action.get("token_in") or action.get("tokenIn"))
            token_out = _coerce_token(action.get("token_out") or action.get("tokenOut"))
            for label, token in (("token_in", token_in), ("token_out", token_out)):
                if not token:
                    continue
                if _is_allowed_token(token, allowed_symbols, allowed_addresses):
                    continue
                signals.append(
                    RugPullSignal(
                        name="unrecognized_token",
                        severity="MED",
                        detail=f"Swap includes {label} {token} outside allowlisted tokens.",
                    )
                )

        simulation = artifacts.get("simulation") or {}
        simulation_signals = _signals_from_simulation(simulation)
        signals.extend(simulation_signals)

        flagged = any(sig.severity in {"MED", "HIGH"} for sig in signals)
        if not signals:
            summary = "No rug pull indicators detected."
        elif flagged:
            summary = "Potential rug pull indicators detected."
        else:
            summary = "Minor rug pull indicators detected."

        confidence = _confidence_from_signals(signals)

        return RugPullAnalysis(
            flagged=flagged,
            confidence=confidence,
            summary=summary,
            signals=signals,
        )


def _build_allowlists(
    allowlisted_tokens: Dict[str, Dict[str, Any]]
) -> Tuple[set[str], set[str]]:
    symbols = {str(key).upper() for key in allowlisted_tokens.keys()}
    addresses = set()
    for meta in allowlisted_tokens.values():
        if not isinstance(meta, dict):
            continue
        address = meta.get("address")
        if address:
            addresses.add(str(address).lower())
    return symbols, addresses


def _coerce_token(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _is_allowed_token(
    token: str,
    allowed_symbols: Iterable[str],
    allowed_addresses: Iterable[str],
) -> bool:
    token_upper = token.upper()
    token_lower = token.lower()
    if token_upper in allowed_symbols:
        return True
    if token_lower in allowed_addresses:
        return True
    return False


def _signals_from_simulation(simulation: Dict[str, Any]) -> List[RugPullSignal]:
    if not isinstance(simulation, dict):
        return []
    results = simulation.get("results") or []
    if not isinstance(results, list):
        return []
    signals: List[RugPullSignal] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        if result.get("success") is True:
            continue
        error = str(result.get("error") or "").lower()
        if not error:
            continue
        if any(
            pattern in error
            for pattern in (
                "transfer_from_failed",
                "transfer failed",
                "transfer amount exceeds",
                "insufficient liquidity",
                "execution reverted",
                "erc20: transfer",
            )
        ):
            signals.append(
                RugPullSignal(
                    name="simulation_reverted",
                    severity="HIGH",
                    detail="Simulation reverted during token transfer/swap.",
                )
            )
    return signals


def _confidence_from_signals(signals: List[RugPullSignal]) -> float | None:
    if not signals:
        return 0.1
    high = sum(1 for sig in signals if sig.severity == "HIGH")
    med = sum(1 for sig in signals if sig.severity == "MED")
    score = min(1.0, 0.2 + 0.3 * high + 0.15 * med)
    return round(score, 2)
