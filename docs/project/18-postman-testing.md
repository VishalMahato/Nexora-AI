# Postman API Test Guide

## Purpose

This document shows how to test each Nexora API endpoint in Postman, including
the SSE streaming endpoints. It includes example inputs and expected outputs.

## Prerequisites

- Backend running locally (`uv run uvicorn app.main:app --reload` or Docker)
- Postman installed (v10+ recommended for SSE support)
- A valid wallet address for read-only queries

## Postman Environment

Create an environment with these variables:

- `BASE_URL` = `http://localhost:8000`
- `RUN_ID` = (set after create run)
- `WALLET` = `0x0000000000000000000000000000000000000000`

## Health

### GET `{{BASE_URL}}/healthz`

Expected response:

```json
{ "ok": true, "llm_model": "...", "db_ok": true }
```

## Chat

### POST `{{BASE_URL}}/v1/chat/route`

Request body (JSON):

```json
{
  "message": "what tokens are supported?",
  "conversation_id": "postman-demo"
}
```

Expected response:

```json
{
  "mode": "QUERY",
  "assistant_message": "Here are the currently supported tokens and routers.",
  "data": { "allowlists": { "chain_id": 1, "tokens": {}, "routers": {} } }
}
```

### POST `{{BASE_URL}}/v1/chat/route/stream` (SSE)

Request body (JSON):

```json
{
  "message": "show wallet snapshot",
  "conversation_id": "postman-demo",
  "wallet_address": "{{WALLET}}",
  "chain_id": 1
}
```

Expected SSE events (example):

```
data: {"type":"status","status":"processing"}
data: {"type":"delta","content":"Wallet snapshot..."}
data: {"type":"final","response":{...}}
```

Notes:

- In Postman, open the **Stream** tab to see incoming SSE messages.
- If your Postman version does not render SSE, use curl:

```
curl -N -X POST "{{BASE_URL}}/v1/chat/route/stream" \
  -H "Content-Type: application/json" \
  -d '{"message":"show wallet snapshot","wallet_address":"{{WALLET}}","chain_id":1}'
```

## Runs (Lifecycle)

### POST `{{BASE_URL}}/v1/runs`

Request body:

```json
{
  "intent": "send 0.0001 eth to 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "walletAddress": "{{WALLET}}",
  "chainId": 1
}
```

Expected response:

```json
{ "runId": "uuid", "status": "CREATED" }
```

Save `runId` as `RUN_ID` in Postman environment.

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/start`

Expected response (core fields):

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "AWAITING_APPROVAL|PAUSED|BLOCKED|FAILED",
  "final_status": "READY|NEEDS_INPUT|NOOP|BLOCKED|FAILED",
  "artifacts": { ... }
}
```

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}?includeArtifacts=true`

Expected response:

```json
{
  "run": {
    "id": "uuid",
    "status": "AWAITING_APPROVAL",
    "current_step": "PLAN_TX",
    "final_status": "READY",
    "artifacts": { ... }
  }
}
```

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}/events` (SSE)

Expected SSE events:

```
data: {"type":"run_step","runId":"...","step":"PLAN_TX","status":"DONE","summary":"Planner produced a transaction plan.","replay":true}
data: {"type":"run_status","runId":"...","status":"AWAITING_APPROVAL","replay":true}
```

Notes:

- This endpoint replays existing steps first, then streams new ones.
- In Postman, open the **Stream** tab.

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/approve`

Request body:

```json
{ "reviewer": "postman" }
```

Expected response:

```json
{ "ok": true, "runId": "uuid", "status": "APPROVED_READY" }
```

Guard:

- Approval/execution requires `final_status == READY` (otherwise 409).

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/execute`

Expected response:

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "APPROVED_READY",
  "tx_request": { "chainId": 1, "to": "0x...", "data": "0x", "valueWei": "0" }
}
```

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/tx_submitted`

Request body:

```json
{
  "txHash": "0x" + "a".repeat(64),
  "submittedBy": "postman"
}
```

Expected response:

```json
{ "ok": true, "runId": "uuid", "status": "SUBMITTED", "txHash": "0x..." }
```

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/poll_tx`

Expected response (pending):

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

Expected response (mined):

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "CONFIRMED|REVERTED",
  "mined": true,
  "tx_hash": "0x...",
  "receipt": { "status": 1, "blockNumber": 123 }
}
```

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}/tool-calls`

Expected response:

```json
[
  {
    "tool_name": "web3.eth_getBalance",
    "request": { ... },
    "response": { ... }
  }
]
```

## Common Issues

- **Empty response body**: backend error or invalid wallet address; check server logs.
- **SSE not showing**: use the Stream tab in Postman or run with curl.
- **409 conflicts**: run is in the wrong status for the action; check `GET /v1/runs/{id}`.

## Change log

- 2026-01-11: Initial version for Postman + SSE testing.
- 2026-01-14: Add final_status/current_step and PAUSED handling.
