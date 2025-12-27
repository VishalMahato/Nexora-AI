from fastapi import FastAPI
from app.config import get_settings

def create_app() -> FastAPI:
    app = FastAPI(title="AI Service", version="0.1.0")

    @app.get("/healthz")
    async def healthz():
        s = get_settings()
        return {
            "ok": True,
            "llm_model": s.LLM_MODEL,
            "db_configured": bool(s.DATABASE_URL),
            "web3_configured": bool(s.WEB3_SERVICE_URL),
        }

    return app
app = create_app()
