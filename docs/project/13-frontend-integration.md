# Frontend Integration

## Purpose

Explain how the UI should call backend endpoints and render results.

## Primary Endpoints

- `POST /v1/chat/route`
- `GET /v1/runs/{id}?includeArtifacts=true`
- `POST /v1/runs/{id}/approve`
- `POST /v1/runs/{id}/execute`

## Chat Rendering Rules

- Always display `assistant_message` as the main response.
- If `questions[]` exists, render optional quick replies under the message.
- Do not create separate "clarify" panels; keep the conversation linear.
- Preserve line breaks in `assistant_message` when rendering.

## Run Rendering Rules

- Show `timeline` in order.
- Display `tx_requests` for approval.
- Use `judge_result` and `security_result` for explainability sections.
- If `simulation` includes `assumed_success`, show a warning badge.

## Status Handling

When run status is:

- `AWAITING_APPROVAL`: show approval controls.
- `BLOCKED`: show reasons and stop.
- `FAILED`: show error and stop.
- `APPROVED_READY`: enable execute button.

## Execution Flow

1) User approves.
2) UI calls `/execute`.
3) UI signs `tx_requests` with wallet.
4) UI posts tx hashes back to backend (if enabled).

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
