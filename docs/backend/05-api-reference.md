  # API Reference (Backend)

  ## Base URL

  All endpoints are under the FastAPI app root. Examples assume:

  ```
  http://localhost:8000
  ```

  ## Health

  ### GET /healthz

  Returns basic service status.

  Response:

  ```
  { "ok": true, "llm_model": "...", "db_ok": true }
  ```

  ## Chat

  ### POST /v1/chat/route

  Routes a chat message and optionally calls tools or runs.

  Request:

  ```
  {
    "message": "swap 1 usdc to weth",
    "conversation_id": "uuid",
    "wallet_address": "0x...",
    "chain_id": 1,
    "metadata": { "history": [...] }
  }
  ```

  Response (example QUERY):

  ```
  {
    "mode": "QUERY",
    "assistant_message": "...",
    "questions": [],
    "data": { "snapshot": { ... } },
    "classification": { ... }
  }
  ```

  Response (example ACTION):

  ```
  {
    "mode": "ACTION",
    "assistant_message": "...",
    "run_ref": { "id": "...", "status": "AWAITING_APPROVAL" },
    "next_ui": "SHOW_APPROVAL_SCREEN"
  }
  ```

  ### POST /v1/chat/route/stream

  Streams the assistant message and final response as server-sent events (SSE).

  Event types:

  - `status`: emitted immediately (`processing`)
  - `delta`: partial assistant message chunks
  - `final`: full `ChatRouteResponse` payload

  Example SSE payloads:

  ```
  data: {"type":"status","status":"processing"}

  data: {"type":"delta","content":"Wallet snapshot..."}

  data: {"type":"final","response":{...}}
  ```

  ## Runs

  ### POST /v1/runs

  Creates a run.

  Request:

  ```
  { "intent": "...", "walletAddress": "0x...", "chainId": 1 }
  ```

  Response:

  ```
  { "runId": "...", "status": "CREATED" }
  ```

  ### POST /v1/runs/{id}/start

  Starts execution of the run graph.

  Response:

  ```
  { "ok": true, "runId": "...", "status": "...", "final_status": "...", "artifacts": { ... } }
  ```

  ### POST /v1/runs/{id}/resume

  Resumes a paused run that needs input.

  Request:

  ```
  {
    "answers": { "amount": "1", "token_out": "WETH" },
    "metadata": { "source": "ui" }
  }
  ```

  Response:

  ```
  { "ok": true, "runId": "...", "status": "...", "final_status": "...", "artifacts": { ... } }
  ```

  Guards:

  - Requires `status == PAUSED` and `final_status == NEEDS_INPUT`.
  - Returns 409 if no checkpoint is found.
  - Merges `answers` into `artifacts.user_inputs` and clears `needs_input`.

  ### GET /v1/runs/{id}

  Fetches run metadata. Supports `includeArtifacts=true`.

  Run payload includes:

  - `current_step` (last STARTED step)
  - `final_status` (READY/NEEDS_INPUT/BLOCKED/FAILED/NOOP)

  ### GET /v1/runs/{id}/status

  Alias for metadata without artifacts.

  ### GET /v1/runs/{id}/details

  Alias for metadata with artifacts.

  ### GET /v1/runs/{id}/events

  Streams run step events as server-sent events (SSE).

  Behavior:

  - Replays existing timeline entries first
  - Continues streaming new `run_step` / `run_status` events

  Example events:

  ```
  data: {"type":"run_step","runId":"...","step":"PLAN_TX","status":"OK","summary":"Planner produced a transaction plan.","replay":true}

  data: {"type":"run_status","runId":"...","status":"AWAITING_APPROVAL"}
  ```

  ### POST /v1/runs/{id}/approve

  Moves run to `APPROVED_READY`.

  Guard:

  - Requires `final_status == READY` (otherwise 409).

  Request:

  ```
  { "reviewer": "name" }
  ```

  ### POST /v1/runs/{id}/execute

  Returns `tx_requests` for frontend execution.

  Guard:

  - Requires `final_status == READY` (otherwise 409).

  ### GET /v1/runs/{id}/tool-calls

  Lists tool calls associated with the run.

  Aliases:

  - `/v1/runs/{id}/tools`

  ## Confirmations

  ### POST /v1/runs/{id}/tx_submitted

  Records transaction submission data.

  ### GET /v1/runs/{id}/tx_status

  Fetches confirmation status for submitted transactions.

  ## Error Responses

  All endpoints return standard HTTP errors with:

  ```
  { "detail": "error message" }
  ```

  ## References

  - `docs/backend/06-data-models.md`

  ## Change log

  - 2026-01-14: Document final_status/current_step and approval guards.
  - 2026-01-15: Add resume endpoint and merge behavior notes.

