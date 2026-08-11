from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import Goal
from app.models.routine import Routine
from app.models.task import Task
from app.models.user import User
from app.schemas.auth import AccountExportProfile, AccountExportResponse


def export_account_data(db: Session, user: User) -> AccountExportResponse:
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)
    ).all()
    tasks = db.scalars(
        select(Task).where(Task.user_id == user.id).order_by(Task.id)
    ).all()
    routines = db.scalars(
        select(Routine).where(Routine.user_id == user.id).order_by(Routine.id)
    ).all()

    return AccountExportResponse(
        exported_at=datetime.now(timezone.utc),
        profile=AccountExportProfile(
            public_id=user.public_id,
            name=user.name,
            email=user.email,
            timezone=user.timezone,
            work_start_time=_iso_or_none(user.work_start_time),
            work_end_time=_iso_or_none(user.work_end_time),
            sleep_time=_iso_or_none(user.sleep_time),
            created_at=user.created_at,
        ),
        goals=[
            {
                "id": goal.id,
                "title": goal.title,
                "category": goal.category,
                "priority": goal.priority,
                "target_date": _iso_or_none(goal.target_date),
                "status": goal.status,
            }
            for goal in goals
        ],
        tasks=[
            {
                "id": task.id,
                "goal_id": task.goal_id,
                "title": task.title,
                "description": task.description,
                "target_date": task.target_date.isoformat(),
                "status": task.status,
                "scheduling_type": task.scheduling_type,
                "estimated_minutes": task.estimated_minutes,
            }
            for task in tasks
        ],
        routines=[
            {
                "id": routine.id,
                "title": routine.title,
                "cadence": routine.cadence,
                "weekdays": routine.weekdays,
                "fixed_time": _iso_or_none(routine.fixed_time),
                "preferred_window": routine.preferred_window,
                "estimated_minutes": routine.estimated_minutes,
                "start_date": routine.start_date.isoformat(),
                "end_date": _iso_or_none(routine.end_date),
                "active": routine.active,
            }
            for routine in routines
        ],
    )


def delete_account_data(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value is not None else None
