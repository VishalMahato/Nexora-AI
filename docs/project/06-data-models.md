# Data Models

## Purpose

Summarize the core JSON shapes used across the system. These definitions are
used by the frontend, tests, and LLM contracts.

## Chat Models

### ChatRouteRequest

- `message: string`
- `conversation_id?: string`
- `wallet_address?: string`
- `chain_id?: number`
- `metadata?: object`

### ChatRouteResponse

- `mode: QUERY | ACTION | CLARIFY | GENERAL`
- `assistant_message: string`
- `questions: string[]`
- `run_id?: string`
- `run_ref?: { id, status, fetch_url }`
- `data?: object`
- `classification?: IntentClassification`
- `conversation_id?: string`
- `pending?: boolean`
- `pending_slots?: object`
- `suggestions?: string[]`

### IntentClassification

- `mode`
- `intent_type`
- `confidence`
- `slots`
- `missing_slots`
- `reason`

## Run Models

### RunResponse (GET /v1/runs/{id})

```
{
  "run": {
    "id": "...",
    "intent": "...",
    "wallet_address": "...",
    "chain_id": 1,
    "status": "...",
    "current_step": "...",
    "final_status": "...",
    "artifacts": { ... }
  }
}
```

`final_status` values:

- READY
- NEEDS_INPUT
- BLOCKED
- FAILED
- NOOP

## AgentResult

Used by planner, security, and judge.

Fields:

- `agent`
- `step_name`
- `version`
- `status` (OK / WARN / BLOCK)
- `output`
- `explanation` (summary, assumptions, risks)
- `confidence`
- `sources`
- `errors`
- `created_at`

## JudgeOutput

- `verdict: PASS | NEEDS_REWORK | BLOCK`
- `reasoning_summary`
- `issues[]`

Issue fields:

- `code`
- `severity`
- `message`
- `data`

## tx_plan

Fields:

- `plan_version`
- `type` (plan | noop)
- `normalized_intent`
- `actions[]`
- `candidates[]`

Action types:

- TRANSFER
- APPROVE
- SWAP

## tx_requests

Frontend signing payloads.

Example:

```
{
  "txRequestId": "approve-1",
  "chainId": 1,
  "to": "0x...",
  "data": "0x...",
  "valueWei": "0",
  "meta": {
    "kind": "APPROVE",
    "token": "USDC",
    "spender": "UNISWAP_V2_ROUTER",
    "amount": "20",
    "amountBaseUnits": "20000000"
  }
}
```

## simulation

Fields:

- `status` (completed / skipped)
- `mode` (single / sequential)
- `sequence[]`
- `overrides_used`
- `override_support`
- `results[]`
- `summary`

Each result includes:

- `txRequestId`
- `success`
- `assumed_success`
- `assumption_reason`
- `gasEstimate`
- `fee`
- `error`

## policy_result

```
{
  "checks": [
    { "id": "...", "title": "...", "status": "PASS|WARN|FAIL", "reason": "...", "metadata": {} }
  ]
}
```

## decision

```
{
  "action": "NEEDS_APPROVAL|BLOCK",
  "severity": "LOW|MED|HIGH",
  "risk_score": 0,
  "summary": "...",
  "reasons": [ ... ]
}
```

## timeline

Array of timeline entries:

```
{ "step": "PLAN_TX", "status": "OK", "title": "planner", "summary": "..." }
```

## needs_input

Stored in `artifacts["needs_input"]` when the graph requires clarification:

```
{
  "questions": ["..."],
  "missing": ["wallet_address", "amount"],
  "resume_from": "PLAN_TX",
  "data": { "chain_options": [1, 10] }
}
```

## assistant_message

FINALIZE writes a user-facing response to `artifacts["assistant_message"]` for
display in the UI or chat flow.

## References

Source files:

- `app/chat/contracts.py`
- `app/contracts/agent_result.py`
- `app/contracts/judge_result.py`
- `defi/` compiler outputs
- `graph/nodes/` artifacts

## Change log

- 2026-01-14: Add final_status/current_step and needs_input contracts.

