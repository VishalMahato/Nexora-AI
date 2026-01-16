# Contributing Guide (Nexora AI)

This guide summarizes the minimum you need to get productive, based on the
project docs and current repo layout.

## Quick Start (local)

Prereqs:
- Python 3.12 (see `.python-version`)
- Postgres
- RPC provider access
- Optional: `uv` for faster env management

Setup:
1) Create `.env` (see `.env.example`)
2) Install deps
3) Run migrations
4) Start the API

Example (uv):
```bash
uv venv
uv pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Smoke test:
```bash
curl -s -X POST http://localhost:8000/v1/chat/route \
  -H "Content-Type: application/json" \
  -d '{"message":"what are the supported tokens?"}' | python -m json.tool
```

Optional UI:
```bash
streamlit run streamlit_app.py
```

## Configuration Essentials

Settings load from `app/config.py` with overrides in `.env`.

Required:
- `DATABASE_URL`
- `RPC_URLS`

LLM (if enabled):
- `LLM_ENABLED`, `LLM_MODEL`, `LLM_PROVIDER`, `OPENAI_API_KEY`

Allowlists (safety critical):
- `ALLOWLIST_TO`
- `ALLOWLIST_TO_ALL` (true/false, disable target allowlist checks for local dev)
- `ALLOWLISTED_TOKENS`
- `ALLOWLISTED_ROUTERS`

See `docs/config/08-config-and-env.md` for formats and defaults.

## Codebase Map (what does what)

API surface:
- `app/main.py` wires FastAPI, middleware, and `/v1` routers.
- `api/v1/` holds request/response endpoints for runs and chat.

Core run pipeline (LangGraph):
- `graph/graph.py` defines the step graph.
- `graph/nodes/` contains each step implementation.
- `graph/state.py` defines `RunState` and shared artifacts.

Persistence:
- `db/models/` SQLAlchemy models (`run`, `run_step`, `tool_call`)
- `db/repos/` data access patterns used by services and endpoints
- `alembic/` migrations and `alembic.ini`

Chat + LLM:
- `app/chat/` routing, prompts, and tools
- `llm/` provider client and prompt templates

Web3 / chain access:
- `chain/` RPC client, ABIs, snapshots, and helpers

Policy + safety:
- `policy/` rules and engine used during graph execution

Observability:
- `tools/tool_runner.py` logs tool calls
- `app/core/logging.py`, `app/core/middleware.py` handle logs and run context

## Core Behavior to Understand

Run lifecycle:
- The `/v1/runs` endpoints create and execute runs.
- The graph enforces simulation, policy checks, and a human approval gate.
- Each run stores step-by-step audit artifacts in the DB.

Chat routing:
- `/v1/chat/route` classifies intents into QUERY/ACTION/CLARIFY.
- Only one ACTION intent is allowed at a time.

Safety invariants (do not break):
- Backend never signs or broadcasts transactions.
- All actions are allowlisted.
- Simulation is required before approval.
- Human approval is mandatory.

Reference docs: `docs/architecture/03-run-lifecycle.md`,
`docs/backend/04-chat-router.md`, `docs/security/12-security-safety.md`.

## Tests

Run all tests:
```bash
pytest
```

Note: LLM and RPC calls are mocked in unit tests. Set `LLM_ENABLED=false`
unless explicitly mocked.

More details: `docs/tests/10-testing.md`.

## Git Workflow

- Work on feature branches; do not commit directly to `main`.
- Use Conventional Commits (e.g. `feat:`, `fix:`, `chore:`).

See `docs/process/git-workflow.md` for the naming conventions.

## Known Limitations (current)

- In-memory chat state is not shared across instances.
- Simulation uses guarded assumptions for approvals in stateless `eth_call`.
- Only one ACTION intent supported per conversation.

Details: `docs/ops/14-known-issues.md`.

## Where to Learn Next (recommended order)

Docs are now categorized under `docs/` (design, product, architecture, backend,
config, setup, security, ops, UI, tests). Start with `docs/README.md` for the
current index, then follow the reading order:
- `docs/README.md` (categorized doc index)
- `docs/product/00-product-brief.md`
- `docs/architecture/01-architecture-overview.md`
- `docs/architecture/02-backend-architecture.md`
- `docs/backend/05-api-reference.md`
- `docs/backend/06-data-models.md`
- `docs/backend/07-llm-prompts.md`
- `docs/ops/11-ops-deploy.md`
- `docs/ui/13-frontend-integration.md`

Supplemental:
- `docs/design/architecture-overview.md`
- `docs/design/ui-demo-spec.md`
