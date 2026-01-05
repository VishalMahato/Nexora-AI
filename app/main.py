from fastapi import FastAPI, APIRouter
from sqlalchemy import text

from app.config import get_settings
from db.session import engine
from api.v1.runs import router as runs_router


def create_app() -> FastAPI:
    app = FastAPI(title="Nexora AI", version="0.1.0")

    @app.get("/healthz")
    async def healthz():
        settings = get_settings()

        db_ok = True
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = False

        return {"ok": True, "llm_model": settings.LLM_MODEL, "db_ok": db_ok}

    v1_router = APIRouter(prefix="/v1")
    v1_router.include_router(runs_router)
    app.include_router(v1_router)

    return app


app = create_app()
