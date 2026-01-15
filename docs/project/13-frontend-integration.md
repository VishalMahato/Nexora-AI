# Frontend Integration

## Purpose

Explain how the UI should call backend endpoints and render results.

## Primary Endpoints

- `POST /v1/chat/route`
- `POST /v1/runs/{id}/start`
- `GET /v1/runs/{id}?includeArtifacts=true`
- `POST /v1/runs/{id}/resume`
- `POST /v1/runs/{id}/approve`
- `POST /v1/runs/{id}/execute`

## Chat Rendering Rules

- Always display `assistant_message` as the main response.
- If `questions[]` exists, render optional quick replies under the message.
- Do not create separate "clarify" panels; keep the conversation linear.
- Preserve line breaks in `assistant_message` when rendering.

## Run Rendering Rules

- Show `timeline` in order.
- Use `current_step` for progress indicators.
- Display `tx_requests` for approval.
- Use `judge_result` and `security_result` for explainability sections.
- If `simulation` includes `assumed_success`, show a warning badge.
- Use `artifacts.assistant_message` for the final user-facing summary.

## Status Handling

When run status is:

- `AWAITING_APPROVAL`: show approval controls only if `final_status == READY`.
- `PAUSED` + `final_status == NEEDS_INPUT`: show questions from `needs_input`.
- `PAUSED` + `final_status == NOOP`: show `assistant_message` and prompt for a new intent.
- `BLOCKED`: show reasons and stop.
- `FAILED`: show error and stop.
- `APPROVED_READY`: enable execute button.

## Execution Flow

1) User approves.
2) UI calls `/execute`.
3) UI signs `tx_requests` with wallet.
4) UI posts tx hashes back to backend (if enabled).

## Resume Flow (NEEDS_INPUT)

1) Run ends with `status=PAUSED` and `final_status=NEEDS_INPUT`.
2) UI shows `artifacts.assistant_message` and `artifacts.needs_input.questions`.
3) UI posts answers to `POST /v1/runs/{id}/resume`.
4) UI re-opens `/v1/runs/{id}/events` and waits for the next terminal status.

For detailed UI guidance, see `docs/project/20-checkpointing-ui.md`.

## Error Handling

- If `/chat/route` returns error, show the error text in chat.
- If `/runs/{id}` returns 404, clear `run_id` in UI state.

## Suggested UI States

- IDLE_CHAT
- CLARIFYING
- RUNNING_ACTION
- NEEDS_APPROVAL
- EXECUTING
- DONE / BLOCKED

## Change log

- 2026-01-14: Add guidance for final_status/current_step and PAUSED.
- 2026-01-15: Add resume flow and checkpointing UI reference.
