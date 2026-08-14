from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.mobile import router as mobile_router
from app.api.v2 import router as api_v2_router
from app.core.config import settings


def create_mobile_dogfood_app() -> FastAPI:
    dogfood_app = FastAPI(
        title=f"{settings.app_name} Mobile Dogfood",
        debug=settings.app_debug,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    dogfood_app.include_router(health_router)
    dogfood_app.include_router(mobile_router)
    dogfood_app.include_router(api_v2_router)
    return dogfood_app


app = create_mobile_dogfood_app()
