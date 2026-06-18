from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.schemas import ParsedUserMessage
from app.schemas.api import (
    DateSelector,
    GoalResponse,
    MessageRequest,
    MessageResponse,
    PlanResponse,
    ProfileResponse,
    TaskResponse,
)
from app.services.goal_service import list_active_goals
from app.services.message_service import (
    goal_to_response,
    plan_to_response,
    process_user_message,
    profile_to_response,
    task_to_response,
)
from app.services.planning_service import rebuild_day_plan
from app.services.task_service import list_active_tasks
from app.services.user_service import get_or_create_user_by_external_id


router = APIRouter(prefix="/api", tags=["web-api"])


@router.post("/message", response_model=MessageResponse)
def process_message(
    request: MessageRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    return process_user_message(
        db=db,
        user_external_id=request.user_external_id,
        text=request.text,
        source=request.source,
    )


@router.get("/profile/{user_external_id}", response_model=ProfileResponse)
def get_profile(
    user_external_id: str,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    user = get_or_create_user_by_external_id(db=db, external_id=user_external_id)

    return profile_to_response(user, user_external_id)


@router.get("/goals/{user_external_id}", response_model=list[GoalResponse])
def get_goals(
    user_external_id: str,
    db: Session = Depends(get_db),
) -> list[GoalResponse]:
    user = get_or_create_user_by_external_id(db=db, external_id=user_external_id)
    goals = list_active_goals(db=db, user=user)

    return [goal_to_response(goal) for goal in goals]


@router.get("/tasks/{user_external_id}", response_model=list[TaskResponse])
def get_tasks(
    user_external_id: str,
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    user = get_or_create_user_by_external_id(db=db, external_id=user_external_id)
    tasks = list_active_tasks(db=db, user=user)

    return [task_to_response(task) for task in tasks]


@router.get("/plan/{user_external_id}", response_model=PlanResponse)
def get_plan(
    user_external_id: str,
    date: DateSelector = "today",
    db: Session = Depends(get_db),
) -> PlanResponse:
    user = get_or_create_user_by_external_id(db=db, external_id=user_external_id)
    parsed_message = ParsedUserMessage(intent="show_plan", date=date)
    day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)

    return plan_to_response(day_plan)
