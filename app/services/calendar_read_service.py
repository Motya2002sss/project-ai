from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.calendar import CalendarBusyBlock, TemporaryLifeMode
from app.models.day_plan import DayPlan
from app.models.evidence import MetricObservation
from app.models.goal import Goal
from app.models.plan_item import PlanItem
from app.models.program import GoalMilestone, WeeklyCommitment
from app.models.user import User
from app.schemas.calendar import (
    CalendarCommitmentLoad,
    CalendarDayItem,
    CalendarDayResponse,
    CalendarDaySummary,
    CalendarInterval,
    CalendarMonthDeadline,
    CalendarMonthLifeMode,
    CalendarMonthMeasurement,
    CalendarMonthMilestone,
    CalendarMonthResponse,
    CalendarMonthTension,
    CalendarWeekResponse,
)
from app.services.planning_service import DEFAULT_DAY_END, DEFAULT_DAY_START


UTC = timezone.utc


def get_calendar_day(db: Session, *, user: User, plan_date: date) -> CalendarDayResponse:
    zone = _user_zone(user)
    start_at, end_at = _planning_day_bounds(user, plan_date, zone)
    plan = db.scalar(
        select(DayPlan)
        .options(selectinload(DayPlan.items).selectinload(PlanItem.task))
        .where(DayPlan.user_id == user.id, DayPlan.date == plan_date)
    )
    busy = _busy_intervals(db, user_id=user.id, start_at=start_at, end_at=end_at)
    items = _day_items(plan, zone) if plan is not None else []
    occupied = busy + [
        CalendarInterval(start_at=item.start_at, end_at=item.end_at)
        for item in items
        if item.start_at is not None and item.end_at is not None
    ]
    response = CalendarDayResponse(
        date=plan_date,
        timezone=user.timezone,
        materialized=plan is not None,
        plan_version=plan.version if plan is not None else None,
        summary=plan.summary if plan is not None else None,
        items=items,
        busy_intervals=busy,
        free_intervals=_free_intervals(start_at, end_at, occupied),
        cursor="",
    )
    response.cursor = _cursor(response.model_dump(exclude={"cursor"}, mode="json"))
    return response


def get_calendar_week(db: Session, *, user: User, start: date) -> CalendarWeekResponse:
    end = start + timedelta(days=6)
    zone = _user_zone(user)
    plans = list(
        db.scalars(
            select(DayPlan)
            .options(selectinload(DayPlan.items).selectinload(PlanItem.task))
            .where(
                DayPlan.user_id == user.id,
                DayPlan.date >= start,
                DayPlan.date <= end,
            )
            .order_by(DayPlan.date)
        ).unique()
    )
    plans_by_date = {plan.date: plan for plan in plans}
    days: list[CalendarDaySummary] = []
    for offset in range(7):
        current = start + timedelta(days=offset)
        plan = plans_by_date.get(current)
        items = _day_items(plan, zone) if plan is not None else []
        days.append(
            CalendarDaySummary(
                date=current,
                materialized=plan is not None,
                plan_version=plan.version if plan is not None else None,
                scheduled_count=sum(item.start_at is not None for item in items),
                unscheduled_count=sum(item.start_at is None for item in items),
                completed_count=sum(item.status == "done" for item in items),
                items=items,
            )
        )

    commitments = list(
        db.scalars(
            select(WeeklyCommitment)
            .where(WeeklyCommitment.user_id == user.id, WeeklyCommitment.active.is_(True))
            .order_by(WeeklyCommitment.created_at, WeeklyCommitment.id)
        )
    )
    scheduled: dict[str, tuple[int, int, int, int]] = {}
    for plan in plans:
        for item in plan.items:
            if item.task is None or item.task.commitment_id is None:
                continue
            key = str(item.task.commitment_id)
            minutes = _item_minutes(item)
            total_minutes, total_sessions, done_minutes, done_sessions = scheduled.get(
                key, (0, 0, 0, 0)
            )
            if item.start_time is not None and item.end_time is not None:
                total_minutes += minutes
                total_sessions += 1
                if item.status == "done" or item.task.status == "done":
                    done_minutes += minutes
                    done_sessions += 1
            scheduled[key] = (total_minutes, total_sessions, done_minutes, done_sessions)
    loads = []
    for commitment in commitments:
        values = scheduled.get(str(commitment.id), (0, 0, 0, 0))
        loads.append(
            CalendarCommitmentLoad(
                commitment_id=str(commitment.id),
                title=commitment.title,
                target_minutes=commitment.target_minutes_week,
                target_sessions=commitment.target_sessions_week,
                scheduled_minutes=values[0],
                scheduled_sessions=values[1],
                completed_minutes=values[2],
                completed_sessions=values[3],
                remaining_minutes=max(0, commitment.target_minutes_week - values[0]),
            )
        )
    response = CalendarWeekResponse(
        start=start,
        end=end,
        timezone=user.timezone,
        days=days,
        commitment_load=loads,
        cursor="",
    )
    response.cursor = _cursor(response.model_dump(exclude={"cursor"}, mode="json"))
    return response


