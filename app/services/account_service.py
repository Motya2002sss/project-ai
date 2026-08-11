from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import Goal
from app.models.onboarding import OnboardingPreview, ResourceBudget
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
    resource_budget = db.scalar(
        select(ResourceBudget).where(ResourceBudget.user_id == user.id)
    )
    onboarding_previews = db.scalars(
        select(OnboardingPreview)
        .where(OnboardingPreview.user_id == user.id)
        .order_by(OnboardingPreview.created_at, OnboardingPreview.id)
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
        resource_budget=(
            {
                "weekly_available_minutes": resource_budget.weekly_available_minutes,
                "available_days": resource_budget.available_days,
                "minimum_minutes": resource_budget.minimum_minutes,
                "comfortable_minutes": resource_budget.comfortable_minutes,
                "maximum_minutes": resource_budget.maximum_minutes,
                "free_evenings": resource_budget.free_evenings,
                "preferred_windows": resource_budget.preferred_windows,
                "money_budget": resource_budget.money_budget,
                "conflict_priority": resource_budget.conflict_priority,
                "reserve_percent": resource_budget.reserve_percent,
                "allocatable_minutes": resource_budget.allocatable_minutes,
                "allocation": resource_budget.allocation,
                "version": resource_budget.version,
            }
            if resource_budget is not None
            else None
        ),
        onboarding_previews=[
            {
                "id": str(preview.id),
                "status": preview.status,
                "version": preview.version,
                "narrative": preview.narrative,
                "structured_summary": preview.structured_summary,
                "goal_candidates": preview.goal_candidates,
                "resource_budget": preview.resource_budget,
                "allocation": preview.allocation,
                "clarification": preview.clarification,
                "created_at": preview.created_at,
                "applied_at": preview.applied_at,
            }
            for preview in onboarding_previews
        ],
    )


def delete_account_data(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value is not None else None
