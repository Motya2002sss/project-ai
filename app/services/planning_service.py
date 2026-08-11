from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.schemas import ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User
from app.services.time_service import (
    ceil_datetime,
    combine_user_datetime,
    get_user_now,
    resolve_target_date,
)
from app.services.routine_service import (
    WeeklyCommitmentShortfall,
    materialize_routine_occurrences,
    materialize_weekly_commitments,
)
from app.services.task_duration_service import estimate_task_minutes


PRIORITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}

FOCUS_TEXT_MAX_LENGTH = 180
SCHEDULING_STEP_MINUTES = 15
DEFAULT_DAY_START = time(hour=6)
DEFAULT_DAY_END = time(hour=23)
PREFERRED_WINDOWS = {
    "morning": (time(hour=6), time(hour=12)),
    "afternoon": (time(hour=12), time(hour=17)),
    "evening": (time(hour=17), time(hour=23)),
    "anytime": (DEFAULT_DAY_START, DEFAULT_DAY_END),
}


@dataclass(frozen=True)
class TimeInterval:
    start: datetime
    end: datetime
    label: str | None = None

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("planning intervals must be timezone-aware")

        if self.end <= self.start:
            raise ValueError("interval end must be after start")


@dataclass(frozen=True)
class PlanningConflict:
    task_id: int
    title: str
    message: str


@dataclass
class PlanBuildResult:
    day_plan: DayPlan
    conflicts: list[PlanningConflict] = field(default_factory=list)
    unscheduled_task_ids: list[int] = field(default_factory=list)
    commitment_shortfalls: list[WeeklyCommitmentShortfall] = field(default_factory=list)


def intervals_overlap(left: TimeInterval, right: TimeInterval) -> bool:
    return left.start < right.end and right.start < left.end


def _merge_intervals(intervals: list[TimeInterval]) -> list[TimeInterval]:
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
    merged: list[TimeInterval] = [ordered[0]]

    for interval in ordered[1:]:
        previous = merged[-1]

        if interval.start <= previous.end:
            merged[-1] = TimeInterval(
                previous.start,
                max(previous.end, interval.end),
                previous.label or interval.label,
            )
        else:
            merged.append(interval)

    return merged


def find_available_slots(
    day_start: datetime,
    day_end: datetime,
    occupied: list[TimeInterval],
    duration_minutes: int,
    *,
    preferred_window: TimeInterval | None = None,
    earliest_start: datetime | None = None,
    latest_end: datetime | None = None,
) -> list[TimeInterval]:
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")

    effective_start = max(day_start, earliest_start) if earliest_start else day_start
    effective_end = min(day_end, latest_end) if latest_end else day_end

    if preferred_window:
        effective_start = max(effective_start, preferred_window.start)
        effective_end = min(effective_end, preferred_window.end)

    if effective_end <= effective_start:
        return []

    window = TimeInterval(effective_start, effective_end)
    clipped_occupied: list[TimeInterval] = []

    for interval in occupied:
        start = max(interval.start, window.start)
        end = min(interval.end, window.end)

        if end > start:
            clipped_occupied.append(TimeInterval(start, end, interval.label))

    free_intervals: list[TimeInterval] = []
    cursor = window.start

    for interval in _merge_intervals(clipped_occupied):
        if interval.start > cursor:
            candidate = TimeInterval(cursor, interval.start)

            if candidate.end - candidate.start >= timedelta(minutes=duration_minutes):
                free_intervals.append(candidate)

        cursor = max(cursor, interval.end)

    if cursor < window.end:
        candidate = TimeInterval(cursor, window.end)

        if candidate.end - candidate.start >= timedelta(minutes=duration_minutes):
            free_intervals.append(candidate)

    return free_intervals