def get_calendar_month(db: Session, *, user: User, month: date) -> CalendarMonthResponse:
    zone = _user_zone(user)
    last_day = monthrange(month.year, month.month)[1]
    end_date = date(month.year, month.month, last_day)
    start_at, _ = _civil_day_bounds(month, zone)
    _, end_at = _civil_day_bounds(end_date, zone)

    milestones = list(
        db.execute(
            select(GoalMilestone, Goal)
            .join(Goal, Goal.id == GoalMilestone.goal_id)
            .where(
                GoalMilestone.user_id == user.id,
                GoalMilestone.completed_at.is_not(None),
                GoalMilestone.completed_at >= start_at,
                GoalMilestone.completed_at < end_at,
            )
            .order_by(GoalMilestone.completed_at, GoalMilestone.id)
        )
    )
    goals = list(
        db.scalars(
            select(Goal).where(
                Goal.user_id == user.id,
                Goal.deadline >= month,
                Goal.deadline <= end_date,
            ).order_by(Goal.deadline, Goal.id)
        )
    )
    modes = list(
        db.scalars(
            select(TemporaryLifeMode).where(
                TemporaryLifeMode.user_id == user.id,
                TemporaryLifeMode.status == "active",
                TemporaryLifeMode.ends_at > start_at,
                TemporaryLifeMode.starts_at < end_at,
            ).order_by(TemporaryLifeMode.starts_at, TemporaryLifeMode.id)
        )
    )
    measurements = list(
        db.execute(
            select(MetricObservation, Goal)
            .join(Goal, Goal.id == MetricObservation.goal_id)
            .where(
                MetricObservation.user_id == user.id,
                MetricObservation.occurred_at >= start_at,
                MetricObservation.occurred_at < end_at,
            )
            .order_by(MetricObservation.occurred_at, MetricObservation.id)
        )
    )
    plans = list(
        db.scalars(
            select(DayPlan)
            .options(selectinload(DayPlan.items))
            .where(
                DayPlan.user_id == user.id,
                DayPlan.date >= month,
                DayPlan.date <= end_date,
            )
        ).unique()
    )
    busy = _busy_intervals(db, user_id=user.id, start_at=start_at, end_at=end_at)
    response = CalendarMonthResponse(
        month=month,
        timezone=user.timezone,
        milestones=[
            CalendarMonthMilestone(
                milestone_id=str(milestone.id),
                goal_id=str(goal.public_id),
                title=milestone.title,
                occurred_at=_as_utc(milestone.completed_at),
                status=milestone.status,
            )
            for milestone, goal in milestones
        ],
        deadlines=[
            CalendarMonthDeadline(goal_id=str(goal.public_id), title=goal.title, date=goal.deadline)
            for goal in goals
        ],
        life_modes=[
            CalendarMonthLifeMode(
                mode_id=str(mode.id),
                mode=mode.mode,
                starts_at=_as_utc(mode.starts_at),
                ends_at=_as_utc(mode.ends_at),
            )
            for mode in modes
        ],
        measurements=[
            CalendarMonthMeasurement(
                goal_id=str(goal.public_id),
                occurred_at=_as_utc(observation.occurred_at),
                value=Decimal(observation.value),
                unit=observation.unit,
            )
            for observation, goal in measurements
        ],
        tension=CalendarMonthTension(
            materialized_days=len(plans),
            scheduled_minutes=sum(
                _item_minutes(item)
                for plan in plans
                for item in plan.items
                if item.start_time is not None and item.end_time is not None
            ),
            unscheduled_items=sum(
                item.start_time is None for plan in plans for item in plan.items
            ),
            busy_minutes=sum(_interval_minutes(interval) for interval in busy),
        ),
        cursor="",
    )
    response.cursor = _cursor(response.model_dump(exclude={"cursor"}, mode="json"))
    return response


