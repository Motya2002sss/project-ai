from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.llm.schemas import ParsedUserMessage
from app.models.user import User
from app.schemas.api import DaySnapshotResponse
from app.schemas.mobile import (
    MobileActionResponse,
    MobileCaptureRequest,
    MobileInteractionResponseRequest,
    MobileTaskMutationResponse,
    MobileTaskStatusRequest,
)
from app.services.message_service import day_snapshot_to_response, process_user_message
from app.services.mobile_service import message_to_mobile_response, update_mobile_task_status
from app.services.planning_service import rebuild_day_plan
from app.services.user_service import get_or_create_user_by_external_id


router = APIRouter(prefix="/api/v1", tags=["mobile-v1"])
bearer = HTTPBearer(auto_error=False)


def get_mobile_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    configured_token = settings.mobile_dogfood_token

    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mobile dogfood authentication is not configured",
        )

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not compare_digest(credentials.credentials, configured_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_or_create_user_by_external_id(
        db=db,
        external_id=settings.mobile_dogfood_user_external_id,
    )


@router.get("/today", response_model=DaySnapshotResponse)
def get_today(
    user: User = Depends(get_mobile_user),
    db: Session = Depends(get_db),
) -> DaySnapshotResponse:
    day_plan = rebuild_day_plan(
        db=db,
        user=user,
        parsed_message=ParsedUserMessage(intent="show_plan", date="today"),
    )
    return day_snapshot_to_response(db, user, day_plan)


@router.post("/capture", response_model=MobileActionResponse)
def capture(
    request: MobileCaptureRequest,
    user: User = Depends(get_mobile_user),
    db: Session = Depends(get_db),
) -> MobileActionResponse:
    response = process_user_message(
        db=db,
        user_external_id=user.external_id or settings.mobile_dogfood_user_external_id,
        text=request.text,
        source="ios_text",
        request_id=request.request_id,
    )
    return message_to_mobile_response(response)


@router.post(
    "/interactions/{interaction_id}/responses",
    response_model=MobileActionResponse,
)
def respond_to_interaction(
    interaction_id: str,
    request: MobileInteractionResponseRequest,
    user: User = Depends(get_mobile_user),
    db: Session = Depends(get_db),
) -> MobileActionResponse:
    response = process_user_message(
        db=db,
        user_external_id=user.external_id or settings.mobile_dogfood_user_external_id,
        text=request.text,
        source="ios_text",
        request_id=request.request_id,
        interaction_id=interaction_id,
        option_id=request.option_id,
    )
    return message_to_mobile_response(response)


@router.patch(
    "/tasks/{task_id}/status",
    response_model=MobileTaskMutationResponse,
)
def update_task_status(
    task_id: int,
    request: MobileTaskStatusRequest,
    user: User = Depends(get_mobile_user),
    db: Session = Depends(get_db),
) -> MobileTaskMutationResponse:
    response = update_mobile_task_status(
        db=db,
        user=user,
        task_id=task_id,
        task_status=request.status,
    )

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return response
