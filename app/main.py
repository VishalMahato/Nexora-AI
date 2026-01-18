# app/main.py
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.logging import configure_logging
from app.core.langsmith import configure_langsmith
from app.core.middleware import RunContextMiddleware  
from app.config import get_settings
from db.session import engine
from api.v1.runs import router as runs_router
from api.v1.run_execution import router as run_execution_router
from api.v1.run_approval import router as run_approval_router
from api.v1.run_execute import router as run_execute_router
from api.v1.run_confirmations import router as run_confirmations_router
from api.v1.chat import router as chat_router



def create_app() -> FastAPI:
    configure_logging()
    configure_langsmith()

    app = FastAPI(title="Nexora AI", version="0.1.0")

    # request-scoped run_id context
    app.add_middleware(RunContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    v1_router.include_router(run_execution_router)
    v1_router.include_router(run_approval_router) 
    v1_router.include_router(run_execute_router)
    v1_router.include_router(run_confirmations_router)
    v1_router.include_router(chat_router)

    app.include_router(v1_router)

    return app


app = create_app()
