from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.web import router as web_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
    )

    app.include_router(health_router)
    app.include_router(web_router)

    return app


app = create_app()
