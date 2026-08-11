from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from app.models.goal import Goal
from app.models.onboarding import ResourceBudget
from app.models.day_plan import DayPlan
from app.models.plan_item import PlanItem
from app.models.program import Program, ProgramPhase, WeeklyCommitment
from app.models.routine import Routine
from app.models.task import Task
from app.models.user import User
from app.services.task_duration_service import estimate_task_minutes
from app.services.time_service import get_user_now


SUPPORTED_CADENCES = {"daily", "weekdays", "selected_weekdays"}


@dataclass
class RoutineCreationResult:
    routine: Routine
    created: bool
    occurrences: list[Task] = field(default_factory=list)


@dataclass(frozen=True)
class WeeklyCommitmentShortfall:
    commitment_id: UUID
    missing_minutes: int
    missing_sessions: int
    reason: str


@dataclass
class WeeklyCommitmentMaterializationResult:
    week_start: date
    created_tasks: list[Task] = field(default_factory=list)
    shortfalls: list[WeeklyCommitmentShortfall] = field(default_factory=list)
    skipped_reason: str | None = None


@dataclass(frozen=True)
class _CommitmentLoad:
    desired_minutes: int
    desired_sessions: int


def _routine_is_due(routine: Routine, occurrence_date: date) -> bool:
    if not routine.active or occurrence_date < routine.start_date:
        return False

    if routine.end_date and occurrence_date > routine.end_date:
        return False

    if routine.cadence == "daily":
        return True

    if routine.cadence == "weekdays":
        return occurrence_date.weekday() < 5

    if routine.cadence == "selected_weekdays":
        return occurrence_date.weekday() in set(routine.weekdays or [])

    return False


def create_routine(
    db: Session,
    user: User,
    *,
    title: str,
    cadence: str,
    start_date: date,
    weekdays: list[int] | None = None,
    fixed_time: time | None = None,
    preferred_window: str | None = None,
    estimated_minutes: int | None = 10,
    end_date: date | None = None,
    commit: bool = True,
) -> RoutineCreationResult:
    if cadence not in SUPPORTED_CADENCES:
        raise ValueError(f"unsupported routine cadence: {cadence}")

    normalized_weekdays = sorted(set(weekdays or []))

    if cadence == "selected_weekdays" and not normalized_weekdays:
        raise ValueError("selected_weekdays routine requires weekdays")

    routine = (
        db.query(Routine)
        .filter(
            Routine.user_id == user.id,
            Routine.title.ilike(title.strip()),
            Routine.cadence == cadence,
            Routine.active.is_(True),
        )
        .one_or_none()
    )
    created = routine is None

    if routine is None:
        routine = Routine(
            user_id=user.id,
            title=title.strip()[:255],
            cadence=cadence,
            weekdays=normalized_weekdays,
            fixed_time=fixed_time,
            preferred_window=preferred_window,
            estimated_minutes=estimated_minutes,
            start_date=start_date,
            end_date=end_date,
            active=True,
        )
        db.add(routine)
        db.flush()

    occurrences = materialize_routine_occurrences(
        db,
        user,
        start_date,
        routines=[routine],
        commit=False,
    )

    if commit:
        db.commit()
        db.refresh(routine)

    return RoutineCreationResult(routine=routine, created=created, occurrences=occurrences)


def materialize_routine_occurrences(
    db: Session,
    user: User,
    occurrence_date: date,
    *,
    routines: list[Routine] | None = None,
    commit: bool = True,
) -> list[Task]:
    if routines is None:
        routines = (
            db.query(Routine)
            .filter(Routine.user_id == user.id, Routine.active.is_(True))
            .with_for_update()
            .all()
        )

    created: list[Task] = []

    for routine in routines:
        if routine.user_id != user.id or not _routine_is_due(routine, occurrence_date):
            continue

        existing = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.routine_id == routine.id,
                Task.occurrence_date == occurrence_date,
            )
            .one_or_none()
        )

        if existing:
            continue

        task = Task(
            user_id=user.id,
            routine_id=routine.id,
            title=routine.title,
            source_text=None,
            priority="medium",
            estimated_minutes=routine.estimated_minutes,
            target_date=occurrence_date,
            occurrence_date=occurrence_date,
            scheduling_type="fixed" if routine.fixed_time else "flexible",
            fixed_start=routine.fixed_time,
            preferred_window=routine.preferred_window,
            is_locked=bool(routine.fixed_time),
            status="planned",
        )
        db.add(task)
        created.append(task)

    db.flush()

    if commit:
        db.commit()

        for task in created:
            db.refresh(task)

    return created


