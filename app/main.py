from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AI Service", version="0.1.0")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
