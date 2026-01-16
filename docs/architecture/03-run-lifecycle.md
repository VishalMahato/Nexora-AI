# Run Lifecycle

## Purpose

Describe how runs move through the graph, what artifacts are produced, and how
status changes are determined.

## Run Statuses

Common statuses (current):

- CREATED
- RUNNING
- PAUSED
- AWAITING_APPROVAL
- APPROVED_READY
- SUBMITTED
- CONFIRMED
- REVERTED
- BLOCKED
- FAILED
- REJECTED

Optional / future:

- NEEDS_INPUT (graph asks for missing fields)
- EXECUTING (frontend has submitted txs)
- COMPLETED

## Final Status (Outcome)

Final status is a run outcome derived from artifacts (service-owned):

- READY
- NEEDS_INPUT
- BLOCKED
- FAILED
- NOOP

Mapping (current):

- READY -> AWAITING_APPROVAL
- NEEDS_INPUT / NOOP -> PAUSED
- BLOCKED -> BLOCKED
- FAILED -> FAILED

## High-Level Flow

```
POST /v1/runs
POST /v1/runs/{id}/start
  -> Graph executes nodes in order
  -> Artifacts and timeline produced
  -> Status and final_status set by runs_service
  -> If missing inputs are detected, run pauses with NEEDS_INPUT
```

## Node Order (Current)

1) INPUT_NORMALIZE
   - Normalizes intent string.

2) PRECHECK
   - Validates wallet/chain/intent cheaply; may set `needs_input`.

3) WALLET_SNAPSHOT
   - Reads wallet balances and allowances.

4) PLAN_TX
   - LLM planner creates `tx_plan` with actions.

5) BUILD_TXS
   - Compiler builds `tx_requests` and candidates.

6) SIMULATE_TXS
   - Simulates txs. Sequential mode for approve -> swap.

7) POLICY_EVAL
   - Deterministic checks on artifacts.

8) SECURITY_EVAL
   - Wraps policy results as `security_result` AgentResult.

9) JUDGE_AGENT
   - Produces `judge_result` AgentResult (PASS / NEEDS_REWORK / BLOCK).

10) REPAIR_ROUTER / REPAIR_PLAN_TX
   - Optional bounded repair (if enabled).

11) CLARIFY
    - Ensures `needs_input.questions` exists (idempotent).

12) FINALIZE
    - Composes `assistant_message` and finalize metadata.

## Artifacts (Core)

- `normalized_intent`
- `needs_input`
- `wallet_snapshot`
- `tx_plan`
- `tx_requests`
- `simulation`
- `policy_result`
- `decision`
- `security_result`
- `judge_result`
- `assistant_message`
- `final_status_suggested`
- `timeline`
- `user_inputs`

## Timeline

Each node adds a timeline entry:

- `step`
- `status`
- `title`
- `summary`

UI renders this timeline for explainability.

`current_step` on the run row is updated when a step logs `STARTED`.

## Policy Result and Decision

Policy rules produce a `policy_result` with checks:

```
{ id, title, status, reason, metadata }
```

The decision summarizes the overall outcome:

```
{ action, risk_score, severity, summary, reasons[] }
```

## Judge Verdict Mapping

Judge output:

- PASS -> OK
- NEEDS_REWORK -> WARN (may trigger repair or require review)
- BLOCK -> BLOCKED

In current behavior, `BLOCK` stops execution; other verdicts proceed to approval.

## Failure Handling

- Invalid planner output -> fallback noop plan.
- Simulation revert -> policy FAIL -> BLOCKED.
- LLM errors -> degrade to safe defaults and WARN.
- Fatal errors set `fatal_error` and resolve to `final_status=FAILED`.

## Execution Path (Frontend)

When run is `AWAITING_APPROVAL`:

1) UI calls `POST /v1/runs/{id}/approve`
2) UI calls `POST /v1/runs/{id}/execute`
3) Backend returns `tx_requests`
4) Frontend signs via wallet

## Resume Flow (NEEDS_INPUT)

1) Run ends with `status=PAUSED` and `final_status=NEEDS_INPUT`.
2) UI collects answers from the user.
3) UI calls `POST /v1/runs/{id}/resume` with an `answers` map.
4) Service loads the checkpoint, merges `answers` into `artifacts.user_inputs`,
   clears `needs_input`, and re-runs the graph.

Note: `needs_input.resume_from` is recorded for future use; the current resume
implementation restarts the graph with the restored state.

## Checkpointing

- Graph checkpoints are stored per run with `thread_id = run_id`.
- Resume fails with 409 when no checkpoint exists (run never started).

## References

- `docs/project/06-data-models.md`
- `docs/project/12-security-safety.md`

## Change log

- 2026-01-14: Add final_status mapping, PRECHECK/CLARIFY, and current_step.
- 2026-01-15: Add resume flow and checkpointing notes.

