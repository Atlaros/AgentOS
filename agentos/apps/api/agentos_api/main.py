from fastapi import FastAPI

from agentos_api.oauth import router as oauth_router
from agentos_api.rails import router as rails_router
from agentos_api.readiness import router as readiness_router
from agentos_api.routes import router


def mount_rail_routes(app: FastAPI) -> None:
    """Additive Pollar surfaces under /v1/ramps/*. Does not redefine core routes."""
    app.include_router(rails_router)


def create_app() -> FastAPI:
    app = FastAPI(title="AgentOS", version="0.1.0")
    app.include_router(router)
    app.include_router(oauth_router)
    app.include_router(readiness_router)
    mount_rail_routes(app)
    return app


app = create_app()


def run() -> None:
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("agentos_api.main:app", host="0.0.0.0", port=port, reload=False)
