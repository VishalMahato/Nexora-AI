# Ops and Deployment

## Purpose

Operational guidance for running Nexora in a staging or production environment.

## Deployment Options

1) Local / single node
   - Uvicorn running FastAPI
   - Postgres on the same machine

2) Docker
   - `Dockerfile` and `docker-compose.yml` provided

## Docker Notes

- `docker-compose.yml` is intended for local staging.
- Use a managed Postgres instance for production.
- Do not bake secrets into images; use env vars or secret mounts.

## Environment

Required:

- `DATABASE_URL`
- `RPC_URLS`
- `OPENAI_API_KEY` (if LLM enabled)

Recommended:

- `LLM_ENABLED=true`
- `LOG_LEVEL=INFO`

## Migrations

```
alembic upgrade head
```

Run migrations on deploy before starting the app.

## Health Checks

- `GET /healthz`
  - returns `{ ok, llm_model, db_ok }`

## Secrets Handling

- Store API keys in environment variables or secret manager.
- Never commit `.env` with secrets.

## Logging

Structured logging is enabled via settings:

- `LOG_LEVEL`
- `LOG_JSON`

## Monitoring (minimal)

- HTTP 200 rate for `/healthz`
- Error rate on `/v1/runs/*`
- Latency for `/v1/runs/{id}/start`

## Scaling Notes

- Chat pending state is in-memory; multiple instances require shared storage
  if you need persistence across instances.
- LLM latency can dominate; consider async workers if needed.

## Backups

Backup the Postgres database on a regular schedule.

## Incident Checklist (short)

- Check `/healthz`
- Check DB connectivity and migrations
- Check RPC provider rate limits
- Check LLM provider errors

## Rollback

- Roll back the application version.
- Roll back DB only if migrations were destructive (avoid if possible).
