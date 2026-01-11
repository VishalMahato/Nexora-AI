# Nexora Conversational Web3 Copilot - HLD (Post-F24)

## Goal

Provide a conversational UI where users can ask wallet questions and request
actions, while the system converts actions into a safe, explainable run:
intent -> plan -> tx_requests -> simulate -> policy/security -> judge -> approval.

## Key Design Decision

Separate the conversational LLM from the execution run:

- Conversation LLM runs on every chat turn and routes between tools, actions,
  and clarification.
- LangGraph runs only when the intent is actionable and needs the audit trail.

This keeps chat fast and avoids run_id spam, while still allowing the run to
pause for missing inputs.

Note: the conversational layer is not the F24 feature itself; F24 refers to
sequential simulation. This HLD captures the overall system after F24.

## System Components

1) Frontend (chat + wallet)
   - Streaming chat UI
   - Wallet connection (MetaMask)
   - Renders tool answers, run timeline, tx_requests
   - Executes tx_requests and posts tx hashes

2) Conversation Router (LLM)
   - Classifies intent: TOOL vs ACTION vs CLARIFY
   - Calls read-only tools for wallet queries
   - Creates runs only for actions
   - Attaches conversation_id metadata to runs (optional)

3) Run Executor (FastAPI + LangGraph)
   - Deterministic pipeline:
     INPUT_NORMALIZE -> WALLET_SNAPSHOT -> PLAN_TX -> BUILD_TXS
     -> SIMULATE_TXS -> POLICY_EVAL -> SECURITY_EVAL -> JUDGE_AGENT
     -> REPAIR_ROUTER (bounded) -> FINALIZE
   - Produces artifacts + timeline for UI

4) Read-only Tool APIs (no run)
   - balances, allowances, allowlists

5) Storage
   - Runs table, RunSteps, and artifacts JSON

6) RPC Provider
   - eth_call, estimate_gas, balanceOf, allowance, block number
   - no signing or broadcasting on backend

## Core Flows

Flow 1 - Tool query (no run)

- User asks for balance/allowance
- Router calls tool endpoint
- UI responds directly

Flow 2 - Action request (run created)

- User requests swap/transfer
- Router creates run and starts it
- Run returns timeline + tx_requests + status
- UI asks for approval and executes txs

Flow 3 - Clarification

- Missing slots trigger follow-up questions
- Only after slots are filled is a run created
- Optional: run can pause in NEEDS_INPUT

## State Machine (Frontend)

Chat modes:

- IDLE_CHAT
- CLARIFYING (slot fill)
- RUNNING_ACTION
- NEEDS_APPROVAL
- EXECUTING
- DONE / BLOCKED

Run statuses map:

- NEEDS_INPUT -> render questions, call provide_input
- AWAITING_APPROVAL -> show tx_requests + approve
- BLOCKED -> show reasons

## Safety Model (Demo-safe)

- Backend never signs or broadcasts
- Allowlist enforcement for tokens and routers
- No unlimited approvals
- Simulation required for txs, with guarded allowance fallback
- Judge provides human-readable review and structured issues

## Key Interfaces (High-level)

- Chat routing (optional): POST /v1/chat/route
- Tool endpoints:
  - GET /v1/wallets/{address}/snapshot?chainId=...
  - GET /v1/wallets/{address}/balances?chainId=...
  - GET /v1/wallets/{address}/allowances?chainId=...&spender=...
  - GET /v1/config/allowlists?chainId=...
- Runs:
  - POST /v1/runs
  - POST /v1/runs/{id}/start
  - GET /v1/runs/{id}?includeArtifacts=true
- Execution tracking (F25):
  - POST /v1/runs/{id}/tx_submitted
  - POST /v1/runs/{id}/poll_tx

## F24 Behavior (Sequential Simulation)

- Multiple tx_requests are ordered (APPROVE then SWAP).
- Each result includes txRequestId.
- Swap failures that match allowance errors and have a matching approve
  are marked assumed_success with a WARN in policy.

```json
{
  "status": "completed",
  "mode": "sequential",
  "sequence": ["approve-1", "swap-1"],
  "override_support": "unsupported",
  "overrides_used": false,
  "results": [
    {"txRequestId": "approve-1", "success": true, "assumed_success": false},
    {
      "txRequestId": "swap-1",
      "success": true,
      "assumed_success": true,
      "assumption_reason": "ALLOWANCE_NOT_APPLIED_IN_SIMULATION"
    }
  ]
}
```

## Known Limitations (F24a)

- No state override for allowances; assumptions are explicit and WARN-only.
- True stateful simulation (approve then swap with allowance applied) is deferred.
