# Product Brief

## Summary

Nexora is a conversational Web3 intent copilot. Users describe what they want to
do (for example, "swap 1 USDC to WETH"), and the system produces an explainable,
auditable plan that the user can approve and execute from the frontend.

The backend never signs or broadcasts transactions. It focuses on deterministic
planning, simulation, policy checks, and human review gates.

## Problem Statement

Web3 actions are error-prone, especially for non-expert users. Existing UX
forces users to understand low-level transaction details, which increases
mistakes and erodes trust.

The product goal is to:

- Translate human intent into safe, deterministic transaction requests.
- Show clear reasoning and risks before any execution.
- Require explicit human approval for any action.

## Users and Personas

- Demo user: wants to see an end-to-end story quickly.
- Power user: knows wallets and tokens but wants safety checks.
- Product owner: needs explainability and a clear audit trail.

## Product Scope (MVP)

In scope:

- Conversational router that handles QUERY vs ACTION vs CLARIFY.
- Deterministic planner that outputs structured transaction plans.
- DeFi compiler for a single router (Uniswap V2).
- Simulation (with guarded sequential fallback for approve -> swap).
- Policy enforcement, security evaluation, judge result.
- Human approval gate.
- Frontend-driven execution (MetaMask).

Out of scope:

- Backend signing or broadcasting.
- Multi-chain support beyond the configured allowlist.
- Unlimited approvals.
- Complex DeFi flows beyond single swap/approve.

## Success Criteria

- User can complete the loop: intent -> plan -> simulate -> approve -> execute.
- Every run has a readable timeline and artifacts.
- Safety checks block unsafe or non-allowlisted actions.
- UI can render a stable, explainable story for a demo.

## Key Constraints

- No private keys on backend.
- No broadcast of transactions from backend.
- Must remain deterministic and testable.
- System must be explainable by default.

## MVP Features (current)

- Planner and policy system with AgentResult contracts.
- Artifacts timeline for UI.
- F23 DeFi compiler (approve + swap).
- Sequential simulation with assumed success (guarded).
- Chat router and query tools (snapshot, balance, allowlists).

## Non-Goals

- Full portfolio management.
- Pricing or market data.
- Automated trading.

## Dependencies

- RPC provider for chain reads.
- Postgres database for runs and artifacts.
- LLM provider for planner and router.

## Risks and Mitigations

- Simulation mismatch: use guarded assumptions and log clearly.
- LLM variability: strict JSON schemas and validation.
- Confusing UX: consolidate responses into a single assistant message.

## Acceptance for Handoff

The next team should be able to:

- Run the backend locally with a single command.
- Use Streamlit UI to create a run and see artifacts.
- Identify where to change allowlists or defaults.
- Add a new action node safely.

## Change Log

- Initial version created for handoff.

