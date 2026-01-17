# UI Checkpointing and Resume

## Purpose

Explain how the frontend should handle runs that pause for missing inputs and
how to resume them using stored checkpoints.

## When resume is required

A run should be resumed only when all of these are true:

- `status == PAUSED`
- `final_status == NEEDS_INPUT`
- `artifacts.needs_input` is present

If any condition is not met, the UI should not call `/resume`.

## Required data sources

1) Fetch the run with artifacts:

```
GET /v1/runs/{run_id}?includeArtifacts=true
```

2) Read:

- `artifacts.needs_input.questions` (user-facing questions)
- `artifacts.needs_input.missing` (machine slots to fill)
- `artifacts.needs_input.data` (optional options for UI pickers)
- `artifacts.assistant_message` (preferred summary to show)

## UI flow (high level)

1) Detect `PAUSED + NEEDS_INPUT`.
2) Render `assistant_message` and the questions.
3) Collect user answers mapped to the `missing` keys.
4) POST answers to `/v1/runs/{id}/resume`.
5) Switch UI back to RUNNING state and re-open SSE events.
6) Fetch the run when it reaches a terminal status.

## Answer mapping

The resume API expects an `answers` map keyed by missing slot names.
Common slots:

- `wallet_address`
- `chain_id`
- `amount`
- `token_in`
- `token_out`
- `recipient`
- `slippage_bps`

Use `needs_input.data` for UI choices (for example, token options).

Example:

```json
{
  "answers": {
    "amount": "1",
    "token_out": "WETH"
  },
  "metadata": {
    "source": "ui"
  }
}
```

## Resume request

```
POST /v1/runs/{run_id}/resume
```

Response example:

```json
{
  "ok": true,
  "runId": "uuid",
  "status": "RUNNING",
  "final_status": "NEEDS_INPUT",
  "artifacts": { "assistant_message": "..." }
}
```

Notes:

- Answers are merged into `artifacts.user_inputs` on the backend.
- The backend clears `artifacts.needs_input` and re-runs the graph.

## After resume

- Re-open `GET /v1/runs/{id}/events` to stream new steps.
- When status becomes `AWAITING_APPROVAL`, fetch artifacts to render approval.
- If it returns to `PAUSED`, the run still needs more input.

## Error handling

- `404`: run not found. Clear local run state.
- `409`: run is not waiting for input or no checkpoint exists.
- `500`: treat as transient; retry or show a failure banner.

## Checkpointing behavior (backend)

- Checkpoints are stored per run using `thread_id = run_id`.
- A run must have started at least once to create a checkpoint.
- Resume will fail with 409 if no checkpoint exists.

## Interaction with chat CLARIFY

Chat routing can ask follow-up questions before a run is created. This is
separate from run-level `needs_input`.

- Chat CLARIFY -> send another `/v1/chat/route`
- Run NEEDS_INPUT -> send `/v1/runs/{id}/resume`

## Change log

- 2026-01-15: Initial UI checkpointing and resume flow.
