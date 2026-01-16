# Step-by-Step UI Integration

## Purpose

Provide a chronological, UI-focused guide for calling the Nexora APIs, including
request payloads, expected responses, and when to use SSE for run events.

## Base URL

```
http://localhost:8000
```

## Inputs the UI should track

- `conversation_id`: stable per chat session (uuid or client-generated string).
- `wallet_address`: required for ACTION and wallet queries.
- `chain_id`: required for ACTION and wallet queries.
- `run_id`: returned for ACTION intents.

## Step 1: Send every chat message to the chat route

Endpoint:

```
POST /v1/chat/route
```

Request (minimum):

```json
{
  "message": "swap 1 usdc to weth",
  "conversation_id": "demo-001",
  "wallet_address": "0xabc...",
  "chain_id": 1
}
```

Response shape (common fields):

```json
{
  "mode": "GENERAL|QUERY|CLARIFY|ACTION",
  "assistant_message": "...",
  "questions": [],
  "data": {},
  "run_id": "uuid",
  "run_ref": { "id": "uuid", "status": "AWAITING_APPROVAL", "fetch_url": "/v1/runs/uuid?includeArtifacts=true" },
  "classification": { "intent_type": "...", "slots": {}, "missing_slots": [] },
  "conversation_id": "demo-001",
  "pending": false
}
```

### Mode handling

1) `GENERAL`
- UI shows `assistant_message` and optional `suggestions`.
- No run is created.

2) `QUERY`
- UI shows `assistant_message` and `data` (allowlists, snapshot, balance).
- No run is created.

3) `CLARIFY`
- UI shows `assistant_message` and `questions`.
- Keep the same `conversation_id` and send the next user reply to `/v1/chat/route`.

4) `ACTION`
- UI shows `assistant_message`.
- Use `run_id` / `run_ref` to drive the run timeline and approval UI.

## Step 2: ACTION flow (chronological)

### 2.1 Chat returns ACTION immediately

The chat response is returned quickly, even when the run is executing in the
background. Use `run_ref.status` to decide next steps.

If you want to delay execution until after chat returns, send:

```json
{
  "message": "...",
  "conversation_id": "demo-001",
  "wallet_address": "0xabc...",
  "chain_id": 1,
  "metadata": { "defer_start": true }
}
```

This creates a run but does not start it.

### 2.2 (Optional) Start the run if deferred

```
POST /v1/runs/{run_id}/start
```

Expected response:

```json
{ "ok": true, "runId": "uuid", "status": "AWAITING_APPROVAL|PAUSED|BLOCKED|FAILED", "final_status": "READY|NEEDS_INPUT|NOOP|BLOCKED|FAILED", "artifacts": { ... } }
```

### 2.3 Subscribe to run events (SSE)

Open SSE immediately after you have the `run_id`:

```
GET /v1/runs/{run_id}/events
```

Events are streamed as:

```json
{ "type": "run_step", "step": "PLAN_TX", "status": "DONE", "summary": "...", "replay": true }
```

```json
{ "type": "run_status", "status": "AWAITING_APPROVAL", "replay": true }
```

Note: the server replays existing steps first, then streams new ones. In the
current synchronous implementation, you may see only replayed events.

### 2.4 Fetch artifacts after the run is finalized

When you receive a `run_status` event that is terminal for the graph (typically
`AWAITING_APPROVAL`, `PAUSED`, `BLOCKED`, or `FAILED`), fetch full artifacts:

```
GET /v1/runs/{run_id}?includeArtifacts=true
```

Use the response to render:
- `artifacts.timeline`
- `artifacts.tx_requests`
- `artifacts.simulation`
- `artifacts.policy_result`
- `artifacts.security_result`
- `artifacts.judge_result`
- `artifacts.decision`
- `artifacts.assistant_message`
- `current_step` and `final_status` for UI state decisions

### 2.5 Resume when the run needs input

If the run returns:

- `status: PAUSED`
- `final_status: NEEDS_INPUT`

Use `artifacts.needs_input` to ask follow-up questions, then call:

```
POST /v1/runs/{run_id}/resume
```

Request example:

```json
{
  "answers": {
    "amount": "1",
    "token_out": "WETH"
  },
  "metadata": { "source": "ui" }
}
```

After resume:

- Re-open `GET /v1/runs/{run_id}/events` to stream new steps.
- Fetch artifacts again once the run reaches a terminal status.

## Step 3: Approval and execution

### 3.1 Approve the run

```
POST /v1/runs/{run_id}/approve
```

Request:

```json
{ "reviewer": "alice", "notes": "looks good" }
```

Response:

```json
{ "ok": true, "runId": "uuid", "status": "APPROVED_READY" }
```

### 3.2 Get tx request for wallet signing

```
POST /v1/runs/{run_id}/execute
```

Response:

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "APPROVED_READY",
  "tx_request": { "chainId": 1, "to": "0x...", "data": "0x", "valueWei": "0" }
}
```

Note: `/execute` currently returns the first candidate from `artifacts.tx_plan`.
If you have multiple transactions, prefer `artifacts.tx_requests` for display.

### 3.3 Submit the signed transaction hash

```
POST /v1/runs/{run_id}/tx_submitted
```

Request:

```json
{ "txHash": "0x...", "submittedBy": "metamask" }
```

Response:

```json
{ "ok": true, "runId": "uuid", "status": "SUBMITTED", "txHash": "0x..." }
```

## Step 4: Confirmation polling

```
POST /v1/runs/{run_id}/poll_tx
```

Pending response:

```json
{ "ok": true, "runId": "uuid", "status": "SUBMITTED", "mined": false, "tx_hash": "0x...", "receipt": null }
```

Mined response:

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "CONFIRMED|REVERTED",
  "mined": true,
  "tx_hash": "0x...",
  "receipt": { "...": "..." }
}
```

## Optional: stream chat responses

If you want streaming chat messages, use:

```
POST /v1/chat/route/stream
```

The SSE stream emits:

- `status` event
- `delta` chunks for `assistant_message`
- `final` with the full `ChatRouteResponse`

Use this for UI typing effects; it does not replace run events.

## Change log

- 2026-01-13: Initial version.
- 2026-01-14: Add final_status/current_step and PAUSED handling.
- 2026-01-15: Add resume flow for NEEDS_INPUT runs.
