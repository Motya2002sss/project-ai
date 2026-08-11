from fastapi import APIRouter

from app.api.v2.account import router as account_router
from app.api.v2.auth import router as auth_router
from app.api.v2.onboarding import router as onboarding_router


router = APIRouter(prefix="/api/v2")
router.include_router(auth_router)
router.include_router(account_router)
router.include_router(onboarding_router)
