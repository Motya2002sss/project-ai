from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.schemas.activity import (
    LearningLogRequest,
    LearningMutationResponse,
    NutritionLogRequest,
    NutritionMutationResponse,
    ProgramAdaptationRequest,
    ProgramAdaptationResponse,
    ProgramAdaptationUnavailableResponse,
    WorkoutDraftRequest,
    WorkoutFinishRequest,
    WorkoutMutationResponse,
    WorkoutSnapshotResponse,
)
from app.services.activity_service import (
    ActivityConflict,
    ActivityUnavailable,
    CandidateBuilder,
    finish_workout,
    get_workout_snapshot,
    log_learning,
    log_nutrition,
    propose_program_adaptation,
    save_workout_draft,
)


router = APIRouter(prefix="/activities", tags=["activities-v2"])


def get_adaptation_candidate_builder() -> CandidateBuilder | None:
    return None


def _activity_error(error: ActivityConflict) -> HTTPException:
    reason = str(error)
    if reason == "workout_not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )
    if reason in {"related_record_not_found", "program_not_found"}:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity resource not found",
        )
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=reason)


@router.get(
    "/workouts/{task_id}",
    response_model=WorkoutSnapshotResponse,
)
def get_workout(
    task_id: int,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> WorkoutSnapshotResponse:
    try:
        return get_workout_snapshot(db, user=authenticated.user, task_id=task_id)
    except ActivityConflict as error:
        raise _activity_error(error) from error


@router.patch(
    "/workouts/{task_id}/draft",
    response_model=WorkoutMutationResponse,
)
def save_draft(
    task_id: int,
    request: WorkoutDraftRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> WorkoutMutationResponse:
    try:
        return save_workout_draft(
            db,
            user=authenticated.user,
            task_id=task_id,
            request=request,
        )
    except ActivityConflict as error:
        raise _activity_error(error) from error


@router.post(
    "/workouts/{task_id}/finish",
    response_model=WorkoutMutationResponse,
)
def finish(
    task_id: int,
    request: WorkoutFinishRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> WorkoutMutationResponse:
    try:
        return finish_workout(
            db,
            user=authenticated.user,
            task_id=task_id,
            request=request,
        )
    except ActivityConflict as error:
        raise _activity_error(error) from error


@router.post(
    "/nutrition",
    response_model=NutritionMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_nutrition_log(
    request: NutritionLogRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> NutritionMutationResponse:
    try:
        return log_nutrition(db, user=authenticated.user, request=request)
    except ActivityConflict as error:
        raise _activity_error(error) from error


@router.post(
    "/learning",
    response_model=LearningMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_learning_log(
    request: LearningLogRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> LearningMutationResponse:
    try:
        return log_learning(db, user=authenticated.user, request=request)
    except ActivityConflict as error:
        raise _activity_error(error) from error


@router.post(
    "/programs/{program_id}/adaptation-candidate",
    response_model=ProgramAdaptationResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ProgramAdaptationUnavailableResponse
        }
    },
)
def create_adaptation_candidate(
    program_id: UUID,
    request: ProgramAdaptationRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
    candidate_builder: CandidateBuilder | None = Depends(
        get_adaptation_candidate_builder
    ),
) -> ProgramAdaptationResponse | JSONResponse:
    try:
        return propose_program_adaptation(
            db,
            user=authenticated.user,
            program_id=program_id,
            request=request,
            candidate_builder=candidate_builder,
        )
    except ActivityConflict as error:
        raise _activity_error(error) from error
    except ActivityUnavailable:
        unavailable = ProgramAdaptationUnavailableResponse()
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=unavailable.model_dump(mode="json"),
        )
