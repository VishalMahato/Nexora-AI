# Backend Architecture

## Purpose

Describe the backend layout, key modules, and where to make changes safely.
This is written to help a new team navigate the codebase quickly.

## Top-Level Layout

```
app/
  chat/            # chat router, LLM wrappers, tools
  contracts/       # shared schemas (AgentResult, JudgeOutput, etc.)
  services/        # service-layer helpers (run orchestration)
  config.py        # environment and defaults
api/
  v1/              # HTTP endpoints (runs, approvals, execute, chat)
graph/             # LangGraph node definitions and wiring
policy/            # policy rules and evaluation
defi/              # tx compilation, router ABIs
chain/             # RPC client + pure helpers
db/                # SQLAlchemy session, models, migrations
llm/               # planner/judge prompts and LLM client
tests/             # pytest suites
```

## Key Entry Points

- `app/main.py`
  - FastAPI app creation
  - Router registration
  - CORS configuration

- `api/v1/run_execution.py`
  - `POST /v1/runs`
  - `POST /v1/runs/{id}/start`

- `api/v1/run_approval.py`
  - `POST /v1/runs/{id}/approve`

- `api/v1/run_execute.py`
  - `POST /v1/runs/{id}/execute`

- `api/v1/chat.py`
  - `POST /v1/chat/route`

## Chat Layer (app/chat)

- `app/chat/router.py`
  - Core routing logic: QUERY / ACTION / CLARIFY / GENERAL
  - Pending state handling for clarify follow-ups
  - Calls tools for queries and runs for actions

- `app/chat/llm.py`
  - LLM calls for classifier and response polishing
  - Controlled by config flags

- `app/chat/prompts.py`
  - System prompts for classification and chat responses

- `app/chat/tools.py`
  - Read-only query helpers (snapshot, balance, allowlists)

- `app/chat/state_store.py`
  - In-memory conversation state (TTL-based)

## Run Execution Layer (graph)

The execution graph is where deterministic processing happens. Key nodes:

- INPUT_NORMALIZE
- PRECHECK (cheap validation, may set `needs_input`)
- WALLET_SNAPSHOT
- PLAN_TX
- BUILD_TXS
- SIMULATE_TXS (sequential)
- POLICY_EVAL
- SECURITY_EVAL
- JUDGE_AGENT
- REPAIR_ROUTER / REPAIR_PLAN_TX
- CLARIFY (ensures questions are present)
- FINALIZE

The graph produces:

- Artifacts (tx_plan, tx_requests, simulation, policy_result, decision)
- Timeline entries for UI
- `assistant_message` in artifacts

## Policy Layer (policy/)

- `policy/rules.py` defines each rule
- `policy/engine.py` evaluates rules and emits `policy_result` + `decision`
- Rules enforce allowlists, simulation success, and invariants

## DeFi Compiler (defi/)

- `defi/compiler_uniswap_v2.py` builds approve + swap tx_requests
- Uses allowlist config and on-chain quote for minOut

## Chain Layer (chain/)

Two categories:

1) RPC client
   - `chain/client.py` and RPC helpers
2) Pure helpers
   - `chain/snapshot.py` (no DB, safe for tools)

## LLM Layer (llm/)

- `llm/client.py` is the shared LLM wrapper used by planner/judge
- `llm/prompts.py` defines planner/judge prompts

## Service Layer

- `app/services/runs_service.py` contains run creation and start logic
  used by both HTTP routes and chat action flow.
  - Resolves `final_status` and maps it to `runs.status`.

## Extension Guidelines

- New read-only query should go in `app/chat/tools.py`.
- New action node should be a graph node + artifacts + policy updates.
- Update the API reference if you add or change endpoints.

## References

- `docs/project/03-run-lifecycle.md`
- `docs/project/04-chat-router.md`
- `docs/project/06-data-models.md`

## Change log

- 2026-01-14: Add PRECHECK/CLARIFY nodes and final_status ownership.

