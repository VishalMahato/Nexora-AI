# UI Response Mapping Guide

## Purpose

Show exactly what the UI should render from large API responses, without
dumping raw JSON to users.

## Key Principles

- Always show `assistant_message` as the primary response.
- Use `final_status` to decide the next UI state.
- Render only the high-signal artifacts and hide the rest behind a debug panel.

## Chat Route Responses

### Response: `POST /v1/chat/route`

Render:

- `assistant_message`
- `questions[]` (if present, as quick replies)
- `suggestions[]` (if present, as chips)

Use:

- `mode` to decide whether to show run UI or chat-only UI.
- `run_ref` to fetch the run if `mode == ACTION`.

## Run Response (Summary)

### Response: `GET /v1/runs/{id}`

Display:

- `status`
- `final_status`
- `current_step` (progress indicator)
- `assistant_message` (from `artifacts`)

Use:

- `final_status` for next UI (approve/clarify/explain).

## Run Response (Artifacts)

### Response: `GET /v1/runs/{id}?includeArtifacts=true`

### Always render

- `artifacts.assistant_message`
- `artifacts.timeline[]` (step list)
- `artifacts.consensus_summary` (multi-agent card)

### Render when READY

- `artifacts.tx_requests[]` (approval + execution UI)
- `artifacts.simulation` (summary + warnings)
- `artifacts.policy_result` (warnings/errors only)
- `artifacts.decision.summary` + `decision.reasons`

### Render when NEEDS_INPUT

- `artifacts.needs_input.questions`
- `artifacts.needs_input.missing` (for form fields)

### Render when BLOCKED or FAILED

- `artifacts.decision.reasons` (blocked)
- `artifacts.finalize_summary.llm_error` (if present, debug only)

### Optional debug panel

- `planner_result`
- `security_result`
- `judge_result`
- `policy_result` (full)
- `simulation` (full)
- `tx_plan`

## Run Events (SSE)

### Response: `GET /v1/runs/{id}/events`

Use:

- `run_step` events for timeline updates
- `run_status` events to flip UI state

Do not render raw event JSON to the user.

## Run Actions

### Approve

`POST /v1/runs/{id}/approve`

Only enable if `final_status == READY`.

### Execute

`POST /v1/runs/{id}/execute`

Use `tx_request` or `tx_requests` for wallet signing UI.

### Resume

`POST /v1/runs/{id}/resume`

Use when `final_status == NEEDS_INPUT`.

## UI State Mapping (Recommended)

- `READY` -> Approval screen
- `NEEDS_INPUT` -> Clarify screen
- `BLOCKED` -> Blocked explanation
- `FAILED` -> Error screen
- `NOOP` -> Informational / ask for new intent

## Change log

- 2026-01-15: Initial UI response mapping guide.
