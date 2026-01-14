# Frontend Integration Guide

This doc describes the current Nexora API surface for UI integration.
All endpoints return JSON and use UUID run IDs.

## Base URL

Local dev:

- `http://localhost:8000`

## Run lifecycle (high level)

```
CREATED -> RUNNING -> AWAITING_APPROVAL -> APPROVED_READY -> SUBMITTED -> CONFIRMED|REVERTED
                    \-> BLOCKED
                    \-> FAILED
                    \-> REJECTED
```

## 1) Create a run

POST `/v1/runs`

Request:

```json
{
  "intent": "send 0.0001 eth to 0x...",
  "walletAddress": "0x...",
  "chainId": 1
}
```

Response:

```json
{ "runId": "uuid", "status": "CREATED" }
```

## 2) Start execution (plan + simulate + policy)

POST `/v1/runs/{runId}/start`

Response (core fields only):

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "AWAITING_APPROVAL|BLOCKED",
  "artifacts": { ... }
}
```

Key artifacts you can render:

- `artifacts.timeline[]` (UI-friendly entries)
- `artifacts.planner_result` (AgentResult)
- `artifacts.security_result` (AgentResult)
- `artifacts.judge_result` (AgentResult)
- `artifacts.tx_plan`
- `artifacts.tx_requests` (compiled txs for FE signing)
- `artifacts.quote` (swap quote summary, if applicable)
- `artifacts.simulation`
- `artifacts.policy_result`
- `artifacts.decision`

Note: `planner_result.output.tx_plan.candidates` may be empty. The compiler fills
`artifacts.tx_requests` (and compiled candidates in `artifacts.tx_plan`) later.
For execution, always use `artifacts.tx_requests`.

## Chat routing (F25)

POST `/v1/chat/route`

Response includes:

- `mode: QUERY|ACTION|CLARIFY`
- `classification` (intent_type, slots, missing_slots)
- `run_id` / `run_ref` when ACTION triggers a run

Frontend should map UI state from `run_ref.status` (or fetch the run status).
If present, `next_ui` may include `SHOW_APPROVAL_SCREEN` when a run is ready
for approval.

## 3) Approve or reject

POST `/v1/runs/{runId}/approve`

```json
{ "reviewer": "name", "notes": "optional" }
```

POST `/v1/runs/{runId}/reject`

```json
{ "reviewer": "name", "reason": "optional" }
```

Response:

```json
{ "ok": true, "runId": "uuid", "status": "APPROVED_READY|REJECTED" }
```

## 4) Execute (build tx request for wallet)

POST `/v1/runs/{runId}/execute`

Response:

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "APPROVED_READY",
  "tx_request": {
    "chainId": 1,
    "to": "0x...",
    "data": "0x",
    "valueWei": "100000000000000"
  }
}
```

UI passes `tx_request` to MetaMask/WalletConnect.

## 5) Submit tx hash

POST `/v1/runs/{runId}/tx_submitted`

```json
{
  "txHash": "0x" + 64 hex chars,
  "submittedBy": "metamask|walletconnect|manual"
}
```

Response:

```json
{ "ok": true, "runId": "uuid", "status": "SUBMITTED", "txHash": "0x..." }
```

## 6) Poll confirmation

POST `/v1/runs/{runId}/poll_tx`

Response (pending):

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "SUBMITTED",
  "mined": false,
  "tx_hash": "0x...",
  "receipt": null
}
```

Response (mined):

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "CONFIRMED|REVERTED",
  "mined": true,
  "tx_hash": "0x...",
  "receipt": { "status": 1, "blockNumber": 123, "gasUsed": 21000 }
}
```

## 7) Fetch run status

GET `/v1/runs/{runId}` or `GET /v1/runs/{runId}/status`

Response:

```json
{
  "run": {
    "id": "uuid",
    "intent": "...",
    "wallet_address": "0x...",
    "chain_id": 1,
    "status": "AWAITING_APPROVAL",
    "error_code": null,
    "error_message": null,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

Optional: include artifacts

- Query: `GET /v1/runs/{runId}?includeArtifacts=true`
- Alias: `GET /v1/runs/{runId}/details` (always includes artifacts)

Response includes `run.artifacts`.

## 7a) Stream run events (live timeline)

GET `/v1/runs/{runId}/events` (SSE)

Behavior:

- Replays existing timeline entries
- Streams `run_step` and `run_status` events as the graph executes

Example events:

```json
{"type":"run_step","runId":"uuid","step":"PLAN_TX","status":"OK","summary":"Planner produced a transaction plan.","replay":true}
```

```json
{"type":"run_status","runId":"uuid","status":"AWAITING_APPROVAL"}
```

## 8) Tool call logs (optional, for debug)

GET `/v1/runs/{runId}/tool-calls`

Each tool call includes `tool_name`, `request`, `response`, and timestamps.

## AgentResult schema (for planner/security/judge)

```json
{
  "agent": "PLANNER|SECURITY|JUDGE",
  "step_name": "PLAN_TX|SECURITY_EVAL|JUDGE_AGENT|FINALIZE",
  "version": 1,
  "status": "OK|WARN|BLOCK|ERROR",
  "output": {},
  "explanation": {
    "summary": "string",
    "assumptions": [],
    "why_safe": [],
    "risks": [{ "severity": "LOW|MED|HIGH", "title": "string", "detail": "string" }],
    "next_steps": []
  },
  "confidence": 0.0,
  "sources": [],
  "errors": [],
  "created_at": "ISO-8601"
}
```

## Judge output schema (artifacts.judge_result.output)

```json
{
  "verdict": "PASS|NEEDS_REWORK|BLOCK",
  "reasoning_summary": "string",
  "issues": [
    { "code": "string", "severity": "LOW|MED|HIGH", "message": "string", "data": {} }
  ]
}
```

## TxRequest schema (artifacts.tx_requests[])

```json
{
  "txRequestId": "approve-1|swap-1",
  "chainId": 1,
  "to": "0x...",
  "data": "0x...",
  "valueWei": "0",
  "meta": {
    "kind": "APPROVE|SWAP",
    "token": "USDC",
    "spender": "UNISWAP_V2_ROUTER",
    "amount": "20",
    "amountBaseUnits": "20000000",
    "tokenIn": "USDC",
    "tokenOut": "ETH",
    "amountIn": "20",
    "amountInBaseUnits": "20000000",
    "minOut": "12345",
    "slippageBps": 50,
    "deadlineSeconds": 1200,
    "routerKey": "UNISWAP_V2_ROUTER"
  }
}
```

## Timeline entries

`artifacts.timeline[]` entries are compact:

```json
{ "step": "PLAN_TX", "status": "OK", "title": "PLANNER", "summary": "..." }
```

## Simulation shape (sequential)

When multiple tx requests are present, simulation runs in order and may mark a
swap as assumed success if allowance cannot be applied in a stateless `eth_call`:

```json
{
  "status": "completed",
  "mode": "sequential",
  "sequence": ["approve-1", "swap-1"],
  "override_support": "unsupported",
  "overrides_used": false,
  "results": [
    {
      "txRequestId": "approve-1",
      "success": true,
      "assumed_success": false
    },
    {
      "txRequestId": "swap-1",
      "success": true,
      "assumed_success": true,
      "assumption_reason": "ALLOWANCE_NOT_APPLIED_IN_SIMULATION"
    }
  ]
}
```

## Common UI states

- `BLOCKED`: show `artifacts.decision.reasons`
- `AWAITING_APPROVAL`: show plan + simulation + warnings
- `SUBMITTED`: show pending status, poll `/poll_tx`
- `CONFIRMED|REVERTED`: show receipt summary

