# Dev Setup

## Prerequisites

- Python 3.12 (matches project tooling)
- Postgres
- RPC provider access
- Optional: `uv` for faster Python environment management

## Environment

Copy or create `.env` and set:

- `DATABASE_URL`
- `OPENAI_API_KEY` (if LLM enabled)
- `LLM_ENABLED=true`
- `RPC_URLS`

## Install Dependencies

Option A (uv):

```
uv venv
uv pip install -r requirements.txt
```

Option B (venv + pip):

```
python -m venv .venv
./.venv/Scripts/activate
pip install -r requirements.txt
```

## Database

Run migrations (if needed):

```
alembic upgrade head
```

## Run Backend

```
uvicorn app.main:app --reload
```

Health check:

```
curl http://localhost:8000/healthz
```

## Run Streamlit UI

```
streamlit run streamlit_app.py
```

## Local Smoke Test (chat)

```
curl -s -X POST http://localhost:8000/v1/chat/route \
  -H "Content-Type: application/json" \
  -d '{"message":"what are the supported tokens?"}' | python -m json.tool
```

## Notes

- If LLM is disabled, chat falls back to safe default responses.
- Keep RPC rate limits in mind when running tests.

## Change log

- 2026-01-14: Align Python version with current tooling.

