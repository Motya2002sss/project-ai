from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.schemas.onboarding import (
    OnboardingApplyRequest,
    OnboardingPreviewRequest,
    OnboardingPreviewResponse,
    OnboardingStateResponse,
)
from app.services.onboarding_service import (
    OnboardingConflict,
    apply_onboarding_preview,
    get_latest_onboarding_preview,
    preview_onboarding,
)


router = APIRouter(prefix="/onboarding", tags=["onboarding-v2"])


def _conflict(error: OnboardingConflict) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@router.get("", response_model=OnboardingStateResponse)
def get_onboarding_state(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> OnboardingStateResponse:
    preview = get_latest_onboarding_preview(db, user=authenticated.user)
    if preview is None:
        return OnboardingStateResponse(status="not_started", preview=None)
    return OnboardingStateResponse(
        status="completed" if preview.status == "applied" else "in_progress",
        preview=OnboardingPreviewResponse.model_validate(preview),
    )


@router.post("/preview", response_model=OnboardingPreviewResponse)
def create_or_correct_preview(
    request: OnboardingPreviewRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> OnboardingPreviewResponse:
    try:
        preview = preview_onboarding(
            db,
            user=authenticated.user,
            narrative=request.narrative,
            resource_budget=request.resource_budget,
            request_id=request.request_id,
            preview_id=request.preview_id,
            expected_version=request.expected_version,
        )
    except OnboardingConflict as error:
        raise _conflict(error) from error
    return OnboardingPreviewResponse.model_validate(preview)

@router.post("/apply", response_model=OnboardingPreviewResponse)
def apply_preview(
    request: OnboardingApplyRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> OnboardingPreviewResponse:
    try:
        preview = apply_onboarding_preview(
            db,
            user=authenticated.user,
            preview_id=request.preview_id,
            expected_version=request.expected_version,
        )
    except OnboardingConflict as error:
        raise _conflict(error) from error
    return OnboardingPreviewResponse.model_validate(preview)
