from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.schemas.api import DaySnapshotResponse
from app.schemas.mobile import (
    MobileActionResponse,
    MobileCaptureRequest,
    MobileInteractionResponseRequest,
    MobileTaskMutationResponse,
    MobileTaskStatusV2Request,
)
from app.services.message_service import process_authenticated_user_message
from app.services.idempotency_service import IdempotencyConflict
from app.services.mobile_service import (
    get_mobile_today_snapshot,
    message_to_mobile_response,
    MobileTaskConflict,
    update_versioned_mobile_task_status,
)


router = APIRouter(tags=["planner-v2"])


@router.get("/today", response_model=DaySnapshotResponse)
def get_today(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> DaySnapshotResponse:
    return get_mobile_today_snapshot(db, authenticated.user)


@router.post("/capture", response_model=MobileActionResponse)
def capture(
    request: MobileCaptureRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> MobileActionResponse:
    try:
        response = process_authenticated_user_message(
            db,
            user=authenticated.user,
            text=request.text,
            source="ios_text",
            request_id=request.request_id,
        )
    except IdempotencyConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return message_to_mobile_response(response)


@router.post(
    "/interactions/{interaction_id}/responses",
    response_model=MobileActionResponse,
)
def respond_to_interaction(
    interaction_id: str,
    request: MobileInteractionResponseRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> MobileActionResponse:
    try:
        response = process_authenticated_user_message(
            db,
            user=authenticated.user,
            text=request.text,
            source="ios_text",
            request_id=request.request_id,
            interaction_id=interaction_id,
            option_id=request.option_id,
        )
    except IdempotencyConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return message_to_mobile_response(response)


@router.patch(
    "/tasks/{task_id}/status",
    response_model=MobileTaskMutationResponse,
)
def update_task_status(
    task_id: int,
    request: MobileTaskStatusV2Request,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> MobileTaskMutationResponse:
    try:
        response = update_versioned_mobile_task_status(
            db=db,
            user=authenticated.user,
            task_id=task_id,
            task_status=request.status,
            request_id=request.request_id,
            expected_plan_version=request.expected_plan_version,
        )
    except MobileTaskConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return response
