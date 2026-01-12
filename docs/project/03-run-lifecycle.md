# Run Lifecycle

## Purpose

Describe how runs move through the graph, what artifacts are produced, and how
status changes are determined.

## Run Statuses

Common statuses (current):

- CREATED
- RUNNING
- AWAITING_APPROVAL
- APPROVED_READY
- BLOCKED
- FAILED

Optional / future:

- NEEDS_INPUT (graph asks for missing fields)
- EXECUTING (frontend has submitted txs)
- COMPLETED

## High-Level Flow

```
POST /v1/runs
POST /v1/runs/{id}/start
  -> Graph executes nodes in order
  -> Artifacts and timeline produced
  -> Status set by FINALIZE
```

## Node Order (Current)

1) INPUT_NORMALIZE
   - Normalizes intent string.

2) WALLET_SNAPSHOT
   - Reads wallet balances and allowances.

3) PLAN_TX
   - LLM planner creates `tx_plan` with actions.

4) BUILD_TXS
   - Compiler builds `tx_requests` and candidates.

5) SIMULATE_TXS
   - Simulates txs. Sequential mode for approve -> swap.

6) POLICY_EVAL
   - Deterministic checks on artifacts.

7) SECURITY_EVAL
   - Wraps policy results as `security_result` AgentResult.

8) JUDGE_AGENT
   - Produces `judge_result` AgentResult (PASS / NEEDS_REWORK / BLOCK).

9) REPAIR_ROUTER / REPAIR_PLAN_TX
   - Optional bounded repair (if enabled).

10) FINALIZE
    - Maps outcomes to run status and response.

## Artifacts (Core)

- `normalized_intent`
- `wallet_snapshot`
- `tx_plan`
- `tx_requests`
- `simulation`
- `policy_result`
- `decision`
- `security_result`
- `judge_result`
- `timeline`

## Timeline

Each node adds a timeline entry:

- `step`
- `status`
- `title`
- `summary`

UI renders this timeline for explainability.

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
- NEEDS_REWORK -> WARN (still AWAITING_APPROVAL in F21)
- BLOCK -> BLOCKED

In current behavior, `BLOCK` stops execution; other verdicts proceed to approval.

## Failure Handling

- Invalid planner output -> fallback noop plan.
- Simulation revert -> policy FAIL -> BLOCKED.
- LLM errors -> degrade to safe defaults and WARN.

## Execution Path (Frontend)

When run is `AWAITING_APPROVAL`:

1) UI calls `POST /v1/runs/{id}/approve`
2) UI calls `POST /v1/runs/{id}/execute`
3) Backend returns `tx_requests`
4) Frontend signs via wallet

## References

- `docs/project/06-data-models.md`
- `docs/project/12-security-safety.md`