def choose_best_slot(
    available_slots: list[TimeInterval],
    duration_minutes: int,
    *,
    existing_start: datetime | None = None,
) -> TimeInterval | None:
    if not available_slots:
        return None

    duration = timedelta(minutes=duration_minutes)
    candidates: list[TimeInterval] = []

    for slot in available_slots:
        candidate_start = slot.start

        if existing_start and slot.start <= existing_start and existing_start + duration <= slot.end:
            candidate_start = existing_start

        candidates.append(TimeInterval(candidate_start, candidate_start + duration))

    if existing_start:
        return min(
            candidates,
            key=lambda interval: (abs((interval.start - existing_start).total_seconds()), interval.start),
        )

    return min(candidates, key=lambda interval: interval.start)


def _truncate_focus_text(value: str) -> str:
    if len(value) <= FOCUS_TEXT_MAX_LENGTH:
        return value

    shortened = value[: FOCUS_TEXT_MAX_LENGTH - 1].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
    return f"{shortened}…"


def effective_work_window(day_plan: DayPlan, user: User | None = None) -> tuple[time | None, time | None]:
    profile = user or getattr(day_plan, "user", None)

    if day_plan.work_override_mode == "off":
        return None, None

    if day_plan.work_override_mode == "busy":
        return (
            day_plan.work_start_time or (profile.work_start_time if profile else None),
            day_plan.work_end_time or (profile.work_end_time if profile else None),
        )

    return (
        profile.work_start_time if profile else None,
        profile.work_end_time if profile else None,
    )


def build_plan_focus(day_plan: DayPlan, user: User | None = None) -> str:
    """Build safe Today copy from persisted plan items, never from raw parser text."""
    items = list(day_plan.items)
    scheduled = [item for item in items if item.status == "planned"]
    unscheduled = [item for item in items if item.status == "not_scheduled"]

    if not items:
        _, work_end = effective_work_window(day_plan, user)

        if work_end:
            return f"Рабочий день до {work_end.strftime('%H:%M')}. Вечер пока свободен."

        return "План пока пуст. Можно оставить день свободным."

    if unscheduled:
        if scheduled:
            text = f"Сначала — {scheduled[0].title}. На сегодня поместится не всё: оставил главное."
        else:
            text = "На сегодня поместится не всё. Задачи без времени не потеряны."

        return _truncate_focus_text(text)

    if not scheduled:
        return "Активных задач без времени нет. Выполненное осталось в истории дня."

    if len(scheduled) == 1:
        return _truncate_focus_text(f"Сначала — {scheduled[0].title}. На сегодня этого достаточно.")

    return _truncate_focus_text(
        f"Сначала — {scheduled[0].title}, затем — {scheduled[1].title}."
    )


def get_plan_date(
    parsed_message: ParsedUserMessage | None = None,
    user: User | None = None,
    now: datetime | None = None,
) -> date:
    date_value = parsed_message.date if parsed_message else None
    return resolve_target_date(date_value, user=user, now=now)


def format_plan_date(plan_date: date, user: User | None = None) -> str:
    today = resolve_target_date(None, user=user)

    if plan_date == today:
        return "сегодня"

    if plan_date == today + timedelta(days=1):
        return "завтра"

    return plan_date.strftime("%d.%m.%Y")


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None

    try:
        hour_raw, minute_raw = value.split(":")
        return time(hour=int(hour_raw), minute=int(minute_raw))
    except ValueError:
        return None


def _day_bounds(user: User, plan_date: date) -> TimeInterval:
    start = combine_user_datetime(plan_date, DEFAULT_DAY_START, user)
    end_time = user.sleep_time or DEFAULT_DAY_END
    end = combine_user_datetime(plan_date, end_time, user)

    if end <= start:
        end += timedelta(days=1)

    return TimeInterval(start, end, "day")


def _work_interval(
    user: User,
    plan_date: date,
    bounds: TimeInterval,
    day_plan: DayPlan,
) -> TimeInterval | None:
    work_start, work_end = effective_work_window(day_plan, user)

    if not work_end:
        return None

    start = combine_user_datetime(plan_date, work_start or bounds.start.time(), user)
    end = combine_user_datetime(plan_date, work_end, user)

    if end <= start:
        end += timedelta(days=1)

    end += timedelta(minutes=settings.plan_start_buffer_minutes)
    clipped_start = max(start, bounds.start)
    clipped_end = min(end, bounds.end)

    if clipped_end <= clipped_start:
        return None

    return TimeInterval(clipped_start, clipped_end, "рабочее время")


