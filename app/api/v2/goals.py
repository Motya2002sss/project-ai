from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.models.goal import Goal
from app.schemas.goals import (
    EvidenceCreate,
    EvidenceMutationResponse,
    EvidenceResponse,
    GoalCreateRequest,
    GoalDeleteRequest,
    GoalMutationResponse,
    GoalResponse,
    GoalUpdateRequest,
    GoalVersionRequest,
    MetricObservationCreate,
    MetricObservationResponse,
    MilestoneCompleteRequest,
    ObservationMutationResponse,
    ProgramApplyRequest,
    ProgramMutationResponse,
    ProgramProposalInput,
    ProgramResponse,
)
from app.services.evidence_service import (
    EvidenceConflict,
    complete_milestone,
    create_evidence,
    create_metric_observation,
)
from app.services.goal_service import (
    GoalConflict,
    create_goal_v2,
    delete_goal_v2,
    get_owned_goal,
    set_goal_status_v2,
    update_goal_v2,
)
from app.services.program_service import (
    ProgramConflict,
    apply_program_proposal,
    preview_program_proposal,
)
from app.schemas.path import EvidencePageResponse, GoalPathResponse, PathResponse
from app.services.path_service import (
    EvidenceCursorError,
    get_goal_detail_read_model,
    get_path_read_model,
    list_goal_evidence_page,
)


router = APIRouter(prefix="/goals", tags=["goals-v2"])
path_router = APIRouter(tags=["path-v2"])


def _goal_or_404(db: Session, authenticated: AuthenticatedRequest, public_id: UUID) -> Goal:
    goal = get_owned_goal(db, user=authenticated.user, public_id=public_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found"
        )
    return goal


def _conflict(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))


@path_router.get("/path", response_model=PathResponse)
def get_path(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> PathResponse:
    return get_path_read_model(db, user=authenticated.user)


@router.get("/{public_id}", response_model=GoalPathResponse)
def get_goal_detail(
    public_id: UUID,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalPathResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    return get_goal_detail_read_model(db, user=authenticated.user, goal=goal)


@router.get("/{public_id}/evidence", response_model=EvidencePageResponse)
def get_goal_evidence(
    public_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> EvidencePageResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        return list_goal_evidence_page(
            db,
            user=authenticated.user,
            goal=goal,
            limit=limit,
            cursor=cursor,
        )
    except EvidenceCursorError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_cursor",
        ) from error


@router.post("", response_model=GoalMutationResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    request: GoalCreateRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalMutationResponse:
    try:
        return create_goal_v2(db, user=authenticated.user, request=request)
    except GoalConflict as error:
        raise _conflict(error) from error


@router.patch("/{public_id}", response_model=GoalMutationResponse)
def update_goal(
    public_id: UUID,
    request: GoalUpdateRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        return update_goal_v2(
            db, user=authenticated.user, goal=goal, request=request
        )
    except GoalConflict as error:
        raise _conflict(error) from error


@router.delete("/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    public_id: UUID,
    request: GoalDeleteRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> Response:
    try:
        delete_goal_v2(
            db,
            user=authenticated.user,
            public_id=public_id,
            request=request,
        )
    except GoalConflict as error:
        if str(error) == "goal_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found"
            ) from error
        raise _conflict(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{public_id}/pause", response_model=GoalMutationResponse)
def pause_goal(
    public_id: UUID,
    request: GoalVersionRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        return set_goal_status_v2(
            db,
            user=authenticated.user,
            goal=goal,
            request=request,
            target_status="paused",
        )
    except GoalConflict as error:
        raise _conflict(error) from error


@router.post("/{public_id}/resume", response_model=GoalMutationResponse)
def resume_goal(
    public_id: UUID,
    request: GoalVersionRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        return set_goal_status_v2(
            db,
            user=authenticated.user,
            goal=goal,
            request=request,
            target_status="active",
        )
    except GoalConflict as error:
        raise _conflict(error) from error


@router.post(
    "/{public_id}/evidence",
    response_model=EvidenceMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_evidence(
    public_id: UUID,
    request: EvidenceCreate,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> EvidenceMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        result = create_evidence(
            db, user=authenticated.user, goal=goal, request=request
        )
    except EvidenceConflict as error:
        raise _conflict(error) from error
    return EvidenceMutationResponse(
        goal=GoalResponse.model_validate(goal),
        evidence=EvidenceResponse.model_validate(result.evidence),
        progress=result.progress,
    )


@router.post(
    "/{public_id}/observations",
    response_model=ObservationMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_metric_observation(
    public_id: UUID,
    request: MetricObservationCreate,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> ObservationMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        result = create_metric_observation(
            db, user=authenticated.user, goal=goal, request=request
        )
    except EvidenceConflict as error:
        raise _conflict(error) from error
    return ObservationMutationResponse(
        goal=GoalResponse.model_validate(goal),
        observation=MetricObservationResponse.model_validate(result.observation),
        progress=result.progress,
    )


@router.post(
    "/{public_id}/milestones/{milestone_id}/complete",
    response_model=GoalMutationResponse,
)
def confirm_milestone(
    public_id: UUID,
    milestone_id: UUID,
    request: MilestoneCompleteRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> GoalMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        result = complete_milestone(
            db,
            user=authenticated.user,
            goal=goal,
            milestone_id=milestone_id,
            expected_version=request.expected_version,
            confirmation=request.confirmation,
            occurred_at=request.occurred_at,
            request_id=request.request_id,
        )
    except EvidenceConflict as error:
        raise _conflict(error) from error
    return GoalMutationResponse(
        goal=GoalResponse.model_validate(goal), progress=result.progress
    )


@router.post("/{public_id}/program/preview", response_model=ProgramProposalInput)
def preview_program(
    public_id: UUID,
    proposal: ProgramProposalInput,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> ProgramProposalInput:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        return preview_program_proposal(
            db, user=authenticated.user, goal=goal, proposal=proposal
        )
    except ProgramConflict as error:
        raise _conflict(error) from error


@router.post("/{public_id}/program/apply", response_model=ProgramMutationResponse)
def apply_program(
    public_id: UUID,
    request: ProgramApplyRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> ProgramMutationResponse:
    goal = _goal_or_404(db, authenticated, public_id)
    try:
        result = apply_program_proposal(
            db, user=authenticated.user, goal=goal, request=request
        )
    except ProgramConflict as error:
        raise _conflict(error) from error
    return ProgramMutationResponse(
        goal=GoalResponse.model_validate(goal),
        program=ProgramResponse.model_validate(result.program),
        progress=result.progress,
    )
