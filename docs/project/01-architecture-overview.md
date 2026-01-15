# Architecture Overview

## Purpose

Provide a clear, end-to-end system view for new owners. This document focuses
on boundaries, data flow, and responsibility split between components.

## High-Level System

```
User
  -> Conversational UI (Streamlit / FE)
      -> Chat Router (LLM-based classifier)
          -> Tool APIs (read-only)
          -> Runs API (LangGraph)
                -> DB (runs, steps, artifacts)
                -> RPC Provider (chain reads)
```

## Core Components

1) Conversational UI
   - Presents a chat interface.
   - Sends messages to `POST /v1/chat/route`.
   - Displays responses and run summaries.
   - Shows timelines and artifacts for runs.

2) Chat Router
   - Classifies user messages into QUERY / ACTION / CLARIFY / GENERAL.
   - Handles query tools directly (no run).
   - Creates runs for ACTION intents only.
   - Supports a single pending intent with clarify follow-ups.

3) Runs API (LangGraph)
   - Deterministic execution graph.
   - Produces artifacts, timeline, and tx_requests.
   - Enforces policy and safety checks.
   - Pauses at approval gate.
   - Resolves `final_status` for UI gating and safe approvals.

4) Tool APIs (Read-only)
   - Wallet snapshot
   - Token balances
   - Allowlist/config

5) Storage
   - Runs table for lifecycle and metadata.
   - RunSteps table for step logs.
   - Artifacts JSON for detailed outputs.

6) RPC Provider
   - Chain reads: balance, allowance, eth_call, estimateGas.
   - No private keys or broadcasting.

## Boundary Rules

- Chat router handles conversational turns and tool queries.
- Runs are created only for actionable intents.
- Read-only tools must never create runs or mutate state.
- Exactly one ACTION intent may be active per conversation.
- QUERY intents are non-blocking and can be answered while an ACTION is pending.

## Data Flow (Action)

1) User sends intent.
2) Chat router returns ACTION.
3) UI calls `POST /v1/runs`.
4) UI calls `POST /v1/runs/{id}/start`.
5) Graph executes and returns artifacts.
6) UI shows timeline and checks `final_status`.
7) UI calls `POST /v1/runs/{id}/approve`.
8) UI calls `POST /v1/runs/{id}/execute` to get tx_requests.
9) UI signs via wallet (frontend).

## Data Flow (Query)

1) User sends query.
2) Chat router returns QUERY.
3) Chat router calls tool API and responds with summary + data payload.

## Key Design Decisions

- No backend signing: all execution is client-side.
- Deterministic artifacts: every run produces machine + human readable outputs.
- Explainability: timeline entries for each step.
- Safe by default: allowlists and simulation gates.
- Approval/execute are guarded by `final_status == READY`.

## Known Limitations

- Sequential simulation uses guarded assumptions when allowances cannot be
  applied in stateless eth_call.
- Multi-intent dialog management is deferred to a product-level release.

## References

- `docs/project/03-run-lifecycle.md`
- `docs/project/04-chat-router.md`
- `docs/project/05-api-reference.md`

## Change log

- 2026-01-14: Document final_status gating in run flow.

