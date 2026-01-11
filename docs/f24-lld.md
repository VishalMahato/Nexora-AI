# Conversational Orchestrator LLD (Post-F24)

## Goal

Define a low-level design for the conversational orchestration layer that
uses tools for queries and only starts a run when the intent is actionable.

## Assumptions

- Chat LLM lives outside the run service.
- Runs are created only for action intents that can lead to tx_requests.
- Wallet queries (balance, allowances) are tools, not runs.
- Wallet address is already known in the client session.
- conversation_id can be attached to runs as metadata (optional).
- This LLD is about chat orchestration, not the F24 simulation feature.

## Components

1) Conversational Orchestrator
   - Runs in FE or a thin API.
   - Classifies intent and calls tools.
   - Stores conversation context (not in run DB).

2) Runs API (LangGraph)
   - Creates and executes action runs.
   - Produces artifacts, timeline, tx_requests.

3) Tool Endpoints (Query)
   - Wallet snapshot, balances, allowances, config allowlists.
   - No run_id required.
   - These are called directly by the conversational agent.

## Core Data Structures

### IntentClassification (chat output)

```json
{
  "mode": "QUERY|ACTION|CLARIFY",
  "action": "SWAP|TRANSFER|APPROVE|UNKNOWN",
  "tool": "GET_BALANCES",
  "slots": {
    "token_in": "USDC",
    "token_out": "WETH",
    "amount_in": "1",
    "chain_id": 1,
    "wallet_address": "0x..."
  },
  "missing_fields": [],
  "run_intent": "swap 1 usdc to weth",
  "confidence": 0.88
}
```

### NeedsInput (run artifact, proposed)

```json
{
  "status": "NEEDS_INPUT",
  "questions": [
    {
      "id": "amount_in",
      "field": "amount_in",
      "question": "How much USDC do you want to swap?",
      "choices": null
    }
  ]
}
```

## Tool Interface (Chat LLM -> APIs)

### Chat routing (optional)

- `POST /v1/chat/route`
  - input: message + context
  - output: mode, slots, missing_fields, run_intent

### Query tools (no run_id)

- `GET /v1/wallets/{address}/snapshot?chainId=1`
- `GET /v1/wallets/{address}/balances?chainId=1`
- `GET /v1/wallets/{address}/allowances?chainId=1&spender=0x...`
- `GET /v1/config/allowlists?chainId=1`

### Action tools (run lifecycle)

- `POST /v1/runs`
  - input: intent, walletAddress, chainId
  - output: runId
- `POST /v1/runs/{id}/start`
  - output: artifacts, status
- `POST /v1/runs/{id}/approve`
- `POST /v1/runs/{id}/execute`
- `GET /v1/runs/{id}?includeArtifacts=true`

### Proposed (for graph clarification)

- `POST /v1/runs/{id}/provide_input`
  - input: answers map
  - resumes from NEEDS_INPUT

## State Machine (Frontend)

Chat mode states:

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

## Flow: Query (Balance)

1) User: "What is my USDC balance?"
2) Chat LLM -> classify QUERY
3) Call `GET /v1/wallets/.../balances`
4) Answer returned directly, no run.

## Flow: Action (Swap)

1) User: "Swap 1 USDC to WETH"
2) Chat LLM -> ACTION with full slots
3) Create run -> start run
4) FE renders timeline, tx_requests, approval gate.

## Flow: Action with Missing Fields

1) User: "Swap USDC to WETH"
2) Chat LLM -> CLARIFY (missing amount)
3) Ask follow-up in chat (no run yet)
4) Once filled, create and start run.

## Flow: Graph Needs Input (Optional)

1) Run starts, planner detects missing required fields
2) Run stops with NEEDS_INPUT and questions
3) FE asks user, then calls `provide_input`
4) Run resumes from next node

## Notes

- The graph is not a tool itself; the Runs API is the tool.
- Chat LLM can wrap the Runs API as one tool call named `execute_action_run`.
- All query tools should be fast and not allocate run_id.
- The conversational agent should treat all Run endpoints as tools.
- The run can pause in NEEDS_INPUT if it finds missing slots after start.