def _task_datetime(plan_date: date, value: time | None, user: User) -> datetime | None:
    return combine_user_datetime(plan_date, value, user) if value else None


def _task_preferred_interval(task: Task, plan_date: date, user: User) -> TimeInterval | None:
    if not task.preferred_window:
        return None

    window = PREFERRED_WINDOWS.get(task.preferred_window)

    if not window:
        return None

    start = combine_user_datetime(plan_date, window[0], user)
    end = combine_user_datetime(plan_date, window[1], user)

    if end <= start:
        end += timedelta(days=1)

    return TimeInterval(start, end, task.preferred_window)


def _fixed_task_interval(task: Task, plan_date: date, user: User) -> TimeInterval | None:
    start = _task_datetime(plan_date, task.fixed_start, user)

    if start is None:
        return None

    end = _task_datetime(plan_date, task.fixed_end, user)

    if end is None:
        end = start + timedelta(minutes=estimate_task_minutes(task))
    elif end <= start:
        end += timedelta(days=1)

    return TimeInterval(start, end, task.title)


def _item_interval(item: PlanItem, plan_date: date, user: User) -> TimeInterval | None:
    if not item.start_time or not item.end_time:
        return None

    start = combine_user_datetime(plan_date, item.start_time, user)
    end = combine_user_datetime(plan_date, item.end_time, user)

    if end <= start:
        end += timedelta(days=1)

    return TimeInterval(start, end, item.title)


def _interval_fits_task(
    interval: TimeInterval,
    task: Task,
    bounds: TimeInterval,
    available_start: datetime,
    user: User,
) -> bool:
    if interval.start < available_start or interval.end > bounds.end:
        return False

    if interval.end - interval.start != timedelta(minutes=estimate_task_minutes(task)):
        return False

    earliest = _task_datetime(task.target_date, task.earliest_start, user)
    latest = _task_datetime(task.target_date, task.latest_end, user)
    preferred = _task_preferred_interval(task, task.target_date, user)

    if earliest and interval.start < earliest:
        return False

    if latest and interval.end > latest:
        return False

    if preferred and (interval.start < preferred.start or interval.end > preferred.end):
        return False

    return interval.start >= bounds.start


def _first_conflicting_interval(
    candidate: TimeInterval,
    occupied: list[TimeInterval],
) -> TimeInterval | None:
    return next((interval for interval in occupied if intervals_overlap(candidate, interval)), None)


def _commitment_recovery_constraints(
    task: Task,
    commitment_intervals: dict[UUID, list[TimeInterval]],
) -> list[TimeInterval]:
    if task.commitment_id is None or task.commitment is None:
        return []
    gap_minutes = task.commitment.recovery_gap_minutes
    if gap_minutes <= 0:
        return []
    gap = timedelta(minutes=gap_minutes)
    return [
        TimeInterval(
            interval.start - gap,
            interval.end + gap,
            "восстановление между сессиями",
        )
        for interval in commitment_intervals.get(task.commitment_id, [])
    ]


def _deadline_sort_value(task: Task, current_time: datetime) -> float:
    if task.deadline is None:
        return float("inf")

    deadline = task.deadline

    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=current_time.tzinfo)

    return deadline.timestamp()


def get_or_create_day_plan(
    db: Session,
    user: User,
    plan_date: date,
    *,
    commit: bool = True,
) -> DayPlan:
    day_plan = (
        db.query(DayPlan)
        .filter(
            DayPlan.user_id == user.id,
            DayPlan.date == plan_date,
        )
        .one_or_none()
    )

    if day_plan:
        return day_plan

    day_plan = DayPlan(
        user_id=user.id,
        date=plan_date,
        summary="Автоматический план дня",
        status="draft",
    )

    db.add(day_plan)
    db.flush()

    if commit:
        db.commit()
        db.refresh(day_plan)

    return day_plan


