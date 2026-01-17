# Demo-Safe Config and UI Prompts

## Purpose

Capture the minimum safe configuration and the UI prompt copy for demos so
operators and frontend teams have a single reference before going live.

## Scope

- Demo-safe backend configuration (environment variables).
- UI prompt copy aligned with run statuses and outcomes.
- Guardrails for approvals and execution.

## Demo-Safe Config (Baseline)

Use these defaults unless you have a specific reason to change them:

- `ALLOWLIST_TO_ALL=false`
- `ALLOWLIST_TO` set to explicit recipient addresses for the demo
- `ALLOWLISTED_TOKENS` set to the smallest possible list (example: USDC, WETH)
- `ALLOWLISTED_ROUTERS` set to a single router (example: Uniswap V2)
- `RPC_URLS` only for the chains in the allowlists
- `DEX_KIND=uniswap_v2`
- `DEFAULT_SLIPPAGE_BPS` within [`MIN_SLIPPAGE_BPS`, `MAX_SLIPPAGE_BPS`]
- `DEFAULT_DEADLINE_SECONDS=1200`
- `LLM_ENABLED=true` for demo planning, with:
  - `LLM_TEMPERATURE=0.0`
  - `LLM_CHAT_TEMPERATURE<=0.5`
  - `LLM_TIMEOUT_S=30`
- `SIMULATION_ASSUMED_SUCCESS_WARN=false` to avoid demo rework loops

If you do not want LLM variability at all, set `LLM_ENABLED=false` and use
deterministic fallbacks, but plan quality will be limited.

## Demo-Safe Config (Example)

```
ALLOWLIST_TO='["0x1111111111111111111111111111111111111111"]'
ALLOWLIST_TO_ALL=false
ALLOWLISTED_TOKENS='{"1":{"USDC":{"address":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48","decimals":6},"WETH":{"address":"0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2","decimals":18}}}'
ALLOWLISTED_ROUTERS='{"1":{"UNISWAP_V2_ROUTER":{"address":"0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"}}}'
RPC_URLS='{"1":"https://eth.llamarpc.com"}'
DEX_KIND=uniswap_v2
DEFAULT_SLIPPAGE_BPS=50
MIN_SLIPPAGE_BPS=10
MAX_SLIPPAGE_BPS=200
DEFAULT_DEADLINE_SECONDS=1200
LLM_ENABLED=true
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.0
LLM_CHAT_TEMPERATURE=0.5
LLM_TIMEOUT_S=30
SIMULATION_ASSUMED_SUCCESS_WARN=false
```

## What Can Go Wrong

- Empty or invalid `ALLOWLIST_TO` skips the target allowlist check.
- `ALLOWLIST_TO_ALL=true` disables target allowlist checks entirely.
- Missing tokens/routers in allowlists block swaps at policy eval.
- RPC URL missing for an allowed chain causes runtime errors.
- Unsupported `DEX_KIND` raises errors in `BUILD_TXS`.
- Slippage defaults outside bounds cause policy BLOCK.
- LLM enabled without valid credentials or with high temperature causes
  unstable plans or fallbacks.

## UI Prompt Copy (Recommended)

Use these strings directly in the UI. Keep them short and consistent.

### Global Banner

- "Demo mode. Review every transaction carefully before approving."

### Missing Inputs (NEEDS_INPUT)

- "I need a bit more information to continue:"
- "Which wallet address should I use?"
- "Which network (chain) should I use?"
- "How much do you want to swap or send?"
- "Which token do you want to receive?"

### Ready for Approval (READY)

- "Plan is ready. Review the transactions and approve to continue."
- "No signing happens on the backend. You will sign in your wallet."

### Approval Confirmation

- "I understand and approve these transactions."
- "Proceed to wallet signing."

### Blocked

- "This request is blocked by policy. See the reasons below."

### Failed

- "This run failed. Please retry or adjust the request."

### No-Op

- "There is nothing to execute for this request. Tell me what you want to do."

### Resume Success

- "Thanks. I have enough information to continue."

## UI Prompt Copy (Buttons / Short Labels)

- "Approve run"
- "Execute in wallet"
- "Resume run"
- "View details"
- "Retry"

## Mapping to Run Status

- `PAUSED + NEEDS_INPUT` -> show missing input prompts + Resume button.
- `AWAITING_APPROVAL + READY` -> show approval prompts + Approve button.
- `BLOCKED` -> show blocked prompt + reasons.
- `FAILED` -> show failed prompt + Retry button.
- `AWAITING_APPROVAL + READY` -> show Execute button after approval.

## Multi-Agent Consensus Card

Display `artifacts.consensus_summary` as a dedicated card:

- Title: "Multi-agent consensus"
- Verdict: READY/NEEDS_INPUT/BLOCKED/FAILED/NOOP
- Signals: Planner, Policy, Security, Judge (status + summary)

This is the main demo proof-point for “multi-agent coordination.”

## References

- `docs/config/08-config-and-env.md`
- `docs/ui/13-frontend-integration.md`
- `docs/ui/20-checkpointing-ui.md`

## Change log

- 2026-01-15: Initial demo-safe config and UI prompt copy.
- 2026-01-15: Add consensus summary card guidance.
