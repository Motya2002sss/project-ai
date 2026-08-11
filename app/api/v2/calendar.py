from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v2.dependencies import AuthenticatedRequest, get_authenticated_request
from app.db.session import get_db
from app.schemas.calendar import (
    CalendarBusyBlocksRequest,
    CalendarSyncBatch,
    CalendarSyncResult,
    CalendarSyncStateResponse,
)
from app.services.calendar_service import (
    CalendarSyncConflict,
    get_calendar_sync_state,
    sync_busy_blocks,
)


router = APIRouter(prefix="/calendar", tags=["calendar-v2"])


@router.get("/sync-state", response_model=CalendarSyncStateResponse)
def get_sync_state(
    device_id: str = Query(min_length=1, max_length=128),
    provider: str = Query(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9_-]+$",
    ),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> CalendarSyncStateResponse:
    return get_calendar_sync_state(
        db,
        user=authenticated.user,
        device_id=device_id,
        provider=provider,
    )


@router.put("/busy-blocks", response_model=CalendarSyncResult)
def put_busy_blocks(
    request: CalendarBusyBlocksRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
) -> CalendarSyncResult:
    batch = CalendarSyncBatch.model_validate(
        request.model_dump(exclude={"expected_version"})
    )
    try:
        return sync_busy_blocks(
            db,
            user=authenticated.user,
            sync_batch=batch,
            expected_version=request.expected_version,
        )
    except CalendarSyncConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
