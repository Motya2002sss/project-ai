from fastapi import APIRouter

from app.api.v2.account import router as account_router
from app.api.v2.activities import router as activities_router
from app.api.v2.auth import router as auth_router
from app.api.v2.calendar import router as calendar_router
from app.api.v2.goals import path_router, router as goals_router
from app.api.v2.onboarding import router as onboarding_router
from app.api.v2.planner import router as planner_router
from app.api.v2.planning import router as planning_router


router = APIRouter(prefix="/api/v2")
router.include_router(auth_router)
router.include_router(account_router)
router.include_router(activities_router)
router.include_router(calendar_router)
router.include_router(onboarding_router)
router.include_router(goals_router)
router.include_router(path_router)
router.include_router(planner_router)
router.include_router(planning_router)
