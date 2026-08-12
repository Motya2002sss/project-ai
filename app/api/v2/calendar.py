from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v2.dependencies import (
    AuthenticatedRequest,
    get_authenticated_read_request,
    get_authenticated_request,
)
from app.db.session import get_db
from app.schemas.calendar import (
    CalendarBusyBlocksRequest,
    CalendarSyncBatch,
    CalendarSyncResult,
    CalendarSyncStateResponse,
    CalendarDayResponse,
    CalendarMonthResponse,
    CalendarWeekResponse,
)
from app.services.calendar_service import (
    CalendarSyncConflict,
    get_calendar_sync_state,
    sync_busy_blocks,
)
from app.services.calendar_read_service import (
    get_calendar_day,
    get_calendar_month,
    get_calendar_week,
)


router = APIRouter(prefix="/calendar", tags=["calendar-v2"])


@router.get("/day", response_model=CalendarDayResponse)
def get_day(
    response: Response,
    date_: date = Query(alias="date"),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_read_request),
    db: Session = Depends(get_db),
) -> CalendarDayResponse:
    result = get_calendar_day(db, user=authenticated.user, plan_date=date_)
    response.headers["ETag"] = f'"{result.cursor}"'
    return result


@router.get("/week", response_model=CalendarWeekResponse)
def get_week(
    response: Response,
    start: date,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_read_request),
    db: Session = Depends(get_db),
) -> CalendarWeekResponse:
    if start.weekday() != 0:
        raise HTTPException(status_code=422, detail="week start must be Monday")
    result = get_calendar_week(db, user=authenticated.user, start=start)
    response.headers["ETag"] = f'"{result.cursor}"'
    return result


@router.get("/month", response_model=CalendarMonthResponse)
def get_month(
    response: Response,
    month: date,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_read_request),
    db: Session = Depends(get_db),
) -> CalendarMonthResponse:
    if month.day != 1:
        raise HTTPException(status_code=422, detail="month must be its first day")
    result = get_calendar_month(db, user=authenticated.user, month=month)
    response.headers["ETag"] = f'"{result.cursor}"'
    return result


@router.get("/sync-state", response_model=CalendarSyncStateResponse)
def get_sync_state(
    device_id: str = Query(min_length=1, max_length=128),
    provider: str = Query(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9_-]+$",
    ),
    authenticated: AuthenticatedRequest = Depends(get_authenticated_read_request),
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
