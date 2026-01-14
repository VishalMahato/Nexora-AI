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
  { "ok": true, "runId": "...", "status": "...", "artifacts": { ... } }
  ```

  ### GET /v1/runs/{id}

  Fetches run metadata. Supports `includeArtifacts=true`.

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

  Request:

  ```
  { "reviewer": "name" }
  ```

  ### POST /v1/runs/{id}/execute

  Returns `tx_requests` for frontend execution.

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

  - `docs/project/06-data-models.md`