def _commitment_load(commitment: WeeklyCommitment) -> _CommitmentLoad:
    target_minutes = commitment.target_minutes_week
    minimum = commitment.minimum_block_minutes

    if commitment.target_sessions_week > 0:
        session_count = commitment.target_sessions_week
        target_minutes = max(target_minutes, session_count * minimum)
    elif commitment.splittable and target_minutes > 0:
        session_count = max(1, target_minutes // minimum)
    elif target_minutes > 0:
        session_count = 1
    else:
        session_count = 0

    return _CommitmentLoad(
        desired_minutes=target_minutes,
        desired_sessions=session_count,
    )


def _phase_applies_to_week(phase: ProgramPhase | None, week_start: date) -> bool:
    if phase is None:
        return True
    week_end = week_start + timedelta(days=6)
    if phase.status in {"paused", "completed", "archived"}:
        return False
    if phase.start_date and phase.start_date > week_end:
        return False
    if phase.end_date and phase.end_date < week_start:
        return False
    return True


def _commitment_dates(
    commitment: WeeklyCommitment,
    budget: ResourceBudget,
    week_start: date,
    not_before: date,
) -> list[date]:
    allowed = sorted(
        set(commitment.allowed_weekdays or []) & set(budget.available_days or [])
    )
    candidates = [week_start + timedelta(days=weekday - 1) for weekday in allowed]
    return [
        candidate
        for candidate in candidates
        if candidate >= not_before
        and (
            commitment.phase is None
            or commitment.phase.start_date is None
            or candidate >= commitment.phase.start_date
        )
        and (
            commitment.phase is None
            or commitment.phase.end_date is None
            or candidate <= commitment.phase.end_date
        )
    ]


def _invalidate_future_plan_items(
    db: Session,
    *,
    user: User,
    task_ids: set[int],
    current_date: date,
) -> None:
    if not task_ids:
        return
    items = list(
        db.scalars(
            select(PlanItem)
            .join(DayPlan, DayPlan.id == PlanItem.day_plan_id)
            .where(
                DayPlan.user_id == user.id,
                DayPlan.date >= current_date,
                PlanItem.task_id.in_(task_ids),
            )
        ).all()
    )
    updated_plan_ids: set[int] = set()
    for item in items:
        if item.day_plan_id not in updated_plan_ids:
            item.day_plan.version += 1
            updated_plan_ids.add(item.day_plan_id)
        db.delete(item)


def materialize_weekly_commitments(
    db: Session,
    user: User,
    week_start: date,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> WeeklyCommitmentMaterializationResult:
    """Create deterministic task candidates for the nearest two detailed weeks."""
    if week_start.isoweekday() != 1:
        raise ValueError("week_start must be a Monday")

    current_date = get_user_now(user, now).date()
    current_week_start = current_date - timedelta(days=current_date.isoweekday() - 1)
    result = WeeklyCommitmentMaterializationResult(week_start=week_start)

    if week_start not in {
        current_week_start,
        current_week_start + timedelta(days=7),
    }:
        result.skipped_reason = "outside_detailed_horizon"
        return result

    if db.scalar(select(User.id).where(User.id == user.id).with_for_update()) is None:
        return result

    budget = db.scalar(
        select(ResourceBudget)
        .where(ResourceBudget.user_id == user.id)
        .with_for_update()
    )

    commitments = list(
        db.scalars(
            select(WeeklyCommitment)
            .options(
                selectinload(WeeklyCommitment.phase),
                selectinload(WeeklyCommitment.program).selectinload(Program.goal),
            )
            .join(Program, Program.id == WeeklyCommitment.program_id)
            .join(Goal, Goal.id == WeeklyCommitment.goal_id)
            .where(
                WeeklyCommitment.user_id == user.id,
                WeeklyCommitment.active.is_(True),
                Program.user_id == user.id,
                Program.status == "active",
                Goal.user_id == user.id,
                Goal.status == "active",
            )
            .order_by(
                case(
                    (Goal.priority == "high", 0),
                    (Goal.priority == "medium", 1),
                    (Goal.priority == "low", 2),
                    else_=1,
                ),
                Goal.id,
                Program.created_at,
                Program.id,
                WeeklyCommitment.created_at,
                WeeklyCommitment.id,
            )
            .with_for_update()
        ).all()
    )
    commitments = [
        commitment
        for commitment in commitments
        if _phase_applies_to_week(commitment.phase, week_start)
    ]
    week_end = week_start + timedelta(days=7)
    week_tasks = list(
        db.scalars(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.target_date >= week_start,
                Task.target_date < week_end,
                Task.status.in_(["planned", "done"]),
            )
            .order_by(Task.target_date, Task.id)
        ).all()
    )
    active_by_id = {commitment.id: commitment for commitment in commitments}
    invalidated_task_ids: set[int] = set()

    for task in week_tasks:
        if (
            task.commitment_id is None
            or task.status != "planned"
            or task.target_date < current_date
            or task.scheduling_type == "fixed"
            or task.is_locked
        ):
            continue
        commitment = active_by_id.get(task.commitment_id)
        valid = commitment is not None
        if valid and budget is not None:
            valid_dates = set(
                _commitment_dates(
                    commitment,
                    budget,
                    week_start,
                    week_start,
                )
            )
            valid = task.target_date in valid_dates
        if not valid:
            task.status = "cancelled"
            invalidated_task_ids.add(task.id)

    existing_tasks = [
        task
        for task in week_tasks
        if task.commitment_id is not None and task.status in {"planned", "done"}
    ]
    existing_by_commitment: dict[UUID, list[Task]] = {}
    for task in existing_tasks:
        if task.commitment_id is not None:
            existing_by_commitment.setdefault(task.commitment_id, []).append(task)

    immutable_commitment_tasks = [
        task
        for task in existing_tasks
        if task.status == "done"
        or task.target_date < current_date
        or task.scheduling_type == "fixed"
        or task.is_locked
    ]
    one_off_minutes = sum(
        estimate_task_minutes(task)
        for task in week_tasks
        if task.commitment_id is None
        and task.routine_id is None
        and task.status in {"planned", "done"}
    )
    allocated_minutes = one_off_minutes + sum(
        estimate_task_minutes(task) for task in immutable_commitment_tasks
    )
    remaining_capacity = max(
        0, (budget.allocatable_minutes if budget is not None else 0) - allocated_minutes
    )

    for commitment in commitments:
        load = _commitment_load(commitment)
        desired_sessions = load.desired_sessions
        desired_minutes = load.desired_minutes
        commitment_tasks = existing_by_commitment.get(commitment.id, [])
        immutable = [
            task
            for task in commitment_tasks
            if task.status == "done"
            or task.target_date < current_date
            or task.scheduling_type == "fixed"
            or task.is_locked
        ]
        future_candidates = [
            task
            for task in commitment_tasks
            if task.status == "planned"
            and task.target_date >= current_date
            and task.scheduling_type != "fixed"
            and not task.is_locked
        ]
        priority = commitment.program.goal.priority
        if priority not in {"high", "medium", "low"}:
            priority = "medium"

        if budget is None:
            existing = immutable + future_candidates
            for task in future_candidates:
                task.priority = priority
            existing_sessions = len(existing)
            existing_minutes = sum(estimate_task_minutes(task) for task in existing)
            missing_minutes = max(0, desired_minutes - existing_minutes)
            missing_sessions = max(0, desired_sessions - existing_sessions)
            if missing_minutes or missing_sessions:
                result.shortfalls.append(
                    WeeklyCommitmentShortfall(
                        commitment_id=commitment.id,
                        missing_minutes=missing_minutes,
                        missing_sessions=missing_sessions,
                        reason="resource_budget_missing",
                    )
                )
            continue

        existing = list(immutable)
        existing_sessions = len(existing)
        existing_minutes = sum(estimate_task_minutes(task) for task in existing)
        missing_sessions = max(0, desired_sessions - existing_sessions)
        missing_minutes = max(0, desired_minutes - existing_minutes)
        blocked_reason: str | None = None

        for task in future_candidates:
            duration = estimate_task_minutes(task)
            reusable_duration = min(duration, missing_minutes, remaining_capacity)
            if (
                missing_sessions <= 0
                or reusable_duration < commitment.minimum_block_minutes
                or (reusable_duration < duration and not commitment.splittable)
            ):
                task.status = "cancelled"
                invalidated_task_ids.add(task.id)
                if missing_sessions > 0 and missing_minutes > 0:
                    blocked_reason = "resource_capacity"
                continue
            if reusable_duration != duration:
                task.estimated_minutes = reusable_duration
                invalidated_task_ids.add(task.id)
            task.priority = priority
            existing.append(task)
            existing_sessions += 1
            existing_minutes += reusable_duration
            missing_sessions = max(0, desired_sessions - existing_sessions)
            missing_minutes = max(0, desired_minutes - existing_minutes)
            remaining_capacity -= reusable_duration

        if missing_sessions == 0 and missing_minutes == 0:
            continue

        if missing_sessions > 0:
            feasible_sessions = min(
                missing_sessions,
                missing_minutes // commitment.minimum_block_minutes,
            )
            if feasible_sessions > 0:
                base, remainder = divmod(missing_minutes, feasible_sessions)
                pending_durations = [
                    base + (1 if index < remainder else 0)
                    for index in range(feasible_sessions)
                ]
            else:
                pending_durations = []
        elif commitment.splittable and missing_minutes >= commitment.minimum_block_minutes:
            extra_sessions = max(
                1, missing_minutes // commitment.minimum_block_minutes
            )
            base, remainder = divmod(missing_minutes, extra_sessions)
            pending_durations = [
                base + (1 if index < remainder else 0)
                for index in range(extra_sessions)
            ]
        else:
            pending_durations = []

        candidate_dates = _commitment_dates(
            commitment,
            budget,
            week_start,
            max(week_start, current_date),
        )
        scheduled_dates = [task.target_date for task in existing]

        for duration in pending_durations:
            selected_date = min(
                candidate_dates,
                key=lambda candidate: (scheduled_dates.count(candidate), candidate),
                default=None,
            )
            if selected_date is None:
                blocked_reason = "weekday_availability"
                break
            planned_duration = duration
            if duration > remaining_capacity:
                if (
                    commitment.splittable
                    and remaining_capacity >= commitment.minimum_block_minutes
                ):
                    planned_duration = remaining_capacity
                else:
                    blocked_reason = "resource_capacity"
                    break

            task = Task(
                user_id=user.id,
                goal_id=commitment.goal_id,
                program_id=commitment.program_id,
                commitment_id=commitment.id,
                title=commitment.title,
                source_text=None,
                priority=priority,
                estimated_minutes=planned_duration,
                target_date=selected_date,
                scheduling_type="flexible",
                preferred_window=commitment.preferred_window,
                status="planned",
            )
            db.add(task)
            result.created_tasks.append(task)
            existing.append(task)
            scheduled_dates.append(selected_date)
            existing_sessions += 1
            existing_minutes += planned_duration
            remaining_capacity -= planned_duration
            if planned_duration < duration:
                blocked_reason = "resource_capacity"
                break

        remaining_sessions = max(0, desired_sessions - existing_sessions)
        remaining_minutes = max(0, desired_minutes - existing_minutes)
        if remaining_sessions or remaining_minutes:
            result.shortfalls.append(
                WeeklyCommitmentShortfall(
                    commitment_id=commitment.id,
                    missing_minutes=remaining_minutes,
                    missing_sessions=remaining_sessions,
                    reason=blocked_reason
                    or (
                        "minimum_block"
                        if not commitment.splittable
                        else "resource_capacity"
                    ),
                )
            )

    _invalidate_future_plan_items(
        db,
        user=user,
        task_ids=invalidated_task_ids,
        current_date=current_date,
    )
    db.flush()
    if commit:
        db.commit()
        for task in result.created_tasks:
            db.refresh(task)
    return result


def list_active_routines(db: Session, user: User) -> list[Routine]:
    return (
        db.query(Routine)
        .filter(Routine.user_id == user.id, Routine.active.is_(True))
        .order_by(Routine.id.asc())
        .all()
    )
