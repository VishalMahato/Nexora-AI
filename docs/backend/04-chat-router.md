# Chat Router

## Purpose

Explain how `POST /v1/chat/route` works, how intent is classified, and how
queries vs actions are handled without creating runs unnecessarily.

## Modes

- GENERAL: smalltalk or capability questions.
- QUERY: read-only request (balances, snapshot, allowlists).
- CLARIFY: missing required slots; ask a question.
- ACTION: actionable intent that requires a run.

## Single-Intent Rule

At any time, exactly one ACTION intent may be active per conversation.
QUERY intents are non-blocking and can be answered while an ACTION is pending.

Multi-intent dialog management is deferred to a later product phase.

## Classification

The router calls the LLM classifier with:

- user message
- conversation context (history when available)
- pending intent + missing slots (if any)

The classifier returns JSON with:

- `mode`
- `intent_type`
- `confidence`
- `slots`
- `missing_slots`
- `reason`

The router normalizes:

- If `intent_type` is a QUERY intent, force mode to QUERY.
- If `intent_type` is an ACTION intent and mode is QUERY, promote to ACTION.

## Query Handling

Query intents include:

- BALANCE
- SNAPSHOT / WALLET_SNAPSHOT
- ALLOWLISTS
- ALLOWANCES

Query flow:

1) Validate wallet/chain if required.
2) Call tool function (no run).
3) Return `assistant_message` summary + `data` payload.

## Action Handling

Action intents include:

- SWAP
- TRANSFER
- APPROVE

Action flow:

1) Validate required slots.
2) If missing, return CLARIFY with questions.
3) If complete, create and start a run.
4) Return `run_id` / `run_ref` and a short summary.

## Guardrails (F36)

Before creating a run, the router applies deterministic safety checks:

- Low-signal / gibberish inputs are downgraded to GENERAL.
- ACTION runs are gated by supported tokens (from allowlists).

These guardrails prevent run creation for nonsense inputs or unsupported assets.

Note: `run_ref.status` is coarse. Fetch the run for `final_status` and
`current_step` when rendering action UI.

## Clarify Handling

When required fields are missing:

- `assistant_message` includes the actual question(s)
- `questions[]` is optional for quick replies
- `pending=true` stores conversation state

The next message attempts to fill missing slots using the classifier.

## Clarify vs Run Resume

Chat CLARIFY happens before a run is created. Run-level `needs_input` happens
inside the graph after a run has started.

- Chat CLARIFY -> respond with another `/v1/chat/route` message.
- Run NEEDS_INPUT -> call `POST /v1/runs/{id}/resume` with answers.

## Response Fields

`ChatRouteResponse` includes:

- `mode`
- `assistant_message`
- `questions`
- `data`
- `run_id` / `run_ref`
- `classification`
- `conversation_id`
- `pending` / `pending_slots`
- `suggestions`

## Example Responses

QUERY (snapshot):

```
{
  "mode": "QUERY",
  "assistant_message": "Wallet snapshot ...",
  "data": { "snapshot": { ... } }
}
```

ACTION (swap):

```
{
  "mode": "ACTION",
  "assistant_message": "Got it - I generated a safe transaction plan.",
  "run_ref": { "id": "...", "status": "AWAITING_APPROVAL" }
}
```

CLARIFY (missing wallet):

```
{
  "mode": "CLARIFY",
  "assistant_message": "What wallet address should I use?",
  "questions": ["What wallet address should I use?"],
  "pending": true
}
```

## References

- `docs/backend/05-api-reference.md`
- `docs/backend/06-data-models.md`

## Change log

- 2026-01-14: Add note about final_status/current_step usage.
- 2026-01-15: Add router guardrails for gibberish and supported tokens.
- 2026-01-15: Clarify chat CLARIFY vs run resume.

