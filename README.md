# Nexora AI Service

Production-ready FastAPI service for blockchain intent orchestration with
auditable run steps, tool-call logging, and policy gating.

## Highlights
- Deterministic graph execution with step-level audit trail
- Conversational router for QUERY/ACTION/CLARIFY intents
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
Client -> /v1/chat/route -> tools (query) or runs (action)
```

## Requirements
- Python 3.12
- PostgreSQL 14+

## Local setup
```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn app.main:app --reload
```
If you prefer plain `venv`:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Docker setup (auto-reload)
```bash
docker compose up --build
```
`docker-compose.override.yml` bind-mounts the repo and enables `--reload`.

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
- `POST /v1/chat/route` route a chat message (QUERY/ACTION/CLARIFY)
- `POST /v1/runs` create a run
- `POST /v1/runs/{id}/start` execute the graph
- `POST /v1/runs/{id}/approve` approve
- `POST /v1/runs/{id}/reject` reject
- `GET  /v1/runs/{id}` fetch run details
- `GET  /v1/runs/{id}?includeArtifacts=true` fetch run + artifacts
- `GET  /v1/runs/{id}/tool-calls` tool-call timeline

## Supported intents (MVP)
- Native transfers:
  - `send 0.0001 eth to 0x...`
  - `transfer 0.1 matic to 0x...`
- DeFi swaps (approve + swap) on allowlisted tokens/routers:
  - `swap 1 usdc to weth`

If the intent does not match supported formats, the planner returns a noop plan.

## Conversational intent rules
- GENERAL handles greetings/help without triggering clarifications
- At any time, exactly one ACTION intent may be active per conversation.
- QUERY intents are non-blocking and can be answered while an ACTION is pending.

## Tests
```bash
uv run pytest
```

## Demo UI (Streamlit)
```bash
uv run streamlit run streamlit_app.py
```
Set `Backend URL` to your API (default: `http://localhost:8000`).

## Project layout
```
api/        FastAPI routes and schemas
app/        app config and middleware
app/chat/   chat routing, tools, and conversation state
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


