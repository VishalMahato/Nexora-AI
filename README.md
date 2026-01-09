# Nexora AI Service

Production-ready FastAPI service for blockchain intent orchestration with
auditable run steps, tool-call logging, and policy gating.

## Highlights
- Deterministic graph execution with step-level audit trail
- Tool-call instrumentation for all external calls
- Policy engine for risk checks and approval gating
- Persisted artifacts for resumable runs

## Architecture (high level)
```
Client -> FastAPI -> LangGraph -> Policy Engine -> Web3 RPC
             |           |
             |           +-> run_steps (audit)
             +-> tool_calls (observability)
             +-> runs (FSM + artifacts)
```

## Requirements
- Python 3.12
- PostgreSQL 14+

## Quick start
```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app.main:app --reload
```

## Configuration
Create a `.env` (see `.env.example`):

Required:
- `DATABASE_URL`
- `RPC_URLS`
- `ALLOWLIST_TO` (JSON list of allowlisted target addresses)

Optional:
- `LLM_MODEL`
- `LOG_LEVEL`, `LOG_JSON`
- `LANGSMITH_*`

## Database migrations
```bash
alembic upgrade head
```

## API
Base: `http://localhost:8000`

Endpoints:
- `POST /v1/runs` create a run
- `POST /v1/runs/{id}/start` execute the graph
- `POST /v1/runs/{id}/approve` approve
- `POST /v1/runs/{id}/reject` reject
- `GET  /v1/runs/{id}` fetch run details
- `GET  /v1/runs/{id}/tool-calls` tool-call timeline

## Supported intent (MVP)
Native transfer only:
- `send 0.0001 eth to 0x...`
- `transfer 0.1 matic to 0x...`

If the intent does not match this format, the planner returns a noop plan.

## Tests
```bash
pytest
```

## Project layout
```
api/        FastAPI routes and schemas
app/        app config and middleware
chain/      web3 client and RPC helpers
db/         models, repos, migrations
graph/      LangGraph nodes and state
policy/     policy rules and engine
tools/      tool-call instrumentation
```

## Contributing
1. Create a feature branch
2. Add tests for behavior changes
3. Ensure migrations are included for schema changes