def build_day_plan_result(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage | None = None,
    *,
    plan_date: date | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> PlanBuildResult:
    resolved_date = plan_date or get_plan_date(parsed_message, user=user, now=now)
    current_time = get_user_now(user, now)
    bounds = _day_bounds(user, resolved_date)
    available_start = bounds.start

    if resolved_date == current_time.date():
        available_start = max(bounds.start, ceil_datetime(current_time, SCHEDULING_STEP_MINUTES))

    day_plan = get_or_create_day_plan(db, user, resolved_date, commit=False)

    previous_plan_context = (
        day_plan.energy_level,
        day_plan.budget_limit,
        day_plan.work_override_mode,
        day_plan.work_start_time,
        day_plan.work_end_time,
        day_plan.status,
    )

    if parsed_message:
        day_plan.energy_level = parsed_message.energy_level or day_plan.energy_level
        day_plan.budget_limit = parsed_message.budget_limit or day_plan.budget_limit
        day_plan.summary = parsed_message.raw_text or "Автоматический план дня"

        if parsed_message.intent == "set_day_availability":
            day_plan.work_override_mode = (
                "off" if parsed_message.work_context == "off" else "busy"
            )
            day_plan.work_start_time = _parse_hhmm(parsed_message.work_start)
            day_plan.work_end_time = _parse_hhmm(parsed_message.work_until)

    existing_items = list(day_plan.items)
    previous_items_signature = sorted(
        (
            item.task_id,
            item.start_time,
            item.end_time,
            item.title,
            item.item_type,
            item.status,
            item.unscheduled_reason,
        )
        for item in existing_items
    )
    existing_by_task = {
        item.task_id: item
        for item in existing_items
        if item.task_id is not None
    }
    day_plan.items.clear()
    db.flush()

    commitment_result = materialize_weekly_commitments(
        db,
        user,
        resolved_date - timedelta(days=resolved_date.isoweekday() - 1),
        now=current_time,
        commit=False,
    )
    materialize_routine_occurrences(
        db,
        user,
        resolved_date,
        commit=False,
    )
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.target_date == resolved_date,
            Task.status.in_(["planned", "done"]),
        )
        .order_by(Task.id.asc())
        .all()
    )
    occupied: list[TimeInterval] = []
    commitment_intervals: dict[UUID, list[TimeInterval]] = {}
    work_interval = _work_interval(user, resolved_date, bounds, day_plan)

    if work_interval:
        occupied.append(work_interval)

    conflicts: list[PlanningConflict] = []
    unscheduled_task_ids: list[int] = []
    scheduled_task_ids: set[int] = set()

    def append_item(
        task: Task,
        *,
        status: str,
        interval: TimeInterval | None = None,
        reason: str | None = None,
    ) -> None:
        day_plan.items.append(
            PlanItem(
                task_id=task.id,
                start_time=interval.start.timetz().replace(tzinfo=None) if interval else None,
                end_time=interval.end.timetz().replace(tzinfo=None) if interval else None,
                title=task.title,
                item_type="task",
                status=status,
                unscheduled_reason=reason,
            )
        )

    for task in [item for item in tasks if item.status == "done"]:
        existing_interval = _item_interval(existing_by_task.get(task.id), resolved_date, user) if existing_by_task.get(task.id) else None
        append_item(task, status="done", interval=existing_interval, reason=None if existing_interval else "completed_without_time")

        if existing_interval:
            occupied.append(existing_interval)
            if task.commitment_id is not None:
                commitment_intervals.setdefault(task.commitment_id, []).append(
                    existing_interval
                )

        scheduled_task_ids.add(task.id)

    fixed_tasks = [
        task
        for task in tasks
        if task.status == "planned" and (task.scheduling_type == "fixed" or task.is_locked)
    ]

    for task in sorted(fixed_tasks, key=lambda item: (item.fixed_start or time.max, item.id)):
        interval = _fixed_task_interval(task, resolved_date, user)

        if interval is None:
            append_item(task, status="not_scheduled", reason="missing_fixed_time")
            unscheduled_task_ids.append(task.id)
            scheduled_task_ids.add(task.id)
            continue

        conflict = _first_conflicting_interval(
            interval,
            occupied + _commitment_recovery_constraints(task, commitment_intervals),
        )
        reason = None

        if interval.start < bounds.start or interval.end > bounds.end:
            reason = "outside_day_bounds"
        elif resolved_date == current_time.date() and interval.start < current_time:
            reason = "fixed_time_passed"
        elif conflict:
            reason = "fixed_time_conflict"

        if reason:
            append_item(task, status="not_scheduled", reason=reason)
            unscheduled_task_ids.append(task.id)
            scheduled_task_ids.add(task.id)
            conflict_label = conflict.label if conflict else "границы доступного дня"
            conflicts.append(
                PlanningConflict(
                    task_id=task.id,
                    title=task.title,
                    message=(
                        f"В {interval.start.strftime('%H:%M')} уже занято: {conflict_label}. "
                        f"«{task.title}» пересекается с этим интервалом. Уточни, что перенести."
                    ),
                )
            )
            continue

        append_item(task, status="planned", interval=interval)
        occupied.append(interval)
        if task.commitment_id is not None:
            commitment_intervals.setdefault(task.commitment_id, []).append(interval)
        scheduled_task_ids.add(task.id)

    flexible_tasks = [
        task
        for task in tasks
        if task.status == "planned" and task.id not in scheduled_task_ids
    ]

    for task in flexible_tasks:
        if task.scheduling_type == "unscheduled":
            reason = "needs_clarification" if task.estimated_minutes else "missing_duration"
            append_item(task, status="not_scheduled", reason=reason)
            unscheduled_task_ids.append(task.id)
            scheduled_task_ids.add(task.id)
            continue

        existing = existing_by_task.get(task.id)
        existing_interval = _item_interval(existing, resolved_date, user) if existing else None

        if (
            existing_interval
            and _interval_fits_task(existing_interval, task, bounds, available_start, user)
            and not _first_conflicting_interval(
                existing_interval,
                occupied
                + _commitment_recovery_constraints(task, commitment_intervals),
            )
        ):
            append_item(task, status="planned", interval=existing_interval)
            occupied.append(existing_interval)
            if task.commitment_id is not None:
                commitment_intervals.setdefault(task.commitment_id, []).append(
                    existing_interval
                )
            scheduled_task_ids.add(task.id)

    remaining_tasks = sorted(
        [task for task in flexible_tasks if task.id not in scheduled_task_ids],
        key=lambda task: (
            PRIORITY_ORDER.get(task.priority, 1),
            _deadline_sort_value(task, current_time),
            task.id,
        ),
    )

    for task in remaining_tasks:
        duration = estimate_task_minutes(task)
        preferred = _task_preferred_interval(task, resolved_date, user)
        earliest = _task_datetime(resolved_date, task.earliest_start, user)
        latest = _task_datetime(resolved_date, task.latest_end, user)
        slots = find_available_slots(
            available_start,
            bounds.end,
            occupied + _commitment_recovery_constraints(task, commitment_intervals),
            duration,
            preferred_window=preferred,
            earliest_start=earliest,
            latest_end=latest,
        )
        chosen = choose_best_slot(slots, duration)

        if chosen is None:
            reason = "no_available_slot"

            if preferred and resolved_date == current_time.date() and preferred.end <= available_start:
                reason = "preferred_window_passed"

            append_item(task, status="not_scheduled", reason=reason)
            unscheduled_task_ids.append(task.id)
            continue

        append_item(task, status="planned", interval=chosen)
        occupied.append(chosen)
        if task.commitment_id is not None:
            commitment_intervals.setdefault(task.commitment_id, []).append(chosen)

    day_plan.status = "conflict" if conflicts else "overloaded" if unscheduled_task_ids else "draft"
    current_items_signature = sorted(
        (
            item.task_id,
            item.start_time,
            item.end_time,
            item.title,
            item.item_type,
            item.status,
            item.unscheduled_reason,
        )
        for item in day_plan.items
    )
    current_plan_context = (
        day_plan.energy_level,
        day_plan.budget_limit,
        day_plan.work_override_mode,
        day_plan.work_start_time,
        day_plan.work_end_time,
        day_plan.status,
    )

    if previous_items_signature != current_items_signature or previous_plan_context != current_plan_context:
        day_plan.version += 1

    db.flush()
    assert_plan_has_no_overlaps(day_plan, user)

    if commit:
        db.commit()
        db.refresh(day_plan)

    commitment_shortfalls = list(commitment_result.shortfalls)
    tasks_by_id = {task.id: task for task in tasks}
    for item in day_plan.items:
        task = tasks_by_id.get(item.task_id) if item.task_id is not None else None
        if (
            item.status == "not_scheduled"
            and task is not None
            and task.commitment_id is not None
        ):
            commitment_shortfalls.append(
                WeeklyCommitmentShortfall(
                    commitment_id=task.commitment_id,
                    missing_minutes=estimate_task_minutes(task),
                    missing_sessions=1,
                    reason=f"placement_{item.unscheduled_reason or 'unknown'}",
                )
            )

    return PlanBuildResult(
        day_plan=day_plan,
        conflicts=conflicts,
        unscheduled_task_ids=unscheduled_task_ids,
        commitment_shortfalls=commitment_shortfalls,
    )


