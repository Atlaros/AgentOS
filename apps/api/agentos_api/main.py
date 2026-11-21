from fastapi import FastAPI

from agentos_api.oauth import router as oauth_router
from agentos_api.readiness import router as readiness_router
from agentos_api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="AgentOS", version="0.1.0")
    app.include_router(router)
    app.include_router(oauth_router)
    app.include_router(readiness_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("agentos_api.main:app", host="0.0.0.0", port=8080, reload=False)
