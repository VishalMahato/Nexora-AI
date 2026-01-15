# Nexora Demo UI Spec (Streamlit MVP)

## Purpose

Define a minimal, demo-ready UI that exposes the chat flow, run timeline, and
artifacts with maximum clarity and minimal build effort.

## Scope

- One-page Streamlit app.
- Chat drives `/v1/chat/route`.
- Runs are fetched via `/v1/runs/{id}?includeArtifacts=true`.
- Approval and execution use existing run endpoints.

## Layout (Single Page)

### Header

- Title: `Nexora - Web3 Intent Copilot (MVP)`
- Backend status pill: Connected / Not Connected

### Left Sidebar

#### Session
- `conversation_id` (auto-generated; "New conversation" button)
- `wallet_address` (text input)
- `chain` (dropdown; default mainnet)

#### Intent Input
- Chat text box: "What do you want to do?"
- Buttons: `Send`, `Clear chat`

#### Run Controls (visible only if run exists)
- `run_id` (read-only)
- Buttons: `Refresh run`, `Approve`, `Execute`

### Main Area Tabs

#### Tab 1 - Chat
- User + assistant message bubbles.
- If `mode=CLARIFY`: render questions as buttons + free text reply.
- Router card: `mode`, `intent_type`, `missing_slots` (chips).

#### Tab 2 - Run Timeline
- Vertical list or table of steps.
- Columns: step_name, status, timestamp.
- Highlight current step.
- If status is AWAITING_APPROVAL and `final_status == READY`, show a banner.
- If status is PAUSED and `final_status == NEEDS_INPUT`, show a clarify banner.

#### Tab 3 - Artifacts / Debug
- Collapsible JSON viewers for:
  - tx_plan
  - tx_requests
  - simulation
  - policy_result
  - security_result
  - judge_result
  - decision
- Button: "Download run JSON"

## Approval + Execution UX

- When run is `AWAITING_APPROVAL` and `final_status == READY`, show tx_requests table:
  - kind, to, value, data (collapsed), gas estimate (if present)
- Checkbox: "I understand and approve"
- Button: `Approve Run`
- `Execute` calls `/v1/runs/{id}/execute` and displays tx_requests for manual signing.

## Read-Only Tools (Optional)

Small section to call:
- Get allowlists
- Get wallet snapshot
- Get token balance

These call the same tool endpoints used by chat.

## Required Endpoints

- `POST /v1/chat/route`
- `GET /v1/runs/{id}?includeArtifacts=true`
- `POST /v1/runs/{id}/approve`
- `POST /v1/runs/{id}/execute`

Optional tools:
- `GET /v1/wallets/{address}/snapshot?chainId=1`
- `GET /v1/wallets/{address}/balances?chainId=1`
- `GET /v1/config/allowlists?chainId=1`

## Behavior Rules

- Exactly one ACTION intent active per conversation.
- QUERY intents are non-blocking and can be answered while an ACTION is pending.
- On ACTION, auto-switch to Run Timeline tab when `run_id` is returned.

## Change log

- 2026-01-14: Add final_status/PAUSED handling for UI banners.