def assert_plan_has_no_overlaps(day_plan: DayPlan, user: User) -> None:
    intervals = [
        interval
        for item in day_plan.items
        if item.status in {"planned", "done"}
        for interval in [_item_interval(item, day_plan.date, user)]
        if interval is not None
    ]
    ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))

    for previous, current in zip(ordered, ordered[1:]):
        if intervals_overlap(previous, current):
            raise ValueError(
                f"plan overlap invariant failed: {previous.label} and {current.label}"
            )


def rebuild_day_plan(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage | None = None,
    *,
    plan_date: date | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> DayPlan:
    return build_day_plan_result(
        db=db,
        user=user,
        parsed_message=parsed_message,
        plan_date=plan_date,
        now=now,
        commit=commit,
    ).day_plan


def rebuild_today_plan(db: Session, user: User) -> DayPlan:
    return rebuild_day_plan(db=db, user=user, parsed_message=None)


def format_day_plan(day_plan: DayPlan, user: User | None = None) -> str:
    items = list(day_plan.items)
    scheduled_items = sorted(
        [item for item in items if item.status in {"planned", "done"} and item.start_time],
        key=lambda item: item.start_time or time.min,
    )
    not_scheduled_items = [item for item in items if item.status == "not_scheduled"]
    lines: list[str] = [f"План на {format_plan_date(day_plan.date, user=user)}:"]

    if day_plan.budget_limit:
        lines.append(f"Бюджет: {day_plan.budget_limit} ₽")

    if day_plan.energy_level:
        energy_map = {"low": "низкая", "medium": "средняя", "high": "высокая"}
        lines.append(f"Энергия: {energy_map.get(day_plan.energy_level, day_plan.energy_level)}")

    lines.append("")

    if scheduled_items:
        for item in scheduled_items:
            start = item.start_time.strftime("%H:%M")
            end = item.end_time.strftime("%H:%M") if item.end_time else "??:??"
            done_suffix = " — выполнено" if item.status == "done" else ""
            lines.append(f"{start}–{end} — {item.title}{done_suffix}")
    else:
        lines.append("Запланированных задач пока нет.")

    if not_scheduled_items:
        lines.append("")
        lines.append("Без времени:")

        for item in not_scheduled_items:
            reason_map = {
                "preferred_window_passed": "предпочтённое время уже прошло",
                "no_available_slot": "нет подходящего свободного окна",
                "fixed_time_conflict": "конфликт фиксированного времени",
                "fixed_time_passed": "указанное время уже прошло",
                "missing_fixed_time": "нужно уточнить время",
                "needs_clarification": "нужно уточнение",
                "missing_duration": "не указана длительность",
            }
            reason = reason_map.get(item.unscheduled_reason or "", "не удалось безопасно поставить в план")
            lines.append(f"— {item.title}: {reason}")

    return "\n".join(lines)
