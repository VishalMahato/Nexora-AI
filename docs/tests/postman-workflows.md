# Postman Testing: APIs and Workflows

## Purpose

Provide a single Postman-focused guide that covers every API endpoint and the
main workflows (query, action, resume, and confirmations).

## Base URL

```
http://localhost:8000
```

## Postman Environment Variables

- `BASE_URL` = `http://localhost:8000`
- `RUN_ID` = (set after create run)
- `WALLET` = `0x1111111111111111111111111111111111111111`
- `CHAIN_ID` = `1`
- `RECIPIENT` = `0x2222222222222222222222222222222222222222`
- `CONVERSATION_ID` = `postman-demo`

## Health

### GET `{{BASE_URL}}/healthz`

Expected response:

```json
{ "ok": true, "llm_model": "...", "db_ok": true }
```

## Chat APIs

### POST `{{BASE_URL}}/v1/chat/route`

Query example:

```json
{
  "message": "what are the supported tokens?",
  "conversation_id": "{{CONVERSATION_ID}}"
}
```

Expected response:

```json
{
  "mode": "QUERY",
  "assistant_message": "...",
  "data": { "allowlists": { "chain_id": 1, "tokens": {}, "routers": {} } }
}
```

Action example:

```json
{
  "message": "swap 1 usdc to weth",
  "conversation_id": "{{CONVERSATION_ID}}",
  "wallet_address": "{{WALLET}}",
  "chain_id": {{CHAIN_ID}}
}
```

Expected response:

```json
{
  "mode": "ACTION",
  "run_ref": { "id": "uuid", "status": "AWAITING_APPROVAL" }
}
```

### POST `{{BASE_URL}}/v1/chat/route/stream` (SSE)

```json
{
  "message": "show wallet snapshot",
  "conversation_id": "{{CONVERSATION_ID}}",
  "wallet_address": "{{WALLET}}",
  "chain_id": {{CHAIN_ID}}
}
```

In Postman, open the **Stream** tab to see SSE events.

## Run APIs (single endpoints)

### POST `{{BASE_URL}}/v1/runs`

```json
{
  "intent": "send 0.0001 eth to {{RECIPIENT}}",
  "walletAddress": "{{WALLET}}",
  "chainId": {{CHAIN_ID}}
}
```

Expected response:

```json
{ "runId": "uuid", "status": "CREATED" }
```

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

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/resume`

```json
{
  "answers": { "amount": "1", "token_out": "WETH" },
  "metadata": { "source": "postman" }
}
```

Guards:

- Requires `status == PAUSED` and `final_status == NEEDS_INPUT`.
- Returns 409 if no checkpoint exists.

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}`

Use `includeArtifacts=true` for details:

```
GET {{BASE_URL}}/v1/runs/{{RUN_ID}}?includeArtifacts=true
```

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}/status`

Returns metadata without artifacts.

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}/details`

Alias for `includeArtifacts=true`.

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}/events` (SSE)

Streams run steps and status events. Use the **Stream** tab.

### GET `{{BASE_URL}}/v1/runs/{{RUN_ID}}/tool-calls`

Returns tool call logs for the run.

Alias:

```
GET {{BASE_URL}}/v1/runs/{{RUN_ID}}/tools
```

## Approval and Execution

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/approve`

```json
{ "reviewer": "postman" }
```

Guard: requires `final_status == READY` (otherwise 409).

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/reject`

```json
{ "reviewer": "postman", "reason": "not comfortable" }
```

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

Guard: requires `final_status == READY` (otherwise 409).

## Confirmation Tracking

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/tx_submitted`

```json
{
  "txHash": "0x" + "a".repeat(64),
  "submittedBy": "postman"
}
```

### POST `{{BASE_URL}}/v1/runs/{{RUN_ID}}/poll_tx`

Pending response:

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

Mined response:

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

## Workflow Recipes

### Workflow A: Query (no run)

1) POST `/v1/chat/route` with a query message.
2) Use `data` in the response to render answers.

### Workflow B: Action (swap/transfer)

1) POST `/v1/runs`
2) POST `/v1/runs/{id}/start`
3) GET `/v1/runs/{id}?includeArtifacts=true`
4) POST `/v1/runs/{id}/approve`
5) POST `/v1/runs/{id}/execute`

### Workflow C: Needs Input + Resume

1) Start a run with incomplete info (ex: "swap usdc").
2) If `final_status == NEEDS_INPUT`, call `/resume` with answers.
3) Re-fetch run details after resume completes.

### Workflow D: Confirmation Tracking

1) Execute run and sign in wallet.
2) POST `/tx_submitted` with hash.
3) POST `/poll_tx` until confirmed.

## Common Errors

- `409`: run not ready for approve/execute/resume.
- `422`: wallet address invalid.
- `404`: run not found.
- `500`: internal error; check server logs.

## Demo Notes

- For transfers, set `ALLOWLIST_TO` to include the recipient.
- If demo is noisy, set `SIMULATION_ASSUMED_SUCCESS_WARN=false`.

## Change log

- 2026-01-15: Initial Postman workflows guide.