def _user_zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("invalid stored user timezone") from error


def _civil_day_bounds(value: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(value + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def _planning_day_bounds(
    user: User, value: date, zone: ZoneInfo
) -> tuple[datetime, datetime]:
    local_start = datetime.combine(value, DEFAULT_DAY_START, tzinfo=zone)
    local_end = datetime.combine(value, user.sleep_time or DEFAULT_DAY_END, tzinfo=zone)
    if local_end <= local_start:
        local_end += timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def _day_items(plan: DayPlan, zone: ZoneInfo) -> list[CalendarDayItem]:
    items = []
    for item in sorted(
        plan.items,
        key=lambda value: (
            value.start_time is None,
            value.start_time or time.max,
            value.id,
        ),
    ):
        start_at = None
        end_at = None
        if item.start_time is not None and item.end_time is not None:
            local_start = datetime.combine(plan.date, item.start_time, tzinfo=zone)
            end_date = plan.date if item.end_time > item.start_time else plan.date + timedelta(days=1)
            local_end = datetime.combine(end_date, item.end_time, tzinfo=zone)
            start_at = local_start.astimezone(UTC)
            end_at = local_end.astimezone(UTC)
        items.append(
            CalendarDayItem(
                item_id=item.id,
                task_id=item.task_id,
                title=item.title,
                kind=item.item_type,
                status=item.status,
                start_at=start_at,
                end_at=end_at,
                unscheduled_reason=item.unscheduled_reason,
            )
        )
    return items


def _busy_intervals(
    db: Session, *, user_id: int, start_at: datetime, end_at: datetime
) -> list[CalendarInterval]:
    blocks = list(
        db.scalars(
            select(CalendarBusyBlock)
            .where(
                CalendarBusyBlock.user_id == user_id,
                CalendarBusyBlock.deleted_at.is_(None),
                CalendarBusyBlock.occurrence_end > start_at,
                CalendarBusyBlock.occurrence_start < end_at,
            )
            .order_by(CalendarBusyBlock.occurrence_start, CalendarBusyBlock.id)
        )
    )
    return _merge_intervals(
        [
            CalendarInterval(
                start_at=max(start_at, _as_utc(block.occurrence_start)),
                end_at=min(end_at, _as_utc(block.occurrence_end)),
            )
            for block in blocks
        ]
    )


def _free_intervals(
    start_at: datetime, end_at: datetime, occupied: list[CalendarInterval]
) -> list[CalendarInterval]:
    cursor = start_at
    free: list[CalendarInterval] = []
    for interval in _merge_intervals(occupied):
        clipped_start = max(start_at, interval.start_at)
        clipped_end = min(end_at, interval.end_at)
        if clipped_end <= cursor:
            continue
        if clipped_start > cursor:
            free.append(CalendarInterval(start_at=cursor, end_at=clipped_start))
        cursor = max(cursor, clipped_end)
    if cursor < end_at:
        free.append(CalendarInterval(start_at=cursor, end_at=end_at))
    return free


def _merge_intervals(intervals: list[CalendarInterval]) -> list[CalendarInterval]:
    merged: list[CalendarInterval] = []
    for interval in sorted(intervals, key=lambda value: (value.start_at, value.end_at)):
        if interval.end_at <= interval.start_at:
            continue
        if not merged or interval.start_at > merged[-1].end_at:
            merged.append(interval)
            continue
        merged[-1] = CalendarInterval(
            start_at=merged[-1].start_at,
            end_at=max(merged[-1].end_at, interval.end_at),
        )
    return merged


def _item_minutes(item: PlanItem) -> int:
    if item.start_time is None or item.end_time is None:
        return 0
    start = item.start_time.hour * 60 + item.start_time.minute
    end = item.end_time.hour * 60 + item.end_time.minute
    return end - start if end > start else 24 * 60 - start + end


def _interval_minutes(interval: CalendarInterval) -> int:
    return max(0, int((interval.end_at - interval.start_at).total_seconds() // 60))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cursor(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
