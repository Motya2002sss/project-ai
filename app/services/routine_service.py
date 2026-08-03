from dataclasses import dataclass, field
from datetime import date, time

from sqlalchemy.orm import Session

from app.models.routine import Routine
from app.models.task import Task
from app.models.user import User


SUPPORTED_CADENCES = {"daily", "weekdays", "selected_weekdays"}


@dataclass
class RoutineCreationResult:
    routine: Routine
    created: bool
    occurrences: list[Task] = field(default_factory=list)


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


def list_active_routines(db: Session, user: User) -> list[Routine]:
    return (
        db.query(Routine)
        .filter(Routine.user_id == user.id, Routine.active.is_(True))
        .order_by(Routine.id.asc())
        .all()
    )
