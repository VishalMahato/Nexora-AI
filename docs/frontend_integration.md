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
- `artifacts.judge_result` (AgentResult placeholder until F21)
- `artifacts.tx_plan`
- `artifacts.simulation`
- `artifacts.policy_result`
- `artifacts.decision`

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

GET `/v1/runs/{runId}`

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

## 8) Tool call logs (optional, for debug)

GET `/v1/runs/{runId}/tool-calls`

Each tool call includes `tool_name`, `request`, `response`, and timestamps.

## AgentResult schema (for planner/security/judge)

```json
{
  "agent": "PLANNER|SECURITY|JUDGE",
  "step_name": "PLAN_TX|SECURITY_EVAL|FINALIZE",
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

## Timeline entries

`artifacts.timeline[]` entries are compact:

```json
{ "step": "PLAN_TX", "status": "OK", "title": "PLANNER", "summary": "..." }
```

## Common UI states

- `BLOCKED`: show `artifacts.decision.reasons`
- `AWAITING_APPROVAL`: show plan + simulation + warnings
- `SUBMITTED`: show pending status, poll `/poll_tx`
- `CONFIRMED|REVERTED`: show receipt summary

