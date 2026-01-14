# Security and Safety

## Core Invariants

- Backend never signs transactions.
- Backend never broadcasts transactions.
- All actions are subject to allowlists.
- Simulation is required before approval.
- Human approval gate is mandatory.

## Allowlists

Allowlisted tokens and routers are configured in:

- `ALLOWLISTED_TOKENS`
- `ALLOWLISTED_ROUTERS`
- `ALLOWLIST_TO`

Notes:

- Any token or router not on the allowlist is blocked.
- Allowlists are evaluated in policy rules and compiler checks.
- `ALLOWLIST_TO_ALL=true` disables the target allowlist check (dev only).

## Policy Checks (Current)

The policy engine enforces:

- Required artifacts present
- No broadcast invariant
- Allowlist targets
- DeFi allowlists (tokens and routers)
- Approve amount sanity (no unlimited approvals)
- Swap slippage bounds
- Swap minOut presence
- Simulation success (WARN on assumed_success)

Each check produces:

```
{ id, title, status, reason, metadata }
```

## Simulation Safety

Simulation rules:

- Approve tx must succeed.
- Swap tx may be marked `assumed_success` only if:
  - An approve exists for the same token and spender.
  - Wallet balance is sufficient.
  - Error indicates allowance not applied in stateless sim.
- Assumed success triggers WARN, not PASS.

## Approval Gate

- Runs stop at `AWAITING_APPROVAL`.
- The frontend is responsible for showing tx_requests and requiring user
  confirmation.

## Error Transparency

- Every failure is recorded in `policy_result` and `decision.reasons`.
- `judge_result` provides a human-readable explanation.

## Safety Defaults

When LLM output is invalid:

- Planner falls back to noop plan.
- Judge falls back to WARN and requires manual review.
- Chat defaults to CLARIFY or GENERAL with safe prompts.

## Security Boundaries

- Backend is read-only for chain state.
- Signing keys must never be stored server-side.
- All RPC interactions are idempotent.

## Auditability

- Each run stores timeline entries for every step.
- Artifacts include source lists and timestamps.
