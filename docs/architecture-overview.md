# Nexora Architecture Overview (Post-F24)

## Purpose

Give a brief, end-to-end view of the system architecture, backend layout, and
overall request flow after F24.

## High-Level System

```
User -> Conversational UI -> Conversation Router (LLM)
                           -> Tool APIs (read-only)
                           -> Runs API (LangGraph)
                                 -> DB (runs, steps, artifacts)
                                 -> RPC Provider
```

## Core Components

1) Conversational UI
   - Chat interface and wallet connection.
   - Renders tool responses and run timelines.
   - Executes tx_requests via MetaMask.

2) Conversation Router (LLM)
   - Classifies intent: GENERAL vs QUERY vs ACTION vs CLARIFY.
   - Uses tools for read-only queries.
   - Creates runs only for actionable intents.

3) Runs API (FastAPI + LangGraph)
   - Deterministic action pipeline.
   - Produces artifacts, timeline, tx_requests, simulation results.
   - Gates execution behind approval.

4) Tool APIs (read-only)
   - Wallet balances, allowances, allowlists/config.
   - No run_id required; fast responses.

5) Storage
   - Postgres tables for Runs and RunSteps.
   - Artifacts JSON for planner/security/judge/simulation.

6) RPC Provider
   - eth_call, estimate_gas, balanceOf, allowance, block number.
   - No private keys or signing on backend.

## Boundary Rules

- Conversation router handles chat turns and tool queries.
- Runs API is only for actionable intents (creates run_id).
- Read-only tools never create runs.
- At any time, exactly one ACTION intent may be active per conversation.
- QUERY intents are non-blocking and can be answered while an ACTION is pending.

## Backend Architecture

```
FastAPI
  - api/v1 (runs, approvals, execution, confirmations)
  - graph (LangGraph nodes + state)
  - policy (rules + engine)
  - defi (compiler + tx_requests)
  - chain (RPC client + ABI helpers)
  - db (runs, steps, artifacts)
  - llm (planner/judge prompts + clients)
```

## Run Flow (Action Request)

1) POST /v1/runs
2) POST /v1/runs/{id}/start
3) Graph pipeline:
   - INPUT_NORMALIZE
   - WALLET_SNAPSHOT
   - PLAN_TX
   - BUILD_TXS (compiler -> tx_requests)
   - SIMULATE_TXS (sequential for multi-tx)
   - POLICY_EVAL
   - SECURITY_EVAL (AgentResult wrapper)
   - JUDGE_AGENT
   - REPAIR_ROUTER / REPAIR_PLAN_TX (bounded retry)
   - FINALIZE
4) UI shows timeline + artifacts, asks for approval
5) POST /v1/runs/{id}/approve
6) POST /v1/runs/{id}/execute (tx_requests returned)
7) Frontend signs/sends txs and reports via /tx_submitted

## Query Flow (Read-only)

1) Chat LLM classifies QUERY
2) Tool endpoint called (balances/allowances/config)
3) UI responds directly

## State Machine (Frontend)

Chat modes:

- IDLE_CHAT
- CLARIFYING
- RUNNING_ACTION
- NEEDS_APPROVAL
- EXECUTING
- DONE / BLOCKED

Run status handling:

- NEEDS_INPUT -> render questions, call provide_input
- AWAITING_APPROVAL -> show tx_requests + approve
- BLOCKED -> show reasons

## Safety Guarantees

- No signing or broadcasting in backend.
- Allowlisted tokens/routers only.
- No unlimited approvals.
- Simulation required for txs; allowance failures produce WARN with assumed_success.
- Human approval gate before execution.

## Key Artifacts

- tx_plan, tx_requests, simulation, policy_result, decision
- planner_result, security_result, judge_result
- timeline (UI rendering)

## Known Limitations

- Sequential simulation uses guarded assumptions when allowances cannot be
  applied in stateless eth_call.
- Stateful override simulation is deferred (F24b).

## Product Roadmap (Intent Handling)

- Multi-intent dialog management (threads, interrupt rules, disambiguation)
  is deferred to a product-level release. Current chat routing supports a
  single active intent with clarify follow-ups.
